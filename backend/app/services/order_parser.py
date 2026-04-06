"""
Parse Amazon Order History exports (CSV or ZIP containing CSV).
Amazon provides this via: Account → Download Your Data → Order History.
Extracts unique ASINs from all orders.
"""
import csv
import io
import logging
import re
import zipfile
from typing import Iterator

logger = logging.getLogger(__name__)

# Column name patterns for the Amazon order history CSV
ASIN_COLS = {"asin", "asin/isbn"}
TITLE_COLS = {"title", "product name", "product title", "item title"}


def _normalize_asin(raw: str) -> str | None:
    """Extract and validate an ASIN (10 chars, alphanumeric)."""
    raw = raw.strip().upper()
    # Sometimes columns contain extra info
    match = re.search(r"\b([A-Z0-9]{10})\b", raw)
    if match:
        return match.group(1)
    return None


def _parse_csv_stream(stream: io.TextIOBase) -> Iterator[dict]:
    """Yield rows from CSV as dicts with normalized keys."""
    reader = csv.DictReader(stream)
    if not reader.fieldnames:
        return
    for row in reader:
        yield {k.strip().lower(): v.strip() for k, v in row.items() if k}


def extract_asins_from_csv(content: bytes) -> list[dict]:
    """
    Parse raw CSV bytes from Amazon Order History download.
    Returns list of {"asin": ..., "title": ...} dicts (deduplicated by ASIN).
    """
    seen: set[str] = set()
    items: list[dict] = []

    try:
        text = content.decode("utf-8-sig", errors="replace")
        stream = io.StringIO(text)
        for row in _parse_csv_stream(stream):
            asin_raw = ""
            for col in ASIN_COLS:
                if col in row:
                    asin_raw = row[col]
                    break

            asin = _normalize_asin(asin_raw) if asin_raw else None
            if not asin or asin in seen:
                continue

            title = ""
            for col in TITLE_COLS:
                if col in row and row[col]:
                    title = row[col][:255]
                    break

            seen.add(asin)
            items.append({"asin": asin, "title": title})
    except Exception as exc:
        logger.error("CSV parse error: %s", exc)

    logger.info("Extracted %d unique ASINs from CSV", len(items))
    return items


def extract_asins_from_zip(content: bytes) -> list[dict]:
    """
    Parse a ZIP file from Amazon's data export.
    Finds all CSV files inside and combines results.
    """
    all_items: dict[str, dict] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            csv_files = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            logger.info("Found %d CSV files in ZIP: %s", len(csv_files), csv_files)
            for fname in csv_files:
                with zf.open(fname) as f:
                    raw = f.read()
                    for item in extract_asins_from_csv(raw):
                        all_items.setdefault(item["asin"], item)
    except Exception as exc:
        logger.error("ZIP parse error: %s", exc)

    return list(all_items.values())


def parse_order_upload(filename: str, content: bytes) -> list[dict]:
    """Entry point: dispatch to CSV or ZIP parser based on file extension."""
    fname = filename.lower()
    if fname.endswith(".zip"):
        return extract_asins_from_zip(content)
    elif fname.endswith(".csv"):
        return extract_asins_from_csv(content)
    else:
        # Try CSV first, fall back to zip
        items = extract_asins_from_csv(content)
        if not items:
            items = extract_asins_from_zip(content)
        return items
