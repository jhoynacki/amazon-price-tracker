"""
Standalone preview server — renders the UI with mock data.
No PostgreSQL or Redis required. For development preview only.
"""
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

BACKEND = Path(__file__).parent / "backend"

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="preview-only-secret")
app.mount("/amazon/static", StaticFiles(directory=str(BACKEND / "app/static")), name="static")
templates = Jinja2Templates(directory=str(BACKEND / "app/templates"))

PREFIX = "/amazon"

# --------------- Mock data ---------------
def mock_product(asin, title, price, list_price, image=""):
    disc = round((list_price - price) / list_price * 100) if list_price else 0
    return SimpleNamespace(
        asin=asin, title=title, image_url=image or "",
        product_url=f"https://www.amazon.com/dp/{asin}",
        current_price=Decimal(str(price)),
        list_price=Decimal(str(list_price)) if list_price else None,
        in_stock="Available", deal_badge="",
    )

def mock_up(id, asin, title, price, list_price, target_price=None, target_discount_pct=None):
    return SimpleNamespace(
        id=id, user_id="preview", asin=asin,
        target_price=Decimal(str(target_price)) if target_price else None,
        target_discount_pct=Decimal(str(target_discount_pct)) if target_discount_pct else None,
        notify_email=True, notify_sms=False, notify_telegram=False, notify_pushover=False,
        source="import", last_alert_price=None, last_alert_at=None,
        product=mock_product(asin, title, price, list_price),
    )

MOCK_USER = SimpleNamespace(
    id="preview", name="Jack", postal_code="10001",
    alert_email="jack@example.com", alert_sms="+15555550100",
    alert_telegram_chat_id="", alert_pushover_user_key="",
    alerts_enabled=True,
)

MOCK_PRODUCTS = [
    mock_up(1, "B08N5KWB9H", "Echo Dot (5th Gen) Smart Speaker with Alexa", 49.99, 59.99, target_price=39.99),
    mock_up(2, "B07XJ8C8F5", "Kindle Paperwhite (11th Gen) – 6.8\" display, 16 GB", 99.99, 139.99, target_discount_pct=30),
    mock_up(3, "B0C4NQJBK2", "Apple AirPods Pro (2nd Generation) with MagSafe Case", 189.00, 249.00),
    mock_up(4, "B09G9HD6PD", "Anker 65W USB-C Charger, 3-Port Fast Charger", 27.99, 35.99, target_price=22.00),
    mock_up(5, "B07PVCVBN7", "LEGO Technic Bugatti Chiron Set 42083", 219.95, 349.99, target_discount_pct=40),
]

# --------------- Routes ---------------
@app.get("/", response_class=HTMLResponse)
@app.get("/amazon", response_class=HTMLResponse)
@app.get("/amazon/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "prefix": PREFIX})

@app.get("/amazon/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    request.session["user_id"] = "preview"
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": MOCK_USER,
        "email": MOCK_USER.alert_email,
        "user_products": MOCK_PRODUCTS,
        "prefix": PREFIX,
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("preview_server:app", host="0.0.0.0", port=8000, reload=True)
