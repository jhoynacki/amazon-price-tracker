import os
from celery import Celery
from celery.schedules import crontab
from ..config import get_settings

settings = get_settings()

# Railway injects REDIS_URL; fall back to config values
_redis = os.environ.get("REDIS_URL", settings.REDIS_URL)
_broker = os.environ.get("CELERY_BROKER_URL", settings.CELERY_BROKER_URL or _redis)
_backend = os.environ.get("CELERY_RESULT_BACKEND", settings.CELERY_RESULT_BACKEND or _redis)

celery_app = Celery(
    "amazon_tracker",
    broker=_broker,
    backend=_backend,
    include=["app.tasks.price_check"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_track_started=True,
    beat_schedule={
        "check-prices-every-6-hours": {
            "task": "app.tasks.price_check.check_all_prices",
            "schedule": crontab(minute=0, hour="*/6"),
        },
    },
)
