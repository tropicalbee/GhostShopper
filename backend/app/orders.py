"""Orders v2 endpoints the demo store's PayPal button calls: create and capture."""

import json
import logging
import re
from decimal import Decimal
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from store import catalog
from store.flaws import FlawStore
from store.orders import StoreOrders

from . import db
from .agent.recorder import invalidate_run
from .failures import BUYER_SIDE_CAPTURE_ISSUES
from .paypal import PayPalClient, PayPalError, summarize_capture
from .ratelimit import rate_limit
from .verification import verify_payment

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/paypal", tags=["paypal"])

ORDER_ID_RE = re.compile(r"^[A-Z0-9]{5,40}$")


class CreateOrderRequest(BaseModel):
    sku: str
    quantity: int = Field(default=1, ge=1, le=10)


class BrowserOrderRequest(CreateOrderRequest):
    store_order: int | None = Field(default=None, ge=1)  # set when the buyer pays again after a failed attempt


def get_paypal(request: Request) -> PayPalClient:
    state = request.app.state
    client = state.paypal_clients.get(state.paypal_active)
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


def _refund_unavailable(refund_id: str | None, code: str, what: str) -> HTTPException:
    message = f"{what}. "
    message += ("The refund was issued and recorded; try again to confirm it." if refund_id else "No refund was issued; try again.")
    return HTTPException(status_code=502, detail={"error": code, "message": message})


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


def _purchase_unit_for(body: CreateOrderRequest, request: Request) -> tuple[catalog.Product, dict[str, Any], dict[str, bool]]:
    product = catalog.get_by_sku(body.sku)
    if product is None:
        raise HTTPException(status_code=404, detail={"error": "UNKNOWN_SKU", "message": f"No product {body.sku}"})
    # The store's own (possibly flawed) pricing: the price_mismatch flaw charges more than advertised.
    flaws = FlawStore(request.app.state.settings.database_path).get_all()
    if not product.in_stock and not flaws.get("oos_buyable"):
        raise HTTPException(status_code=409, detail={"error": "OUT_OF_STOCK", "message": f"{product.name} is sold out"})
    return product, build_purchase_unit(product, body.quantity, catalog.charged_unit_price(product, flaws)), flaws


async def _read_back_order(paypal: PayPalClient, db_path, order_id: str) -> None:
    """Keep PayPal's own view of the order for the purchase trace. A failed read leaves it unknown; it never
    blocks or changes the payment."""
    try:
        db.record_order_snapshot(db_path, order_id, await paypal.get_order(order_id))
    except (PayPalError, httpx.HTTPError) as exc:
        log.warning("could not read PayPal order %s back: %s", order_id, getattr(exc, "name", type(exc).__name__))


@router.post("/orders", status_code=201)
async def create_order(body: BrowserOrderRequest, request: Request, paypal: PayPalClient = Depends(get_paypal)):
    rate_limit(request, "api_limiter")  # each call creates a PayPal sandbox order
    product, unit, flaws = _purchase_unit_for(body, request)
    db_path = request.app.state.settings.database_path
    # The store's order exists before PayPal's, and its number travels in custom_id: PayPal echoes it back, so the
    # purchase trace can prove both records are the same purchase without comparing amounts.
    store = StoreOrders(db_path)
    store_order = store.open(sku=product.sku, quantity=body.quantity, amount=unit["amount"]["value"],
                             currency=product.currency, retry_of=body.store_order, flaws=flaws)
    unit["custom_id"] = str(store_order["number"])
    try:
        order = await paypal.create_order(unit)
    except PayPalError as exc:
        failure = _paypal_http_error(exc)
        failure.detail["store_order"] = store_order["number"]  # stays awaiting payment: nothing was charged
        raise failure from exc

    db.insert_order(
        db_path,
        order_id=order["id"],
        sku=product.sku,
        quantity=body.quantity,
        currency=product.currency,
        amount=unit["amount"]["value"],
        status=order["status"],
    )
    store.attach_paypal(store_order["number"], order["id"])
    return {"id": order["id"], "status": order["status"], "amount": unit["amount"]["value"],
            "currency": product.currency, "store_order": store_order["number"]}


class AgentOrderRequest(CreateOrderRequest):
    """Agent payment: the buyer approved PayPal once and saved it (Vault), so no popup or password is involved."""

    vault_id: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    request_id: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")  # PayPal-Request-Id
    max_amount: str | None = None  # the shopper's spending limit; checked before PayPal is called


