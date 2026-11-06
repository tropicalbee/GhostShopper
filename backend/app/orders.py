"""Orders v2 endpoints the demo store's PayPal button calls: create and capture."""

import json
import re
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from store import catalog
from store.flaws import FlawStore

from . import db
from .paypal import PayPalClient, PayPalError, summarize_capture
from .ratelimit import rate_limit
from .verification import verify_payment

router = APIRouter(prefix="/api/paypal", tags=["paypal"])

ORDER_ID_RE = re.compile(r"^[A-Z0-9]{5,40}$")


class CreateOrderRequest(BaseModel):
    sku: str
    quantity: int = Field(default=1, ge=1, le=10)


def get_paypal(request: Request) -> PayPalClient:
    client = request.app.state.paypal
    if client is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "PAYPAL_NOT_CONFIGURED", "message": "Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in .env"},
        )
    return client


def _paypal_http_error(exc: PayPalError) -> HTTPException:
    # Pass PayPal's validation errors (e.g. INSTRUMENT_DECLINED) through as 422; anything else is upstream failure.
    status = 422 if exc.status_code == 422 else 502
    return HTTPException(
        status_code=status,
        detail={"error": exc.name, "issue": exc.issue, "debug_id": exc.debug_id, "message": str(exc)},
    )


def build_purchase_unit(product: catalog.Product, quantity: int, unit_price: Decimal | None = None) -> dict[str, Any]:
    unit = product.price if unit_price is None else unit_price
    total = f"{unit * quantity:.2f}"
    return {
        "reference_id": product.sku,
        "description": f"Fernhill Ceramics: {product.name}",
        "items": [
            {
                "name": product.name,
                "sku": product.sku,
                "quantity": str(quantity),
                "category": "PHYSICAL_GOODS",
                "unit_amount": {"currency_code": product.currency, "value": f"{unit:.2f}"},
            }
        ],
        "amount": {
            "currency_code": product.currency,
            "value": total,
            "breakdown": {"item_total": {"currency_code": product.currency, "value": total}},
        },
    }


@router.post("/orders", status_code=201)
async def create_order(body: CreateOrderRequest, request: Request, paypal: PayPalClient = Depends(get_paypal)):
    rate_limit(request, "api_limiter")  # each call creates a PayPal sandbox order
    product = catalog.get_by_sku(body.sku)
    if product is None:
        raise HTTPException(status_code=404, detail={"error": "UNKNOWN_SKU", "message": f"No product {body.sku}"})
    # The store's own (possibly flawed) pricing: the price_mismatch flaw charges more than advertised.
    flaws = FlawStore(request.app.state.settings.database_path).get_all()
    if not product.in_stock and not flaws.get("oos_buyable"):
        raise HTTPException(status_code=409, detail={"error": "OUT_OF_STOCK", "message": f"{product.name} is sold out"})

    unit = build_purchase_unit(product, body.quantity, catalog.charged_unit_price(product, flaws))
    try:
        order = await paypal.create_order(unit)
    except PayPalError as exc:
        raise _paypal_http_error(exc) from exc

    db.insert_order(
        request.app.state.settings.database_path,
        order_id=order["id"],
        sku=product.sku,
        quantity=body.quantity,
        currency=product.currency,
        amount=unit["amount"]["value"],
        status=order["status"],
    )
    return {"id": order["id"], "status": order["status"], "amount": unit["amount"]["value"], "currency": product.currency}


@router.post("/orders/{order_id}/capture")
async def capture_order(order_id: str, request: Request, paypal: PayPalClient = Depends(get_paypal)):
    if not ORDER_ID_RE.match(order_id):
        raise HTTPException(status_code=400, detail={"error": "BAD_ORDER_ID", "message": "Malformed order id"})
    db_path = request.app.state.settings.database_path
    if db.get_order(db_path, order_id) is None:
        raise HTTPException(status_code=404, detail={"error": "UNKNOWN_ORDER", "message": "Order was not created here"})

    try:
        result = await paypal.capture_order(order_id)
    except PayPalError as exc:
        raise _paypal_http_error(exc) from exc

    summary = summarize_capture(result)
    db.record_capture(db_path, order_id, summary, result)
    return summary


def _owned_by(db_path, run_id: int | None, owner: str) -> bool:
    if run_id is None:
        return False
    with db.connect(db_path) as conn:
        row = conn.execute("SELECT owner_hash FROM runs WHERE id = ?", (run_id,)).fetchone()
    return row is not None and row["owner_hash"] == owner


@router.post("/orders/{order_id}/refund")
async def refund_order(order_id: str, request: Request, paypal: PayPalClient = Depends(get_paypal)):
    """Give the sandbox payment back in full, then read the refund from PayPal and check it. Not part of the score."""
    rate_limit(request, "api_limiter")  # each call costs PayPal requests
    if not ORDER_ID_RE.match(order_id):
        raise HTTPException(status_code=400, detail={"error": "BAD_ORDER_ID", "message": "Malformed order id"})
    db_path = request.app.state.settings.database_path
    order = db.get_order(db_path, order_id)
    if order is None or not _owned_by(db_path, order["run_id"], request.state.owner):
        # Only the browser that ran the check may refund; shared examples and other browsers' orders look unknown.
        raise HTTPException(status_code=404, detail={"error": "UNKNOWN_ORDER", "message": "No such order"})
    if not order["capture_id"] or order["capture_status"] != "COMPLETED":
        raise HTTPException(status_code=409, detail={"error": "NOT_CAPTURED", "message": "This order has no completed payment to refund"})
    if order["refund_id"]:
        raise HTTPException(status_code=409, detail={"error": "ALREADY_REFUNDED", "message": "This order was already refunded"})

    try:
        issued = await paypal.refund_capture(order["capture_id"])
        refund = await paypal.get_refund(issued["id"])
    except PayPalError as exc:
        raise _paypal_http_error(exc) from exc

    db.record_refund(db_path, order_id, refund)
    amount, currency = refund["amount"]["value"], refund["amount"]["currency_code"]
    captured = order["gross_amount"] or order["amount"]
    mismatches = []
    if refund["status"] != "COMPLETED":
        mismatches.append(f"Refund status is {refund['status']}, expected COMPLETED")
    if Decimal(amount) != Decimal(captured):
        mismatches.append(f"Refunded {amount}, but {captured} was captured")
    if currency != order["currency"]:
        mismatches.append(f"Refund currency is {currency}, expected {order['currency']}")
    return {
        "order_id": order_id,
        "refund_id": refund["id"],
        "status": refund["status"],
        "amount": amount,
        "currency": currency,
        "verified": not mismatches,
        "mismatches": mismatches,
    }


@router.get("/orders/{order_id}/verify")
def verify_order(order_id: str, request: Request):
    """Order <-> capture <-> advertised amount <-> fees. Used by the agent after a purchase."""
    db_path = request.app.state.settings.database_path
    order = db.get_order(db_path, order_id, include_raw=True)
    if order is None:
        raise HTTPException(status_code=404, detail={"error": "UNKNOWN_ORDER", "message": "No such order"})
    product = catalog.get_by_sku(order["sku"])
    if product is None:
        raise HTTPException(status_code=404, detail={"error": "UNKNOWN_SKU", "message": order["sku"]})
    raw = json.loads(order["capture_response"]) if order.get("capture_response") else None
    return verify_payment(order, raw, product.price, product.currency)


@router.get("/orders/{order_id}")
def get_order(order_id: str, request: Request):
    order = db.get_order(request.app.state.settings.database_path, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail={"error": "UNKNOWN_ORDER", "message": "No such order"})
    return order
