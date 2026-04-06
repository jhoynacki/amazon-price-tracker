"""
Amazon Product Advertising API v5 integration.
Supports key rotation and retry logic.
Falls back to scraper when quota is exhausted.
"""
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from itertools import cycle
from typing import Optional

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Key rotation pool
# ---------------------------------------------------------------------------

def _build_key_pool() -> list[tuple[str, str]]:
    """Build list of (access_key, secret_key) pairs from env."""
    pairs = []
    # Primary keys
    if settings.PAAPI_ACCESS_KEY and settings.PAAPI_SECRET_KEY:
        pairs.append((settings.PAAPI_ACCESS_KEY, settings.PAAPI_SECRET_KEY))
    # Additional rotation keys: "key1:secret1,key2:secret2"
    if settings.PAAPI_KEY_ROTATION:
        for entry in settings.PAAPI_KEY_ROTATION.split(","):
            entry = entry.strip()
            if ":" in entry:
                k, s = entry.split(":", 1)
                pairs.append((k.strip(), s.strip()))
    return pairs


_KEY_POOL = _build_key_pool()
_KEY_CYCLE = cycle(_KEY_POOL) if _KEY_POOL else None


def _next_keys() -> tuple[str, str] | None:
    if _KEY_CYCLE is None:
        return None
    return next(_KEY_CYCLE)


# ---------------------------------------------------------------------------
# AWS SigV4 signing helpers
# ---------------------------------------------------------------------------