@router.post("/agent-orders", status_code=201)
async def create_agent_order(body: AgentOrderRequest, request: Request, paypal: PayPalClient = Depends(get_paypal)):
    """The store accepts an agent payment: create the order paid with a saved PayPal token, capture it if PayPal did
    not already, and record it like a popup purchase. Orders v2 with payment_source.paypal.vault_id; see
    https://developer.paypal.com/docs/api/orders/v2/ (PayPalWalletRequest.vault_id)."""
    from .runs import real_payment_allowed  # local import: runs imports this module's siblings

    state = request.app.state
    if state.paypal_active == "sandbox" and not real_payment_allowed(request):
        # Same gate as real sandbox runs: a deployed server needs the presenter unlock (/store/admin cookie).
        raise HTTPException(status_code=403, detail={
            "error": "REAL_PAYMENT_LOCKED", "message": "Real PayPal sandbox payments need the presenter unlock."})
    rate_limit(request, "api_limiter")  # each call can move sandbox money
    if FlawStore(state.settings.database_path).get_all().get("no_guest_checkout"):
        # The store's checkout is behind an account wall; an agent payment must not skip it.
        raise HTTPException(status_code=403, detail={
            "error": "ACCOUNT_REQUIRED", "message": "Checkout requires creating an account; nothing was charged."})
    product, unit, flaws = _purchase_unit_for(body, request)
    amount = unit["amount"]["value"]
    if body.max_amount is not None and Decimal(amount) > Decimal(body.max_amount):
        raise HTTPException(status_code=409, detail={
            "error": "OVER_BUDGET", "amount": amount,
            "message": f"The order total {amount} is over the spending limit {body.max_amount}; nothing was charged"})
    db_path = request.app.state.settings.database_path
    store = StoreOrders(db_path)
    # One store order per request id: a repeated PayPal-Request-Id answers with the same PayPal order (and the
    # custom_id it was first created with), so it must find the same store order.
    number = store.open(sku=product.sku, quantity=body.quantity, amount=amount, currency=product.currency,
                        retry_of=None, flaws=flaws, request_id=body.request_id)["number"]
    unit["custom_id"] = str(number)
    try:
        result = await paypal.create_vaulted_order(unit, body.vault_id, body.request_id)
        store.attach_paypal(number, result["id"])
        if not result.get("purchase_units", [{}])[0].get("payments", {}).get("captures"):
            # Not paid yet: capture it (stable PayPal-Request-Id, so a retry cannot capture twice).
            if db.get_order(db_path, result["id"]) is None:
                db.insert_order(db_path, order_id=result["id"], sku=product.sku, quantity=body.quantity,
                                currency=product.currency, amount=amount, status=result.get("status", "CREATED"))
            result = await paypal.capture_order(result["id"])
    except PayPalError as exc:
        log.warning("agent order failed: %s (debug_id=%s)", exc.name, exc.debug_id)  # never log the body: it may echo the token
        if exc.status_code == 422 and exc.issue in BUYER_SIDE_CAPTURE_ISSUES:
            store.settle(number, "declined", flaws)
        failure = _paypal_http_error(exc)
        failure.detail["store_order"] = number
        raise failure from exc
    if db.get_order(db_path, result["id"]) is None:
        db.insert_order(db_path, order_id=result["id"], sku=product.sku, quantity=body.quantity,
                        currency=product.currency, amount=amount, status=result.get("status", "COMPLETED"))
    try:
        summary = summarize_capture(result)
    except (KeyError, IndexError, TypeError) as exc:
        raise HTTPException(status_code=502, detail={"error": "PAYPAL_BAD_RESPONSE",
                                                     "message": "PayPal sent a response we could not read"}) from exc
    db.record_capture(db_path, result["id"], summary, result)
    await _read_back_order(paypal, db_path, result["id"])
    store.settle(number, "captured", flaws, summary["capture_id"])
    return {**summary, "id": result["id"], "status": summary["order_status"], "amount": amount,
            "currency": product.currency, "store_order": number}


# Where PayPal sends the buyer after the one-time vault approval (python -m backend.app.vault setup).
@router.get("/vault/return")
def vault_return():
    return {"message": "PayPal approved. Now run: python -m backend.app.vault finish <setup token id>"}


@router.get("/vault/cancel")
def vault_cancel():
    return {"message": "The PayPal approval was cancelled. Run python -m backend.app.vault setup again."}


