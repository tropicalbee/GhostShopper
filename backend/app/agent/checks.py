"""Deterministic detectors: page facts (collected from the live DOM) -> check outcomes.

Pure functions, no browser and no LLM, so they are unit-testable and the score stays reproducible.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

PRICE_RE = re.compile(r"(?:\$|USD\s?)\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?")
STOCK_RE = re.compile(r"\b(in stock|out of stock|sold out|available now|backorder|back-order|pre-?order)\b", re.I)
STOCK_OUT_RE = re.compile(r"\b(out of stock|sold out)\b", re.I)
FILENAME_ALT_RE = re.compile(r"\.(jpe?g|png|gif|webp|svg|heic)$|^(img|image|dsc|photo|pic)[-_ ]?\d+", re.I)
GENERIC_ALT = {"image", "photo", "picture", "product", "product image", "thumbnail", "img"}
BUY_RE = re.compile(r"\b(buy|add to (cart|bag|basket)|checkout|check out|purchase|order now)\b", re.I)
JSONLD_REQUIRED = ("name", "offers.price", "offers.priceCurrency", "offers.availability")


@dataclass
class Outcome:
    key: str
    passed: bool
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)
    code: str | None = None  # failure type (failures.FAILURE_TYPES); None when passed


def is_product_page(facts: dict[str, Any], target: str) -> bool:
    return target.lower() in (facts.get("title") or "").lower()


def is_checkout_page(facts: dict[str, Any]) -> bool:
    return bool(facts.get("has_payment_button")) or (facts.get("title") or "").lower().startswith("checkout")


def _products_in_jsonld(blocks: list[Any]) -> list[dict[str, Any]]:
    found = []
    stack = list(blocks)
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, dict):
            types = item.get("@type")
            types = types if isinstance(types, list) else [types]
            if "Product" in types:
                found.append(item)
            stack.extend(v for k, v in item.items() if k == "@graph")
    return found


def _get(obj: dict[str, Any], dotted: str) -> Any:
    for part in dotted.split("."):
        if isinstance(obj, list):
            obj = obj[0] if obj else None
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    return obj


def evaluate_product_page(facts: dict[str, Any]) -> list[Outcome]:
    url = facts.get("url")
    text = facts.get("main_text") or ""
    controls = facts.get("controls") or []
    products = _products_in_jsonld(facts.get("jsonld") or [])
    product = products[0] if products else None
    out: list[Outcome] = []

    # Price as text, in the main content (header/footer banners like "free shipping over $50" don't count).
    prices = text_prices(facts)
    if prices:
        p = prices[0]
        out.append(Outcome("price_in_text", True, f"Price text found: {p['text']}",
                           {"url": url, "snippet": p["text"], "selector": p.get("selector")}))
    else:
        imgs = facts.get("images_without_alt") or []
        reason = "No price text in the main content."
        if imgs:
            reason += f" {len(imgs)} image(s) without alt text may contain it."
        out.append(Outcome("price_in_text", False, reason,
                           {"url": url, "selector": imgs[0]["selector"] if imgs else "main", "images_without_alt": imgs[:5]},
                           "price_image_only" if imgs else "price_missing"))

    # Structured data.
    if product is None:
        out.append(Outcome("structured_data", False, "No schema.org Product JSON-LD on the page.",
                           {"url": url, "selector": 'script[type="application/ld+json"]', "jsonld_blocks": len(facts.get("jsonld") or [])},
                           "jsonld_missing"))
    else:
        missing = [f for f in JSONLD_REQUIRED if _get(product, f) in (None, "")]
        if missing:
            out.append(Outcome("structured_data", False, f"Product JSON-LD is missing: {', '.join(missing)}.",
                               {"url": url, "selector": 'script[type="application/ld+json"]', "missing": missing},
                               "jsonld_incomplete"))
        else:
            out.append(Outcome("structured_data", True, "Product JSON-LD has name, price, currency and availability.",
                               {"url": url, "price": _get(product, "offers.price"), "currency": _get(product, "offers.priceCurrency")}))

    # Stock status, in text or structured data.
    availability = _get(product, "offers.availability") if product else None
    sm = STOCK_RE.search(text)
    if availability or sm:
        source = f"JSON-LD availability {availability}" if availability else f"text '{sm.group(0)}'"
        out.append(Outcome("stock_readable", True, f"Stock status readable from {source}.", {"url": url}))
    else:
        out.append(Outcome("stock_readable", False, "No stock status in text or structured data.",
                           {"url": url, "selector": "main"}, "stock_missing"))

    # One clear, semantic buy control.
    semantic_buy = [c for c in controls if c.get("semantic") and BUY_RE.search(c.get("text") or "")]
    if semantic_buy:
        c = semantic_buy[0]
        out.append(Outcome("clear_buy_button", True, f"Semantic <{c['tag']}> labelled '{c['text']}'.",
                           {"url": url, "selector": c.get("selector")}))
    else:
        fake = [c for c in controls if not c.get("semantic")]
        reason = "No button or link with a buy label (Buy, Add to cart, Checkout)."
        if fake:
            labels = ", ".join(f"'{c.get('text')}'" for c in fake[:6])
            reason += f" Found {len(fake)} non-semantic clickable element(s) with unclear labels: {labels}."
        out.append(Outcome("clear_buy_button", False, reason,
                           {"url": url, "selector": fake[0]["selector"] if fake else None,
                            "non_semantic_controls": [{"selector": c.get("selector"), "text": c.get("text")} for c in fake[:6]]},
                           "buy_button_nonsemantic" if fake else "buy_button_missing"))

    out += _currency(facts, prices, product)
    out += _stock_consistency(facts, product)
    out += _image_alt(facts)
    out += _sale_claim(facts, prices, product)
    out += _obstruction(facts)
    return out


def text_prices(facts: dict[str, Any]) -> list[dict[str, Any]]:
    """Non-struck prices shown as text in <main>, in page order. Falls back to a regex over main_text."""
    if "prices" in facts:
        return list(facts["prices"] or [])
    return [{"text": m.group(0), "value": m.group(0).lstrip("$USD ").replace(",", ""), "currency": True}
            for m in PRICE_RE.finditer(facts.get("main_text") or "")]


def _dec(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value not in (None, "") else None
    except InvalidOperation:
        return None


def _currency(facts, prices, product) -> list[Outcome]:
    url = facts.get("url")
    ld_price = _get(product, "offers.price") if product else None
    if not prices and ld_price in (None, ""):
        return []  # no readable price anywhere: nothing to judge (price_in_text already failed)
    bare = [p for p in prices if not p.get("currency")]
    ld_missing = ld_price not in (None, "") and not _get(product, "offers.priceCurrency")
    if bare or ld_missing:
        where = []
        if bare:
            where.append(f"page text shows '{bare[0]['text']}'")
        if ld_missing:
            where.append("JSON-LD offers.priceCurrency is missing")
        return [Outcome("currency_stated", False, "The price has no currency: " + " and ".join(where) + ".",
                        {"url": url, "selector": bare[0].get("selector") if bare else 'script[type="application/ld+json"]'},
                        "currency_missing")]
    return [Outcome("currency_stated", True, "Every readable price states its currency.", {"url": url})]


def _stock_consistency(facts, product) -> list[Outcome]:
    url = facts.get("url")
    availability = str(_get(product, "offers.availability") or "") if product else ""
    says_out = bool(STOCK_OUT_RE.search(facts.get("main_text") or "")) or availability.endswith("OutOfStock")
    buy = [c for c in facts.get("controls") or [] if c.get("in_main", True)
           and ((c.get("semantic") and BUY_RE.search(c.get("text") or "")) or not c.get("semantic"))]
    if says_out and buy:
        return [Outcome("stock_consistent", False,
                        f"The page says the item is out of stock but still offers '{buy[0].get('text')}'.",
                        {"url": url, "selector": buy[0].get("selector"), "availability": availability or None},
                        "oos_still_buyable")]
    return [Outcome("stock_consistent", True, "Stock status and buy options agree.", {"url": url})]


def _image_alt(facts) -> list[Outcome]:
    url = facts.get("url")
    bad = [i for i in facts.get("images") or [] if not _good_alt(i.get("alt"))]
    if bad:
        return [Outcome("image_alt_text", False,
                        f"Product photo alt text is {bad[0].get('alt')!r}, which does not describe the product.",
                        {"url": url, "selector": bad[0].get("selector"), "alt": bad[0].get("alt"), "src": bad[0].get("src")},
                        "image_alt_missing")]
    return [Outcome("image_alt_text", True, "Product photos have descriptive alt text.", {"url": url})]


def _good_alt(alt: str | None) -> bool:
    a = (alt or "").strip()
    return bool(a) and not FILENAME_ALT_RE.search(a) and a.lower() not in GENERIC_ALT


def _sale_claim(facts, prices, product) -> list[Outcome]:
    url = facts.get("url")
    struck = facts.get("struck_prices") or []
    pct = facts.get("sale_percent")
    if not struck and pct is None:
        return [Outcome("sale_claim_consistent", True, "No sale claims to check.", {"url": url})]
    was = _dec(struck[0]["value"]) if struck else None
    now = _dec(prices[0]["value"]) if prices else _dec(_get(product, "offers.price") if product else None)
    if was is None or now is None:
        return []  # a claim we can't check (current price unreadable): left untested
    evidence = {"url": url, "selector": struck[0].get("selector") if struck else None,
                "was": str(was), "now": str(now), "claimed_percent_off": pct}
    if was <= now:
        return [Outcome("sale_claim_consistent", False, f"'Was' price {was} is not higher than the current price {now}.",
                        evidence, "sale_claim_misleading")]
    actual = (was - now) / was * 100
    evidence["actual_percent_off"] = float(actual.quantize(Decimal("0.1")))
    if pct is not None and abs(actual - Decimal(pct)) > 1:
        return [Outcome("sale_claim_consistent", False,
                        f"Claims {pct}% off, but {was} -> {now} is {actual:.1f}% off.", evidence, "sale_claim_misleading")]
    return [Outcome("sale_claim_consistent", True, f"Sale claim adds up ({was} -> {now}).", evidence)]


def _obstruction(facts) -> list[Outcome]:
    url = facts.get("url")
    controls = [c for c in facts.get("controls") or [] if c.get("in_main", True)]
    candidates = [c for c in controls if c.get("semantic") and BUY_RE.search(c.get("text") or "")] or \
                 [c for c in controls if not c.get("semantic")]
    if not candidates:
        return []  # no buy control at all: clear_buy_button already failed
    covered = [c for c in candidates if c.get("covered")]
    if covered:
        c = covered[0]
        return [Outcome("buy_button_unobstructed", False,
                        f"'{c.get('text')}' is covered by {c.get('covered_by')}, so it can't be clicked.",
                        {"url": url, "selector": c.get("selector"), "covered_by": c.get("covered_by")},
                        "buy_button_covered")]
    return [Outcome("buy_button_unobstructed", True, "The buy control is not covered.", {"url": url})]


def evaluate_checkout_prices(facts: dict[str, Any], product_price: Decimal | None) -> list[Outcome]:
    """The item price at checkout must equal the product page price. Untested if either isn't text."""
    prices = text_prices(facts)
    checkout_price = _dec(prices[0]["value"]) if prices else None
    if product_price is None or checkout_price is None:
        return []
    url = facts.get("url")
    if checkout_price != product_price:
        return [Outcome("price_consistent", False,
                        f"Product page shows {product_price} but checkout shows {checkout_price}.",
                        {"url": url, "selector": prices[0].get("selector"), "product_price": str(product_price),
                         "checkout_price": str(checkout_price)}, "price_changed_at_checkout")]
    return [Outcome("price_consistent", True, f"Checkout shows the same price ({checkout_price}).", {"url": url})]


def first_price(facts: dict[str, Any]) -> Decimal | None:
    prices = text_prices(facts)
    return _dec(prices[0]["value"]) if prices else None


def evaluate_path_to_checkout(checkout_url: str, form_pages: list[dict[str, Any]]) -> Outcome:
    """form_pages: forms the agent had to submit between the product page and checkout."""
    if not form_pages:
        return Outcome("no_extra_steps", True, "Checkout reached directly from the product page.", {"url": checkout_url})
    first = form_pages[0]
    fields = ", ".join(first.get("fields") or [])
    return Outcome(
        "no_extra_steps",
        False,
        f"{len(form_pages)} form step(s) before payment; first at {first.get('url')} (fields: {fields}).",
        {"url": first.get("url"), "selector": first.get("selector"), "form_pages": form_pages},
        "extra_form_step",
    )
