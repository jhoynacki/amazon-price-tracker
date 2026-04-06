"""
Product management routes: add, delete, edit tracking rules, import from CSV/ZIP.
All responses use HTMX-compatible HTML fragments or JSON.
"""
import logging
import re
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Product, UserProduct, PriceHistory, BlockedAsin
from ..routers.auth import get_current_user
from ..services.order_parser import parse_order_upload
from ..services.price_tracker import fetch_price
from ..tasks.price_check import check_single_product

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/products", tags=["products"])
templates = Jinja2Templates(directory="app/templates")

ASIN_RE = re.compile(r"/dp/([A-Z0-9]{10})|/gp/product/([A-Z0-9]{10})|^([A-Z0-9]{10})$")


def _extract_asin(raw: str) -> Optional[str]:
    raw = raw.strip()
    m = ASIN_RE.search(raw.upper())
    if m:
        return m.group(1) or m.group(2) or m.group(3)
    return None


@router.post("/add", response_class=HTMLResponse)
async def add_product(
    request: Request,
    asin_or_url: str = Form(...),
    target_price: Optional[str] = Form(None),
    target_discount_pct: Optional[str] = Form(None),
    notify_email: bool = Form(False),
    notify_sms: bool = Form(False),
    notify_telegram: bool = Form(False),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    asin = _extract_asin(asin_or_url)
    if not asin:
        return HTMLResponse(
            '<div class="alert alert-error">Invalid ASIN or Amazon URL.</div>', status_code=400
        )

    # Check if already tracking
    existing = (
        db.query(UserProduct)
        .filter(UserProduct.user_id == user.id, UserProduct.asin == asin)
        .first()
    )
    if existing:
        return HTMLResponse(
            '<div class="alert alert-warning">You are already tracking this product.</div>'
        )

    # Fetch product info (fire and forget initial data)
    result = await fetch_price(asin)
    if not result and not db.query(Product).filter(Product.asin == asin).first():
        # Create stub product
        product = Product(
            asin=asin,
            title=f"ASIN {asin}",
            product_url=f"https://www.amazon.com/dp/{asin}",
        )
        db.add(product)
        db.flush()
    elif result:
        product = db.query(Product).filter(Product.asin == asin).first()
        if not product:
            product = Product(asin=asin)
            db.add(product)
        product.title = result.title or product.title or asin
        product.image_url = result.image_url or product.image_url
        product.product_url = result.product_url or product.product_url
        product.current_price = result.price
        product.list_price = result.list_price
        product.in_stock = result.in_stock
        db.flush()

    # Parse optional thresholds
    t_price = None
    if target_price:
        try:
            t_price = Decimal(target_price.replace("$", "").strip())
        except Exception:
            pass

    t_discount = None
    if target_discount_pct:
        try:
            t_discount = Decimal(target_discount_pct.replace("%", "").strip())
        except Exception:
            pass

    up = UserProduct(
        user_id=user.id,
        asin=asin,
        target_price=t_price,
        target_discount_pct=t_discount,
        notify_email=notify_email,
        notify_sms=notify_sms,
        notify_telegram=notify_telegram,
        source="manual",
    )
    db.add(up)
    db.commit()
    db.refresh(up)

    # Schedule immediate price check
    check_single_product.delay(asin)

    return templates.TemplateResponse(
        "partials/product_row.html",
        {
            "request": request,
            "up": up,
            "product": up.product,
            "prefix": settings.APP_PATH_PREFIX,
        },
    )


@router.delete("/{up_id}", response_class=HTMLResponse)
async def delete_product(
    up_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    up = (
        db.query(UserProduct)
        .filter(UserProduct.id == up_id, UserProduct.user_id == user.id)
        .first()
    )
    if not up:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(up)
    db.commit()
    return HTMLResponse("")  # HTMX will swap empty → row removed


@router.put("/{up_id}", response_class=HTMLResponse)
async def update_product(
    request: Request,
    up_id: int,
    target_price: Optional[str] = Form(None),
    target_discount_pct: Optional[str] = Form(None),
    notify_email: bool = Form(False),
    notify_sms: bool = Form(False),
    notify_telegram: bool = Form(False),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    up = (
        db.query(UserProduct)
        .filter(UserProduct.id == up_id, UserProduct.user_id == user.id)
        .first()
    )
    if not up:
        raise HTTPException(status_code=404, detail="Not found")

    if target_price:
        try:
            up.target_price = Decimal(target_price.replace("$", "").strip())
        except Exception:
            pass
    else:
        up.target_price = None

    if target_discount_pct:
        try:
            up.target_discount_pct = Decimal(target_discount_pct.replace("%", "").strip())
        except Exception:
            pass
    else:
        up.target_discount_pct = None

    up.notify_email = notify_email
    up.notify_sms = notify_sms
    up.notify_telegram = notify_telegram
    db.commit()
    db.refresh(up)

    return templates.TemplateResponse(
        "partials/product_row.html",
        {
            "request": request,
            "up": up,
            "product": up.product,
            "prefix": settings.APP_PATH_PREFIX,
        },
    )


@router.post("/import", response_class=HTMLResponse)
async def import_orders(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:  # 50 MB limit
        return HTMLResponse('<div class="alert alert-error">File too large (max 50 MB).</div>', 400)

    items = parse_order_upload(file.filename or "upload.csv", content)
    if not items:
        return HTMLResponse('<div class="alert alert-error">No valid ASINs found in file.</div>')

    # Load blocked ASINs for this user so we never re-add them
    blocked = {
        b.asin for b in db.query(BlockedAsin).filter(BlockedAsin.user_id == user.id).all()
    }

    added = 0
    skipped_blocked = 0
    for item in items:
        asin = item["asin"]

        if asin in blocked:
            skipped_blocked += 1
            continue

        title = item.get("title", f"ASIN {asin}")

        # Ensure Product row exists
        product = db.query(Product).filter(Product.asin == asin).first()
        if not product:
            product = Product(
                asin=asin,
                title=title,
                product_url=f"https://www.amazon.com/dp/{asin}",
            )
            db.add(product)
            db.flush()
        elif title and not product.title:
            product.title = title

        # Add to user's tracking list if not already there
        existing = (
            db.query(UserProduct)
            .filter(UserProduct.user_id == user.id, UserProduct.asin == asin)
            .first()
        )
        if not existing:
            up = UserProduct(
                user_id=user.id,
                asin=asin,
                notify_email=True,
                source="import",
            )
            db.add(up)
            added += 1

    db.commit()

    # Schedule price checks for all new products
    for item in items:
        check_single_product.delay(item["asin"])

    blocked_note = f" ({skipped_blocked} permanently hidden items skipped)" if skipped_blocked else ""
    return HTMLResponse(
        f'<div class="alert alert-success">'
        f'Imported {added} new products from {len(items)} order items{blocked_note}. '
        f'Prices will update shortly.</div>'
        f'<script>setTimeout(()=>window.location.reload(),3000)</script>'
    )


@router.get("/{asin}/history")
async def price_history_data(
    asin: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Return JSON price history for ApexCharts."""
    # Verify user tracks this product
    up = (
        db.query(UserProduct)
        .filter(UserProduct.user_id == user.id, UserProduct.asin == asin)
        .first()
    )
    if not up:
        raise HTTPException(status_code=403, detail="Not tracking this product")

    rows = (
        db.query(PriceHistory)
        .filter(PriceHistory.asin == asin)
        .order_by(PriceHistory.checked_at.asc())
        .limit(500)
        .all()
    )
    data = [
        {
            "x": row.checked_at.isoformat(),
            "y": float(row.price) if row.price else None,
        }
        for row in rows
    ]
    return {"asin": asin, "data": data}


@router.post("/{asin}/refresh", response_class=HTMLResponse)
async def refresh_product(
    asin: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Queue an immediate price check."""
    check_single_product.delay(asin)
    return HTMLResponse('<span class="text-green-500">Refresh queued!</span>')


@router.post("/{up_id}/block", response_class=HTMLResponse)
async def block_product(
    up_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Permanently hide a product — removes it and blocks re-import."""
    up = (
        db.query(UserProduct)
        .filter(UserProduct.id == up_id, UserProduct.user_id == user.id)
        .first()
    )
    if not up:
        raise HTTPException(status_code=404, detail="Not found")

    asin = up.asin

    # Add to blocklist if not already there
    already_blocked = (
        db.query(BlockedAsin)
        .filter(BlockedAsin.user_id == user.id, BlockedAsin.asin == asin)
        .first()
    )
    if not already_blocked:
        db.add(BlockedAsin(user_id=user.id, asin=asin))

    db.delete(up)
    db.commit()
    return HTMLResponse("")  # HTMX swaps row out


@router.get("/blocked", response_class=HTMLResponse)
async def blocked_list(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Return the list of permanently hidden ASINs."""
    blocked = db.query(BlockedAsin).filter(BlockedAsin.user_id == user.id).all()
    return templates.TemplateResponse(
        "partials/blocked_list.html",
        {"request": request, "blocked": blocked, "prefix": settings.APP_PATH_PREFIX},
    )


@router.delete("/blocked/{asin}", response_class=HTMLResponse)
async def unblock_product(
    asin: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Remove an ASIN from the permanent blocklist."""
    db.query(BlockedAsin).filter(
        BlockedAsin.user_id == user.id, BlockedAsin.asin == asin
    ).delete()
    db.commit()
    return HTMLResponse("")