@router.post("/orders/{order_id}/capture")
async def capture_order(order_id: str, request: Request, paypal: PayPalClient = Depends(get_paypal)):
    if not ORDER_ID_RE.match(order_id):
        raise HTTPException(status_code=400, detail={"error": "BAD_ORDER_ID", "message": "Malformed order id"})
    db_path = request.app.state.settings.database_path
    if db.get_order(db_path, order_id) is None:
        raise HTTPException(status_code=404, detail={"error": "UNKNOWN_ORDER", "message": "Order was not created here"})

    store = StoreOrders(db_path)
    store_order = store.for_paypal_order(order_id)
    flaws = FlawStore(db_path).get_all()
    try:
        result = await paypal.capture_order(order_id)
    except PayPalError as exc:
        db.record_capture_failure(db_path, order_id, exc.issue or exc.name)
        await _read_back_order(paypal, db_path, order_id)
        if store_order and exc.status_code == 422 and exc.issue in BUYER_SIDE_CAPTURE_ISSUES:
            settled = store.settle(store_order["number"], "declined", flaws)
            if settled["status"] == "paid":  # the declined_marked_paid flaw: the buyer is told it worked
                return {"order_id": order_id, "capture_id": None, "store_order": settled["number"]}
        raise _paypal_http_error(exc) from exc

    summary = summarize_capture(result)
    db.record_capture(db_path, order_id, summary, result)
    await _read_back_order(paypal, db_path, order_id)
    if store_order:
        store.settle(store_order["number"], "captured", flaws, summary["capture_id"])
    return {**summary, "store_order": store_order["number"] if store_order else None}


@router.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: str, request: Request, paypal: PayPalClient = Depends(get_paypal)):
    """The buyer closed PayPal's window without paying. The store records the cancellation (or, with the
    success_after_cancel flaw, confirms the order anyway)."""
    if not ORDER_ID_RE.match(order_id):
        raise HTTPException(status_code=400, detail={"error": "BAD_ORDER_ID", "message": "Malformed order id"})
    db_path = request.app.state.settings.database_path
    store = StoreOrders(db_path)
    store_order = store.for_paypal_order(order_id)
    if store_order is None:
        raise HTTPException(status_code=404, detail={"error": "UNKNOWN_ORDER", "message": "Order was not created here"})
    if store_order["status"] == "awaiting_payment":
        await _read_back_order(paypal, db_path, order_id)
        store_order = store.settle(store_order["number"], "cancelled", FlawStore(db_path).get_all())
    return {"store_order": store_order["number"], "status": store_order["status"]}


def _owned_by(db_path, run_id: int | None, owner: str) -> bool:
    if run_id is None:
        return False
    with db.connect(db_path) as conn:
        row = conn.execute("SELECT owner_hash FROM runs WHERE id = ?", (run_id,)).fetchone()
    return row is not None and row["owner_hash"] == owner


@router.post("/orders/{order_id}/refund")
async def refund_order(order_id: str, request: Request):
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
    # An issued refund that is not yet confirmed complete (get_refund failed, or PayPal said pending) is retried by
    # reading it again, not by refunding twice.
    resume = bool(order["refund_id"]) and (order["refund_amount"] is None or order["refund_status"] != "COMPLETED")
    if order["refund_id"] and not resume:
        raise HTTPException(status_code=409, detail={"error": "ALREADY_REFUNDED", "message": "This order was already refunded"})

    # The payment lives with the PayPal the run used, which may not be the mode that is active now.
    with db.connect(db_path) as conn:
        run_mode = conn.execute("SELECT paypal_mode FROM runs WHERE id = ?", (order["run_id"],)).fetchone()["paypal_mode"]
    paypal = request.app.state.paypal_clients.get(run_mode)
    if paypal is None:
        raise HTTPException(status_code=503, detail={"error": "PAYPAL_NOT_CONFIGURED", "message": "Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in .env"})
    refund_id = order["refund_id"] if resume else None
    try:
        if not resume:
            issued = await paypal.refund_capture(order["capture_id"])
            refund_id = issued["id"]
            # Keep the id (and whatever status PayPal gave) before reading it back, so a failure below loses nothing.
            db.record_refund(db_path, order_id, issued)
            invalidate_run(db_path, order["run_id"])
        refund = await paypal.get_refund(refund_id)
        refund["id"], refund["status"], refund["amount"]["value"], refund["amount"]["currency_code"]  # shape check
    except PayPalError as exc:
        log.warning("refund failed for order %s: %s (debug_id=%s)", order_id, exc.name, exc.debug_id)
        raise _paypal_http_error(exc) from exc
    except httpx.HTTPError as exc:
        log.warning("refund request failed for order %s: %s", order_id, type(exc).__name__)
        raise _refund_unavailable(refund_id, "PAYPAL_UNREACHABLE", "Could not reach PayPal") from exc
    except (KeyError, TypeError, IndexError) as exc:
        log.warning("refund response for order %s was malformed: %r", order_id, exc)
        raise _refund_unavailable(refund_id, "PAYPAL_BAD_RESPONSE", "PayPal sent a response we could not read") from exc

    db.record_refund(db_path, order_id, refund)
    log.info("refunded order %s: refund %s %s", order_id, refund["id"], refund["status"])
    invalidate_run(db_path, order["run_id"])  # a finished run's cached payload carries its order
    refunded_at = db.get_order(db_path, order_id)["refunded_at"]
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
        "refunded_at": refunded_at,
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
