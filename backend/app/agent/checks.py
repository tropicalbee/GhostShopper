"""Deterministic detectors: page facts (collected from the live DOM) -> check outcomes.

Pure functions, no browser and no LLM, so they are unit-testable and the score stays reproducible.
"""

import re
from dataclasses import dataclass, field
from typing import Any

PRICE_RE = re.compile(r"(?:\$|USD\s?)\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?")
STOCK_RE = re.compile(r"\b(in stock|out of stock|sold out|available now|backorder|back-order|pre-?order)\b", re.I)
BUY_RE = re.compile(r"\b(buy|add to (cart|bag|basket)|checkout|check out|purchase|order now)\b", re.I)
JSONLD_REQUIRED = ("name", "offers.price", "offers.priceCurrency", "offers.availability")


@dataclass
class Outcome:
    key: str
    passed: bool
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)


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
    m = PRICE_RE.search(text)
    if m:
        out.append(Outcome("price_in_text", True, f"Price text found: {m.group(0)}", {"url": url, "snippet": m.group(0)}))
    else:
        imgs = facts.get("images_without_alt") or []
        reason = "No price text in the main content."
        if imgs:
            reason += f" {len(imgs)} image(s) without alt text may contain it."
        out.append(Outcome("price_in_text", False, reason,
                           {"url": url, "selector": imgs[0]["selector"] if imgs else "main", "images_without_alt": imgs[:5]}))

    # Structured data.
    if product is None:
        out.append(Outcome("structured_data", False, "No schema.org Product JSON-LD on the page.",
                           {"url": url, "selector": 'script[type="application/ld+json"]', "jsonld_blocks": len(facts.get("jsonld") or [])}))
    else:
        missing = [f for f in JSONLD_REQUIRED if _get(product, f) in (None, "")]
        if missing:
            out.append(Outcome("structured_data", False, f"Product JSON-LD is missing: {', '.join(missing)}.",
                               {"url": url, "selector": 'script[type="application/ld+json"]', "missing": missing}))
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
        out.append(Outcome("stock_readable", False, "No stock status in text or structured data.", {"url": url, "selector": "main"}))

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
                            "non_semantic_controls": [{"selector": c.get("selector"), "text": c.get("text")} for c in fake[:6]]}))
    return out


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
    )
