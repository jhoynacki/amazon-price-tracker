"""
Playwright-based fallback scraper for Amazon product pages.
Used when PA-API quota is exhausted or keys are not configured.
Implements rotating user agents, optional proxy support, and anti-bot delays.
"""
import asyncio
import logging
import random
import re
from decimal import Decimal
from typing import Optional

from fake_useragent import UserAgent

from ..config import get_settings
from .amazon_api import PriceResult

logger = logging.getLogger(__name__)
settings = get_settings()

_ua = UserAgent()

PROXIES: list[str] = [p.strip() for p in settings.PROXY_LIST.split(",") if p.strip()]

ANTI_BOT_DELAY_RANGE = (2.0, 6.0)


def _get_proxy() -> Optional[str]:
    if PROXIES:
        return random.choice(PROXIES)
    return None


def _parse_price(text: str) -> Optional[Decimal]:
    """Extract decimal price from text like '$12.99' or '12.99'."""
    if not text:
        return None
    cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
    try:
        return Decimal(cleaned) if cleaned else None
    except Exception:
        return None


async def scrape_asin(asin: str) -> Optional[PriceResult]:
    """Scrape a single Amazon product page for pricing data."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("Playwright not installed — run: playwright install chromium")
        return None

    url = f"https://www.amazon.com/dp/{asin}"
    proxy = _get_proxy()

    playwright_proxy = None
    if proxy:
        # Support http://user:pass@host:port or http://host:port
        playwright_proxy = {"server": proxy}

    async with async_playwright() as p:
        browser_args = ["--no-sandbox", "--disable-dev-shm-usage"]
        browser = await p.chromium.launch(headless=True, args=browser_args)
        context = await browser.new_context(
            user_agent=_ua.random,
            viewport={"width": 1280, "height": 800},
            proxy=playwright_proxy,
            locale="en-US",
            timezone_id="America/New_York",
        )
        # Block images/css to speed things up
        await context.route(
            "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2}",
            lambda route: route.abort()
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            # Anti-bot random delay
            await asyncio.sleep(random.uniform(*ANTI_BOT_DELAY_RANGE))

            # Check for CAPTCHA
            if "robot" in (await page.title()).lower() or "captcha" in (await page.content()).lower():
                logger.warning("CAPTCHA detected for ASIN %s", asin)
                return None

            title = ""
            try:
                title_el = await page.query_selector("#productTitle")
                if title_el:
                    title = (await title_el.inner_text()).strip()
            except Exception:
                pass

            price: Optional[Decimal] = None
            try:
                # Try various price selectors Amazon uses
                for selector in [
                    ".a-price .a-offscreen",
                    "#priceblock_ourprice",
                    "#priceblock_dealprice",
                    "#priceblock_saleprice",
                    ".apexPriceToPay .a-offscreen",
                    "#corePrice_feature_div .a-offscreen",
                ]:
                    el = await page.query_selector(selector)
                    if el:
                        text = await el.inner_text()
                        price = _parse_price(text)
                        if price:
                            break
            except Exception:
                pass

            list_price: Optional[Decimal] = None
            try:
                for selector in [
                    ".basisPrice .a-offscreen",
                    "#listPrice",
                    ".a-text-strike",
                    "#priceblock_listprice",
                ]:
                    el = await page.query_selector(selector)
                    if el:
                        text = await el.inner_text()
                        list_price = _parse_price(text)
                        if list_price:
                            break
            except Exception:
                pass

            image_url = ""
            try:
                img_el = await page.query_selector("#landingImage, #imgBlkFront")
                if img_el:
                    image_url = await img_el.get_attribute("src") or ""
            except Exception:
                pass

            in_stock = "Unknown"
            try:
                avail_el = await page.query_selector("#availability span")
                if avail_el:
                    avail_text = (await avail_el.inner_text()).strip().lower()
                    in_stock = "Available" if "in stock" in avail_text else "Unavailable"
            except Exception:
                pass

            deal_badge = ""
            try:
                badge_el = await page.query_selector("#dealBadge_feature_div, .dealBadge, #dealsAccordionRow")
                if badge_el:
                    deal_badge = (await badge_el.inner_text()).strip()[:64]
            except Exception:
                pass

            return PriceResult(
                asin=asin,
                title=title,
                image_url=image_url,
                product_url=url,
                price=price,
                list_price=list_price,
                in_stock=in_stock,
                deal_badge=deal_badge,
                source="scraper",
            )

        except Exception as exc:
            logger.error("Scraping ASIN %s failed: %s", asin, exc)
            return None
        finally:
            await context.close()
            await browser.close()


async def scrape_asins(asins: list[str]) -> list[PriceResult]:
    """Scrape multiple ASINs with rate limiting between requests."""
    results = []
    for asin in asins:
        result = await scrape_asin(asin)
        if result:
            results.append(result)
        # Rate limiting between requests to avoid blocks
        await asyncio.sleep(random.uniform(3.0, 8.0))
    return results
