"""Which shop platform a store runs on, from signals on its pages. Pure and deterministic."""

from typing import Any

PLATFORMS = ("shopify", "wix", "woocommerce", "unknown")
NAMES = {"shopify": "Shopify", "wix": "Wix", "woocommerce": "WooCommerce", "unknown": "your shop's platform"}


def detect_platform(signals: dict[str, Any]) -> dict[str, Any]:
    """signals: generator (meta content), scripts / links (URLs), body_class, globals (window names)."""
    generator = (signals.get("generator") or "").lower()
    urls = " ".join((signals.get("scripts") or []) + (signals.get("links") or [])).lower()
    body = (signals.get("body_class") or "").lower()
    globals_ = set(signals.get("globals") or [])
    hits: dict[str, list[str]] = {"shopify": [], "wix": [], "woocommerce": []}

    if "Shopify" in globals_:
        hits["shopify"].append("window.Shopify is defined")
    if "cdn.shopify.com" in urls or "myshopify.com" in urls:
        hits["shopify"].append("loads files from Shopify's CDN")
    if "shopify" in generator:
        hits["shopify"].append(f"generator: {signals.get('generator')}")

    if "wix.com" in generator:
        hits["wix"].append(f"generator: {signals.get('generator')}")
    if "static.wixstatic.com" in urls or "static.parastorage.com" in urls:
        hits["wix"].append("loads files from Wix's servers")

    if "woocommerce" in generator:
        hits["woocommerce"].append(f"generator: {signals.get('generator')}")
    if "/wp-content/plugins/woocommerce" in urls:
        hits["woocommerce"].append("loads the WooCommerce plugin")
    if "woocommerce" in body.split():
        hits["woocommerce"].append("page body is marked woocommerce")

    best = max(hits, key=lambda k: len(hits[k]))
    if not hits[best]:
        return {"platform": "unknown", "name": NAMES["unknown"], "evidence": []}
    return {"platform": best, "name": NAMES[best], "evidence": hits[best]}
