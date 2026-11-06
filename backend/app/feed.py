"""Product feed: the row a merchant would submit to PayPal's agent programs (Store Sync, Agent Ready).

PayPal has no public sandbox API for Store Sync, so nothing is ever submitted. This builds the file in Google
product feed style from what the shopper actually read on the product page (its Product JSON-LD and page facts,
stored on the run as `product_snapshot`), never from the store's source code. A field the page doesn't show
stays empty and is reported as a gap with a one-line fix.
"""

import csv
import io
import re
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urljoin

COLUMNS = ("id", "title", "description", "link", "image_link", "price", "availability", "brand", "gtin", "mpn",
           "condition")
REQUIRED = ("id", "title", "description", "link", "image_link", "price", "availability")

FIXES = {
    "id": "Add a unique SKU to the page and to the Product JSON-LD (\"sku\"), for example \"FH-MUG-01\".",
    "title": "Give the product page one clear title: an <h1> with the product name, and \"name\" in the Product JSON-LD.",
    "description": "Add a product description in the Product JSON-LD (\"description\") and a <meta name=\"description\"> tag.",
    "link": "Give the product page a canonical link: <link rel=\"canonical\"> and \"offers.url\" in the Product JSON-LD.",
    "image_link": "Add the product photo to the Product JSON-LD (\"image\") with a full https:// address.",
    "price": "Show the price as text with its currency, and set \"offers.price\" and \"offers.priceCurrency\" in the Product JSON-LD.",
    "availability": "Say \"In stock\" or \"Out of stock\" in the page text and set \"offers.availability\" in the Product JSON-LD.",
    "brand": "Add \"brand\" (a name) to the Product JSON-LD.",
    "gtin": "Add the barcode number (\"gtin13\" or \"gtin12\") to the Product JSON-LD. Handmade goods with no barcode can skip it.",
    "mpn": "Add the manufacturer part number (\"mpn\") to the Product JSON-LD.",
    "condition": "Add \"offers.itemCondition\" (for example https://schema.org/NewCondition) to the Product JSON-LD.",
}

AVAILABILITY = {
    "instock": "in_stock", "limitedavailability": "in_stock", "onlineonly": "in_stock", "instoreonly": "in_stock",
    "outofstock": "out_of_stock", "soldout": "out_of_stock", "discontinued": "out_of_stock",
    "preorder": "preorder", "presale": "preorder", "backorder": "backorder",
}
CONDITION = {"newcondition": "new", "usedcondition": "used", "refurbishedcondition": "refurbished",
             "damagedcondition": "used"}
STOCK_TEXT = re.compile(r"\b(in stock|out of stock|sold out|backorder|back-order|pre-?order)\b", re.I)
SKU_TEXT = re.compile(r"\bSKU:?\s*([A-Za-z0-9][\w.\-]{1,40})")
CURRENCY_SYMBOLS = (("US$", "USD"), ("USD", "USD"), ("$", "USD"), ("€", "EUR"), ("£", "GBP"))
MAX_TEXT = 5000


