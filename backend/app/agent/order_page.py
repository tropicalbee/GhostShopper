"""After a payment attempt, read the order page the demo store shows the buyer and note the status on it.

This is runtime code, not an LLM tool: the shopper does it the way a buyer would open "View your order". The status
comes from matching the store's known status phrases in the page text; no match means unknown, never a guess.
"""

from typing import Any

from playwright.async_api import Error as PlaywrightError

from store.orders import STATUS_LABELS, status_from_text

from .browser import PageTools, ToolError

BODY_TEXT_JS = "() => document.body ? document.body.innerText : ''"


async def read_order_status(tools: PageTools, store_orders: list[int]) -> tuple[dict[str, Any], str, bool] | None:
    """(step args, observation, ok) for the latest of these store orders, or None when the payment made no order."""
    if not store_orders:
        return None
    number = store_orders[-1]
    try:
        await tools.open_page(f"{tools.store_url.rstrip('/')}/orders/{number}")
        status = status_from_text(await tools.page.evaluate(BODY_TEXT_JS))
    except (ToolError, PlaywrightError) as exc:
        return {"store_order": number, "status": None}, f"Error: {str(exc).splitlines()[0][:300]}", False
    shown = f"Status: {STATUS_LABELS[status]}." if status else "No order status found on the page."
    return {"store_order": number, "status": status}, f"Opened the page for order #{number}. {shown}", True
