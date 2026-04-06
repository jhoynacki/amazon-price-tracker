from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Amazon Price Tracker"
    APP_BASE_URL: str = "https://jack-hoy.com"
    APP_PATH_PREFIX: str = "/amazon"
    SECRET_KEY: str = "change-me-in-production-use-secrets-generate"
    ENVIRONMENT: str = "development"

    # Database — Railway injects $DATABASE_URL automatically
    DATABASE_URL: str = "postgresql://tracker:tracker@db:5432/amazon_tracker"
    DATABASE_URL_ASYNC: str = ""   # derived from DATABASE_URL if empty

    # Redis / Celery — Railway injects $REDIS_URL automatically
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = ""    # derived from REDIS_URL if empty
    CELERY_RESULT_BACKEND: str = ""  # derived from REDIS_URL if empty

    # Amazon OAuth (Login with Amazon)
    AMAZON_CLIENT_ID: str = ""
    AMAZON_CLIENT_SECRET: str = ""
    AMAZON_OAUTH_REDIRECT_URI: str = "https://jack-hoy.com/amazon/auth/callback"
    AMAZON_OAUTH_SCOPES: str = "profile postal_code"

    # Amazon Product Advertising API (PA-API v5)
    PAAPI_ACCESS_KEY: str = ""
    PAAPI_SECRET_KEY: str = ""
    PAAPI_PARTNER_TAG: str = ""
    PAAPI_HOST: str = "webservices.amazon.com"
    PAAPI_REGION: str = "us-east-1"
    # Comma-separated list for rotation: key1:secret1,key2:secret2
    PAAPI_KEY_ROTATION: str = ""

    # Encryption key for storing tokens at rest (32 bytes, base64url encoded)
    TOKEN_ENCRYPTION_KEY: str = ""

    # Email Alerts
    EMAIL_PROVIDER: str = "smtp"  # smtp or sendgrid
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@jack-hoy.com"
    SENDGRID_API_KEY: str = ""

    # SMS Alerts (Twilio)
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""

    # Push Notifications
    TELEGRAM_BOT_TOKEN: str = ""
    PUSHOVER_APP_TOKEN: str = ""

    # Scraper Proxy (optional — comma-separated list)
    PROXY_LIST: str = ""

    # PIN gate (leave empty to disable)
    ACCESS_PIN: str = ""

    # Price check interval in hours
    PRICE_CHECK_INTERVAL_HOURS: int = 6

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()
