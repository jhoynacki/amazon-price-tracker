"""
Amazon Price Tracker — FastAPI application entry point.
Served at jack-hoy.com/amazon via Nginx reverse proxy.
"""
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
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

app = FastAPI(
    title="Amazon Price Tracker",
    docs_url=f"{settings.APP_PATH_PREFIX}/docs",
    openapi_url=f"{settings.APP_PATH_PREFIX}/openapi.json",
    root_path=settings.APP_PATH_PREFIX,
)

# Middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie="amztracker_session",
    same_site="lax",
    https_only=settings.ENVIRONMENT == "production",
    max_age=7 * 24 * 3600,  # 7 days
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.APP_BASE_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

templates = Jinja2Templates(directory="app/templates")


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