def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _get_signature_key(secret_key: str, date_stamp: str, region: str, service: str) -> bytes:
    k_date = _sign(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    k_signing = _sign(k_service, "aws4_request")
    return k_signing


def _build_paapi_headers(
    access_key: str,
    secret_key: str,
    payload: dict,
    operation: str,
) -> dict:
    """Build SigV4-signed headers for PA-API v5."""
    service = "ProductAdvertisingAPI"
    host = settings.PAAPI_HOST
    region = settings.PAAPI_REGION
    endpoint = f"https://{host}/paapi5/{operation.lower()}"

    amz_target = f"com.amazon.paapi5.v1.ProductAdvertisingAPIv1.{operation}"
    content_type = "application/json; charset=utf-8"

    body = json.dumps(payload)
    t = datetime.now(timezone.utc)
    amz_date = t.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = t.strftime("%Y%m%d")

    canonical_headers = (
        f"content-encoding:amz-1.0\n"
        f"content-type:{content_type}\n"
        f"host:{host}\n"
        f"x-amz-date:{amz_date}\n"
        f"x-amz-target:{amz_target}\n"
    )
    signed_headers = "content-encoding;content-type;host;x-amz-date;x-amz-target"

    payload_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    canonical_request = "\n".join([
        "POST",
        f"/paapi5/{operation.lower()}",
        "",
        canonical_headers,
        signed_headers,
        payload_hash,
    ])

    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256",
        amz_date,
        credential_scope,
        hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
    ])

    signing_key = _get_signature_key(secret_key, date_stamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    auth = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    return {
        "content-encoding": "amz-1.0",
        "content-type": content_type,
        "host": host,
        "x-amz-date": amz_date,
        "x-amz-target": amz_target,
        "Authorization": auth,
    }, endpoint, body


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class PriceResult:
    def __init__(
        self,
        asin: str,
        title: str = "",
        image_url: str = "",
        product_url: str = "",
        category: str = "",
        brand: str = "",
        price: Optional[Decimal] = None,
        list_price: Optional[Decimal] = None,
        currency: str = "USD",
        in_stock: str = "Unknown",
        deal_badge: str = "",
        source: str = "paapi",
    ):
        self.asin = asin
        self.title = title
        self.image_url = image_url
        self.product_url = product_url
        self.category = category
        self.brand = brand
        self.price = price
        self.list_price = list_price
        self.currency = currency
        self.in_stock = in_stock
        self.deal_badge = deal_badge
        self.source = source

    @property
    def discount_pct(self) -> Optional[Decimal]:
        if self.price and self.list_price and self.list_price > 0:
            return ((self.list_price - self.price) / self.list_price * 100).quantize(Decimal("0.1"))
        return None


def _parse_paapi_item(item: dict) -> PriceResult:
    asin = item.get("ASIN", "")
    info = item.get("ItemInfo", {})
    title = info.get("Title", {}).get("DisplayValue", "Unknown")
    brand = info.get("ByLineInfo", {}).get("Brand", {}).get("DisplayValue", "")
    category = item.get("BrowseNodeInfo", {}).get("BrowseNodes", [{}])[0].get("DisplayName", "")

    images = item.get("Images", {}).get("Primary", {}).get("Large", {})
    image_url = images.get("URL", "")

    detail_url = item.get("DetailPageURL", f"https://www.amazon.com/dp/{asin}")

    # Pricing
    offers = item.get("Offers", {}).get("Listings", [{}])
    price = None
    list_price = None
    currency = "USD"
    in_stock = "Unknown"
    deal_badge = ""

    if offers:
        listing = offers[0]
        price_obj = listing.get("Price", {})
        if price_obj:
            price = Decimal(str(price_obj.get("Amount", 0)))
            currency = price_obj.get("Currency", "USD")

        savings_obj = listing.get("SavingBasis", {})
        if savings_obj:
            list_price = Decimal(str(savings_obj.get("Amount", 0)))

        avail = listing.get("Availability", {})
        if avail:
            in_stock = avail.get("Type", "Unknown")

        promotions = listing.get("Promotions", [])
        if promotions:
            deal_badge = promotions[0].get("Type", "")

    return PriceResult(
        asin=asin,
        title=title,
        image_url=image_url,
        product_url=detail_url,
        category=category,
        brand=brand,
        price=price,
        list_price=list_price,
        currency=currency,
        in_stock=in_stock,
        deal_badge=deal_badge,
        source="paapi",
    )


async def get_items(asins: list[str], retries: int = 3) -> list[PriceResult]:
    """Fetch item details + pricing from PA-API for up to 10 ASINs."""
    if not _KEY_POOL:
        logger.warning("No PA-API keys configured — skipping PA-API call")
        return []

    results = []
    # PA-API allows max 10 items per request
    for chunk_start in range(0, len(asins), 10):
        chunk = asins[chunk_start:chunk_start + 10]
        for attempt in range(retries):
            keys = _next_keys()
            if not keys:
                break
            access_key, secret_key = keys
            payload = {
                "ItemIds": chunk,
                "Resources": [
                    "BrowseNodeInfo.BrowseNodes",
                    "Images.Primary.Large",
                    "ItemInfo.Title",
                    "ItemInfo.ByLineInfo",
                    "Offers.Listings.Price",
                    "Offers.Listings.SavingBasis",
                    "Offers.Listings.Availability.Type",
                    "Offers.Listings.Promotions",
                ],
                "PartnerTag": settings.PAAPI_PARTNER_TAG,
                "PartnerType": "Associates",
                "Marketplace": "www.amazon.com",
            }
            try:
                headers, endpoint, body = _build_paapi_headers(
                    access_key, secret_key, payload, "GetItems"
                )
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(endpoint, headers=headers, content=body)
                    if resp.status_code == 200:
                        data = resp.json()
                        items = data.get("ItemsResult", {}).get("Items", [])
                        results.extend(_parse_paapi_item(item) for item in items)
                        break
                    elif resp.status_code == 429:
                        logger.warning("PA-API rate limit hit, rotating key")
                        wait = 2 ** attempt
                        time.sleep(wait)
                    else:
                        logger.error("PA-API error %s: %s", resp.status_code, resp.text[:200])
                        break
            except Exception as exc:
                logger.error("PA-API request failed: %s", exc)
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)

    return results
