"""The shopping.* tool contract PayPal's WebMCP showcase registers, and how tool names reach the LLM."""

import re

SEARCH, GET_PRODUCT, INITIATE, COMPLETE = (
    "shopping.searchProducts", "shopping.getProduct", "shopping.initiateCheckout", "shopping.completeCheckout")
SHOPPING_TOOLS = (SEARCH, GET_PRODUCT, INITIATE, COMPLETE)
PAYPAL_SHOWCASE_URL = "https://webmcp-store.paypal.com/merchants/gift-cards?sdk=v6"

_UNSAFE = re.compile(r"[^A-Za-z0-9_-]")


def function_names(tool_names: list[str]) -> dict[str, str]:
    """tool name -> a name every LLM provider accepts as a function name (`shopping.searchProducts` ->
    `shopping__searchProducts`). Two tools never share one."""
    mapping: dict[str, str] = {}
    for name in tool_names:
        safe = _UNSAFE.sub("__", name)[:64] or "tool"
        while safe in mapping.values():
            safe = f"{safe[:60]}_{len(mapping)}"
        mapping[name] = safe
    return mapping
