import asyncio
import logging

from .celery_app import celery_app
from ..database import SessionLocal
from ..services.price_tracker import check_all_products, check_and_update_product

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.price_check.check_all_prices",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def check_all_prices(self):
    """Celery beat task: check prices for all tracked products."""
    logger.info("Starting scheduled price check")
    db = SessionLocal()
    try:
        asyncio.get_event_loop().run_until_complete(check_all_products(db))
        logger.info("Scheduled price check complete")
    except Exception as exc:
        logger.error("Price check failed: %s", exc)
        raise self.retry(exc=exc)
    finally:
        db.close()


@celery_app.task(
    name="app.tasks.price_check.check_single_product",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def check_single_product(self, asin: str):
    """Trigger an immediate price check for a single ASIN."""
    logger.info("Checking price for ASIN %s", asin)
    db = SessionLocal()
    try:
        asyncio.get_event_loop().run_until_complete(check_and_update_product(asin, db))
    except Exception as exc:
        logger.error("Single product check failed for %s: %s", asin, exc)
        raise self.retry(exc=exc)
    finally:
        db.close()
