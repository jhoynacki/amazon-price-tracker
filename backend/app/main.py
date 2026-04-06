"""
Amazon Price Tracker — FastAPI application entry point.
Served at jack-hoy.com/amazon via Nginx reverse proxy.
"""
import logging

from fastapi import FastAPI, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .config import get_settings
from .database import Base, engine
from .models import User, Product, UserProduct, PriceHistory  # noqa: F401 — register models
from .routers import auth, dashboard, products

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

# Auto-create tables on startup (use Alembic for production migrations)
Base.metadata.create_all(bind=engine)

templates = Jinja2Templates(directory="app/templates")

PIN_EXEMPT = {"/health", f"{settings.APP_PATH_PREFIX}/_pin"}


class PinGateMiddleware(BaseHTTPMiddleware):
    """Block all routes unless the session has a valid PIN or PIN is not set."""

    async def dispatch(self, request: Request, call_next):
        if not settings.ACCESS_PIN:
            return await call_next(request)

        path = request.url.path
        if path in PIN_EXEMPT or path.startswith(f"{settings.APP_PATH_PREFIX}/static"):
            return await call_next(request)

        if not request.session.get("pin_ok"):
            next_url = str(request.url)
            return RedirectResponse(
                url=f"{settings.APP_PATH_PREFIX}/_pin?next={next_url}"
            )

        return await call_next(request)


app = FastAPI(
    title="Amazon Price Tracker",
    docs_url=f"{settings.APP_PATH_PREFIX}/docs",
    openapi_url=f"{settings.APP_PATH_PREFIX}/openapi.json",
    root_path=settings.APP_PATH_PREFIX,
)

# Middleware — Starlette applies in LIFO order (last added = outermost = runs first).
# Desired execution order: SessionMiddleware → CORSMiddleware → PinGateMiddleware → routes
# So we add them in reverse: PinGate first, Session last.
app.add_middleware(PinGateMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.APP_BASE_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie="amztracker_session",
    same_site="lax",
    https_only=settings.ENVIRONMENT == "production",
    max_age=7 * 24 * 3600,  # 7 days
)

# Static files
app.mount(
    f"{settings.APP_PATH_PREFIX}/static",
    StaticFiles(directory="app/static"),
    name="static",
)

# Routers (all prefixed under /amazon)
app.include_router(auth.router, prefix=settings.APP_PATH_PREFIX)
app.include_router(dashboard.router, prefix=settings.APP_PATH_PREFIX)
app.include_router(products.router, prefix=f"{settings.APP_PATH_PREFIX}/products")


@app.exception_handler(401)
async def unauthorized_handler(request: Request, exc):
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "prefix": settings.APP_PATH_PREFIX},
        status_code=401,
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    return RedirectResponse(url=f"{settings.APP_PATH_PREFIX}/")


@app.get(f"{settings.APP_PATH_PREFIX}/_pin", response_class=HTMLResponse)
async def pin_page(request: Request, next: str = ""):
    return templates.TemplateResponse(
        "pin.html",
        {"request": request, "prefix": settings.APP_PATH_PREFIX,
         "next": next or f"{settings.APP_PATH_PREFIX}/", "error": False},
    )


@app.post(f"{settings.APP_PATH_PREFIX}/_pin", response_class=HTMLResponse)
async def pin_submit(
    request: Request,
    pin: str = Form(...),
    next: str = Form(default=""),
):
    if pin == settings.ACCESS_PIN:
        request.session["pin_ok"] = True
        return RedirectResponse(
            url=next or f"{settings.APP_PATH_PREFIX}/", status_code=303
        )
    return templates.TemplateResponse(
        "pin.html",
        {"request": request, "prefix": settings.APP_PATH_PREFIX,
         "next": next, "error": True},
        status_code=401,
    )
