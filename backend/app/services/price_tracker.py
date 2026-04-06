"""
Core price tracking logic: fetch prices, store history, trigger alerts.
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Product, UserProduct, PriceHistory
from ..services import amazon_api, scraper, alerts
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def fetch_price(asin: str) -> Optional[amazon_api.PriceResult]:
    """Try PA-API first; fall back to scraper."""
    results = await amazon_api.get_items([asin])
    if results:
        return results[0]
    logger.info("PA-API returned nothing for %s, trying scraper", asin)
    return await scraper.scrape_asin(asin)


async def check_and_update_product(asin: str, db: Session) -> Optional[PriceHistory]:
    """Fetch latest price for ASIN, store history, update product cache."""
    result = await fetch_price(asin)
    if not result:
        logger.warning("Could not fetch price for ASIN %s", asin)
        return None

    # Update Product cache
    product = db.query(Product).filter(Product.asin == asin).first()
    if not product:
        product = Product(asin=asin)
        db.add(product)

    if result.title:
        product.title = result.title
    if result.image_url:
        product.image_url = result.image_url
    if result.product_url:
        product.product_url = result.product_url
    if result.category:
        product.category = result.category
    if result.brand:
        product.brand = result.brand

    product.current_price = result.price
    product.list_price = result.list_price
    product.in_stock = result.in_stock
    product.last_checked = datetime.now(timezone.utc)

    # Store price history
    entry = PriceHistory(
        asin=asin,
        price=result.price,
        list_price=result.list_price,
        discount_pct=result.discount_pct,
        deal_badge=result.deal_badge,
        in_stock=result.in_stock,
        source=result.source,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    # Check alert conditions for each user tracking this product
    user_products = db.query(UserProduct).filter(UserProduct.asin == asin).all()
    for up in user_products:
        await _check_alert(up, result, db)

    return entry


async def _check_alert(up: UserProduct, result: amazon_api.PriceResult, db: Session):
    """Evaluate alert conditions and send notification if triggered."""
    if not result.price:
        return

    user = up.user
    if not user or not user.alerts_enabled:
        return

    triggered = False
    reason = ""

    if up.target_price and result.price <= up.target_price:
        triggered = True
        reason = f"Price dropped to ${result.price:.2f} (target: ${up.target_price:.2f})"

    if not triggered and up.target_discount_pct and result.discount_pct:
        if result.discount_pct >= up.target_discount_pct:
            triggered = True
            reason = f"{result.discount_pct:.0f}% off (target: {up.target_discount_pct:.0f}%)"

    if not triggered:
        return

    # Avoid duplicate alerts for same price
    if up.last_alert_price and abs(up.last_alert_price - result.price) < Decimal("0.01"):
        return

    logger.info("Alert triggered for user %s, ASIN %s: %s", user.id, up.asin, reason)

    await alerts.send_price_alert(
        user=user,
        user_product=up,
        result=result,
        reason=reason,
    )

    up.last_alert_price = result.price
    up.last_alert_at = datetime.now(timezone.utc)
    db.commit()


async def check_all_products(db: Session):
    """Check all tracked products. Called by Celery task."""
    products = db.query(Product).all()
    logger.info("Checking prices for %d products", len(products))
    for product in products:
        try:
            await check_and_update_product(product.asin, db)
        except Exception as exc:
            logger.error("Error checking ASIN %s: %s", product.asin, exc)