def _text(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("name") or value.get("@id") or value.get("url")
    if isinstance(value, list):
        value = next((v for v in (_text(i) for i in value) if v), None)
    if value is None or isinstance(value, bool):
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text[:MAX_TEXT] or None


def _offer(product: dict[str, Any]) -> dict[str, Any]:
    offers = product.get("offers")
    if isinstance(offers, list):
        offers = offers[0] if offers else None
    return offers if isinstance(offers, dict) else {}


def _tail(value: Any) -> str:
    return re.sub(r"[^a-z]", "", str(value).rsplit("/", 1)[-1].lower())


def snapshot_from_facts(facts: dict[str, Any], products: list[dict[str, Any]]) -> dict[str, Any]:
    """The few things from a product page's facts the feed needs, kept on the run. `products` are the page's
    Product JSON-LD objects (checks._products_in_jsonld)."""
    text = facts.get("main_text") or ""
    stock = STOCK_TEXT.search(text)
    sku = SKU_TEXT.search(text)
    return {
        "url": facts.get("url"),
        "title": facts.get("title"),
        "product": products[0] if products else None,
        "meta_description": facts.get("meta_description"),
        "canonical": facts.get("canonical"),
        "prices": [{"text": p.get("text"), "value": p.get("value")} for p in (facts.get("prices") or [])[:3]],
        "images": [{"src": i.get("src"), "alt": i.get("alt")} for i in (facts.get("images") or [])[:3]],
        "stock_text": stock.group(1) if stock else None,
        "sku_text": sku.group(1) if sku else None,
    }


def _price(snap: dict[str, Any], offer: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """(value, source, note). A price without a currency is only partial: the feed needs "24.00 USD"."""
    code = _text(offer.get("priceCurrency"))
    raw = offer.get("price")
    if raw not in (None, ""):
        try:
            amount = f"{Decimal(str(raw)):.2f}"
        except InvalidOperation:
            amount = None
        if amount:
            if code:
                return f"{amount} {code.upper()}", "Product JSON-LD", None
            return amount, "Product JSON-LD", "The currency is missing, so the price can't be submitted as it is."
    for p in snap.get("prices") or []:
        try:
            amount = f"{Decimal(str(p.get('value'))):.2f}"
        except InvalidOperation:
            continue
        label = p.get("text") or ""
        code = next((c for symbol, c in CURRENCY_SYMBOLS if symbol in label), None)
        if code:
            return f"{amount} {code}", "page text", None
        return amount, "page text", "The page shows the price without a currency, so it can't be submitted as it is."
    return None, None, None


def _first_image(snap: dict[str, Any], product: dict[str, Any]) -> tuple[str | None, str | None]:
    base = snap.get("url") or ""
    ld = _text(product.get("image"))
    if ld:
        return urljoin(base, ld), "Product JSON-LD"
    for img in snap.get("images") or []:
        if img.get("src"):
            return urljoin(base, img["src"]), "page image"
    return None, None


def build_feed(snap: dict[str, Any] | None) -> dict[str, Any] | None:
    """{row, fields, required_found, required_total, ready}, or None if the shopper never read a product page.
    Each field: field, required, status (found | partial | missing), value, source, fix (only when not found)."""
    if not snap:
        return None
    product = snap.get("product") or {}
    offer = _offer(product)
    base = snap.get("url") or ""
    found: dict[str, tuple[str | None, str | None, str | None]] = {}  # field -> (value, source, note)

    sku = _text(product.get("sku"))
    found["id"] = (sku, "Product JSON-LD", None) if sku else (snap.get("sku_text"), "page text", None)
    name = _text(product.get("name"))
    if name:
        found["title"] = (name, "Product JSON-LD", None)
    else:
        title = _text((snap.get("title") or "").split("|")[0])
        found["title"] = (title, "page title", None)
    desc = _text(product.get("description"))
    found["description"] = (desc, "Product JSON-LD", None) if desc else (_text(snap.get("meta_description")), "meta description", None)
    link = _text(offer.get("url")) or _text(product.get("url"))
    if link:
        found["link"] = (urljoin(base, link), "Product JSON-LD", None)
    elif snap.get("canonical"):
        found["link"] = (urljoin(base, snap["canonical"]), "canonical link", None)
    else:
        found["link"] = (base or None, "page address", None)
    image, image_source = _first_image(snap, product)
    found["image_link"] = (image, image_source, None)
    found["price"] = _price(snap, offer)
    availability = AVAILABILITY.get(_tail(offer.get("availability")))
    if availability:
        found["availability"] = (availability, "Product JSON-LD", None)
    else:
        hit = STOCK_TEXT.search(snap.get("stock_text") or "")
        label = (hit.group(1).lower() if hit else "").replace("-", "").replace(" ", "")
        mapped = {"instock": "in_stock", "outofstock": "out_of_stock", "soldout": "out_of_stock",
                  "backorder": "backorder", "preorder": "preorder"}.get(label)
        found["availability"] = (mapped, "page text", None)
    found["brand"] = (_text(product.get("brand")), "Product JSON-LD", None)
    gtin = next((_text(product.get(k)) for k in ("gtin", "gtin8", "gtin12", "gtin13", "gtin14") if _text(product.get(k))), None)
    found["gtin"] = (gtin, "Product JSON-LD", None)
    found["mpn"] = (_text(product.get("mpn")), "Product JSON-LD", None)
    found["condition"] = (CONDITION.get(_tail(offer.get("itemCondition"))), "Product JSON-LD", None)

    fields, row = [], {}
    for name_ in COLUMNS:
        value, source, note = found[name_]
        status = "missing" if not value else ("partial" if note else "found")
        row[name_] = value or ""
        fields.append({
            "field": name_, "required": name_ in REQUIRED, "status": status, "value": value or None,
            "source": source if value else None, "note": note,
            "fix": None if status == "found" else FIXES[name_],
        })
    required = [f for f in fields if f["required"]]
    found_required = sum(1 for f in required if f["status"] == "found")
    return {"row": row, "fields": fields, "required_found": found_required, "required_total": len(required),
            "ready": found_required == len(required), "source_url": base or None}


def _safe_cell(value: str) -> str:
    # A feed built from a third-party page must not carry spreadsheet formulas.
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def feed_csv(feed: dict[str, Any]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    writer.writerow([_safe_cell(feed["row"][c]) for c in COLUMNS])
    return out.getvalue()
