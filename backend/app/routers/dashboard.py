from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import UserProduct
from ..routers.auth import get_current_user
from ..services.crypto import decrypt

settings = get_settings()
router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user_id = request.session.get("user_id")
    if user_id:
        return templates.TemplateResponse(
            "redirect.html",
            {"request": request, "url": f"{settings.APP_PATH_PREFIX}/dashboard"},
        )
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "prefix": settings.APP_PATH_PREFIX},
    )


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    user_products = (
        db.query(UserProduct)
        .filter(UserProduct.user_id == user.id)
        .all()
    )

    email = ""
    if user.alert_email:
        try:
            email = decrypt(user.encrypted_email) if user.encrypted_email else user.alert_email
        except Exception:
            email = user.alert_email

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "email": email,
            "user_products": user_products,
            "prefix": settings.APP_PATH_PREFIX,
        },
    )


@router.post("/settings", response_class=HTMLResponse)
async def save_settings(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    form = await request.form()
    user.alert_email = form.get("alert_email", user.alert_email)
    user.alert_sms = form.get("alert_sms", user.alert_sms)
    user.alert_telegram_chat_id = form.get("alert_telegram_chat_id", user.alert_telegram_chat_id)
    user.alert_pushover_user_key = form.get("alert_pushover_user_key", user.alert_pushover_user_key)
    user.alerts_enabled = bool(form.get("alerts_enabled"))
    db.commit()
    return HTMLResponse(
        '<div class="alert alert-success">Settings saved!</div>'
    )
