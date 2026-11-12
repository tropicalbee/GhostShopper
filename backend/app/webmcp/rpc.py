"""The server behind the Fernhill WebMCP adapter (store/static/webmcp.js): JSON-RPC at POST /store/webmcp/rpc.

Search and product reads come from the catalog, so the storefront's UI flaws never touch them. Checkout goes through
the same order and capture code as the store's PayPal button (orders.py), so the purchase flaws behave identically.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from store import catalog
from store.orders import StoreOrders

from ..orders import BrowserOrderRequest, capture_order, get_paypal, place_order
from .tools import COMPLETE, GET_PRODUCT, INITIATE, SEARCH

router = APIRouter(prefix="/store/webmcp", tags=["webmcp"], include_in_schema=False)

INVALID_PARAMS, METHOD_NOT_FOUND, SERVER_ERROR = -32602, -32601, -32000


class RpcError(Exception):
    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(message)
        self.code, self.message, self.data = code, message, data


class RpcCall(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    tool: str = Field(max_length=100)
    input: dict[str, Any] = Field(default_factory=dict)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchInput(Strict):
    query: str = Field(min_length=1, max_length=200)
    max_results: int = Field(default=10, ge=1, le=20)
    category: str | None = Field(default=None, max_length=100)


class ProductInput(Strict):
    product_id: str | None = Field(default=None, max_length=100)


class CheckoutInput(ProductInput):
    quantity: int = Field(default=1, ge=1, le=5)
    buyer_email: str | None = Field(default=None, max_length=200)
    requires_user_approval: bool = False


class CompleteInput(Strict):
    cart_id: str | None = Field(default=None, max_length=40)
    token: str | None = Field(default=None, max_length=100)


def _origin(request: Request) -> str:
    return f"{request.url.scheme}://{request.url.netloc}"


def _view(request: Request, product: catalog.Product) -> dict[str, Any]:
    return {"product_id": product.sku, "title": product.name, "description": product.summary,
            "price": {"value": product.price_str, "currency_code": product.currency},
            "availability": "in_stock" if product.in_stock else "out_of_stock", "category": product.category_name,
            "url": f"{_origin(request)}/store/products/{product.slug}"}


def _find(product_id: str | None) -> catalog.Product:
    if not product_id:
        raise RpcError(INVALID_PARAMS, "product_id is required (it is only optional on a product page).")
    wanted = product_id.strip()
    product = catalog.get_by_sku(wanted) or catalog.get_by_slug(wanted) or catalog.get_by_name(wanted)
    if product is None:
        raise RpcError(INVALID_PARAMS, f"No product {product_id!r}.")
    return product


async def search_products(request: Request, data: SearchInput) -> dict[str, Any]:
    words = data.query.lower().split()
    category = (data.category or "").strip().lower()
    found = []
    for p in catalog.load_products():
        text = f"{p.sku} {p.name} {p.summary} {p.category_name}".lower()
        if all(w in text for w in words) and (not category or category in (p.category, p.category_name.lower())):
            found.append(_view(request, p))
    return {"query": data.query, "products": found[:data.max_results]}


async def get_product(request: Request, data: ProductInput) -> dict[str, Any]:
    return _view(request, _find(data.product_id))


async def initiate_checkout(request: Request, data: CheckoutInput) -> dict[str, Any]:
    if data.requires_user_approval is not True:
        raise RpcError(INVALID_PARAMS, "requires_user_approval must be true: checkout opens PayPal for the buyer to approve.")
    product = _find(data.product_id)
    returned = f"{_origin(request)}/store/webmcp/return"
    source = {"paypal": {"experience_context": {"return_url": returned, "cancel_url": f"{returned}?cancelled=1",
                                                "user_action": "PAY_NOW"}}}
    order, placed = await place_order(BrowserOrderRequest(sku=product.sku, quantity=data.quantity), request,
                                      get_paypal(request), source)
    link = next((entry["href"] for entry in order.get("links", []) if entry.get("rel") in ("payer-action", "approve")), None)
    if link is None:
        raise RpcError(SERVER_ERROR, "PayPal sent no approval link for this order.", {"order_id": order["id"]})
    return {"cart_id": str(placed["store_order"]), "order_id": order["id"], "approval_url": link, "status": order["status"],
            "amount": {"value": placed["amount"], "currency_code": placed["currency"]},
            "product_id": product.sku, "quantity": data.quantity}


async def complete_checkout(request: Request, data: CompleteInput) -> dict[str, Any]:
    if not data.token:
        raise RpcError(INVALID_PARAMS, "token is required: call shopping.initiateCheckout first.")
    store_order = StoreOrders(request.app.state.settings.database_path).for_paypal_order(data.token)
    if store_order is None:
        raise RpcError(INVALID_PARAMS, "Unknown checkout token.")
    if data.cart_id and data.cart_id != str(store_order["number"]):
        raise RpcError(INVALID_PARAMS, "cart_id does not belong to this token.")
    result = await capture_order(data.token, request, get_paypal(request))
    paid = result.get("gross_amount")
    number = result["store_order"]
    return {"status": result.get("capture_status") or "COMPLETED", "order_id": data.token,
            "capture_id": result.get("capture_id"),
            "amount": {"value": paid, "currency_code": result["currency"]} if paid else None,
            "store_order_number": number, "order_url": f"{_origin(request)}/store/orders/{number}"}


TOOLS = {SEARCH: (SearchInput, search_products), GET_PRODUCT: (ProductInput, get_product),
         INITIATE: (CheckoutInput, initiate_checkout), COMPLETE: (CompleteInput, complete_checkout)}


def _failure(exc: Exception) -> RpcError:
    if isinstance(exc, RpcError):
        return exc
    if isinstance(exc, ValidationError):
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        return RpcError(INVALID_PARAMS, f"Invalid input{f' {where}' if where else ''}: {first['msg']}")
    detail = exc.detail if isinstance(exc, HTTPException) and isinstance(exc.detail, dict) else {"message": str(getattr(exc, "detail", exc))}
    return RpcError(SERVER_ERROR, detail.get("message") or detail.get("error") or "The request failed.", detail)


@router.post("/rpc")
async def rpc(call: RpcCall, request: Request):
    try:
        if call.tool not in TOOLS:
            raise RpcError(METHOD_NOT_FOUND, f"Unknown tool {call.tool!r}.")
        model, handler = TOOLS[call.tool]
        return {"jsonrpc": "2.0", "id": call.id, "result": await handler(request, model(**call.input))}
    except (RpcError, ValidationError, HTTPException) as exc:
        err = _failure(exc)
        return {"jsonrpc": "2.0", "id": call.id, "error": {"code": err.code, "message": err.message, "data": err.data}}
