"""The purchase trace: five records of one purchase, compared field by field.

Stages, in the order a purchase travels: what the agent wanted, the store's own order, PayPal's order, PayPal's
capture, and what the store shows the buyer afterwards. The trace is evidence only. A value the source does not
expose is "unknown" with a reason, never a guess, and no LLM is involved. It never changes the readiness score.

build_trace is a pure function over plain dicts (see its docstring); runs.py gathers them from the database.
"""

from decimal import Decimal, InvalidOperation
from pathlib import PurePath
from typing import Any

from store.orders import STATUS_LABELS

STAGES = (
    ("agent_wanted", "What the agent wanted"),
    ("store_order", "The store's order"),
    ("paypal_order", "PayPal's order"),
    ("paypal_capture", "PayPal's capture"),
    ("store_says", "What the store says"),
)
FIELDS = ("product", "quantity", "amount", "currency", "status")
COMPARED_FIELDS = ("product", "quantity", "amount", "currency")  # checked against what the agent wanted

PAY_TOOLS = ("pay_with_paypal", "pay_with_saved_paypal")
READ_BACK_TOOL = "read_order_status"
SUCCESS = ("paid", "confirmed")  # what a store means by "your order went through"
CAPTURED = "COMPLETED"

KNOWN, UNKNOWN, NOT_APPLICABLE, NOT_REACHED = "known", "unknown", "n/a", "not_reached"

# Why a mismatch costs the merchant, and the fix. {expected} and {actual} are filled from the mismatch.
EXPLANATIONS: dict[str, tuple[str, str]] = {
    "product": (
        "The order is for {actual}, but the shopper chose {expected}. The wrong item would ship.",
        "Build the order from the product the shopper chose: pass its SKU from the product page through checkout "
        "to the PayPal order."),
    "quantity": (
        "The order has quantity {actual}, but the shopper asked for {expected}.",
        "Carry the quantity from the product page into the order and the PayPal purchase unit unchanged."),
    "amount": (
        "The amount is {actual}, but the product page advertised {expected}. The buyer pays a price they were not shown.",
        "Charge exactly the advertised price: build the PayPal order from the same price the product page shows."),
    "currency": (
        "The currency is {actual}, but the product page advertised {expected}.",
        "Use the same currency on the product page, the order and the PayPal purchase unit."),
    "success_without_payment": (
        "The store tells the buyer the order went through ({actual}), but PayPal has no completed capture. "
        "You would ship goods you were not paid for.",
        "Mark an order paid only after PayPal reports the capture COMPLETED. If the capture is declined or the buyer "
        "cancels, mark the order failed or cancelled and tell the buyer."),
    "paid_not_recorded": (
        "PayPal took the money, but the store shows the order as {actual}. The order may never ship, "
        "and the buyer may pay twice.",
        "After PayPal reports the capture COMPLETED, mark the order paid in your own records and show that status "
        "on the order page."),
    "duplicate_orders": (
        "The store created {actual} for one intended purchase. Unpaid duplicates confuse fulfilment and the buyer.",
        "When the buyer retries a payment, reuse the pending order instead of creating a new one: keep the order "
        "number in the checkout page and send it with every attempt."),
}


def _cell(kind: str, value: Any = None, reason: str | None = None) -> dict[str, Any]:
    return {"kind": kind, "value": value, "reason": reason}


def _known(value: Any) -> dict[str, Any]:
    return _cell(KNOWN, value)


def _unknown(reason: str) -> dict[str, Any]:
    return _cell(UNKNOWN, reason=reason)


def _not_reached(reason: str | None = None) -> dict[str, Any]:
    return _cell(NOT_REACHED, reason=reason)


def _stage(key: str, source: str | None, cells: dict[str, dict[str, Any]], evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"key": key, "label": dict(STAGES)[key], "source": source, "cells": {f: cells[f] for f in FIELDS},
            "evidence": evidence or {}}


def _all(cell: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {f: cell for f in FIELDS}


def _screenshot_name(step: dict[str, Any]) -> str | None:
    path = step.get("screenshot_path")
    return PurePath(path).name if path else None


def _step_evidence(step: dict[str, Any] | None) -> dict[str, Any]:
    if step is None:
        return {}
    shot = _screenshot_name(step)
    return {"step": step["idx"], **({"screenshot": shot} if shot else {})}


def _agent_wanted(run: dict[str, Any], sku: str | None, pay_step: dict[str, Any] | None) -> dict[str, Any]:
    price = run.get("catalog_price")
    cells = {
        "product": _known(sku) if sku else _unknown("the target product is not in the demo catalog"),
        "quantity": _known(1),
        "amount": _known(price["amount"]) if price else _unknown("no catalog price for this product"),
        "currency": _known(price["currency"]) if price else _unknown("no catalog price for this product"),
        "status": _known("buy"),
    }
    source = f"intent, step {pay_step['idx']}" if pay_step else "intent"
    return _stage("agent_wanted", source, cells, _step_evidence(pay_step))


def _store_order(orders: list[dict[str, Any]]) -> dict[str, Any]:
    latest = orders[-1]
    cells = {"product": _known(latest["sku"]), "quantity": _known(latest["quantity"]),
             "amount": _known(latest["amount"]), "currency": _known(latest["currency"]),
             "status": _known(latest["status"])}
    return _stage("store_order", ", ".join(f"#{o['number']}" for o in orders), cells)


def _paypal_order(paypal: dict[str, Any] | None) -> dict[str, Any]:
    if paypal is None:
        return _stage("paypal_order", None, _all(_unknown("PayPal returned no order for this purchase")))
    source = paypal["id"]
    order = paypal.get("order")
    if order is None:
        return _stage("paypal_order", source, _all(_unknown("PayPal's order was not read after payment")))
    unit = (order.get("purchase_units") or [{}])[0]
    amount = unit.get("amount") or {}
    items = unit.get("items") or []
    no_items = _unknown("store sent no item list")
    product = quantity = no_items
    if items:
        product = _known(items[0]["sku"]) if items[0].get("sku") else _unknown("store sent no SKU for the item")
        quantity = _known(int(items[0]["quantity"])) if items[0].get("quantity") else _unknown("store sent no quantity")
    cells = {
        "product": product,
        "quantity": quantity,
        "amount": _known(amount["value"]) if amount.get("value") else _unknown("PayPal's order has no amount"),
        "currency": _known(amount["currency_code"]) if amount.get("currency_code") else _unknown("PayPal's order has no currency"),
        "status": _known(order["status"]) if order.get("status") else _unknown("PayPal's order has no status"),
    }
    return _stage("paypal_order", source, cells, {"stored_response": "orders.order_response"})


def _paypal_capture(paypal: dict[str, Any] | None) -> dict[str, Any]:
    if paypal is None:
        return _stage("paypal_capture", None, _all(_not_reached()))
    na = {"product": _cell(NOT_APPLICABLE), "quantity": _cell(NOT_APPLICABLE)}
    response = paypal.get("capture")
    if response is not None:
        capture = response["purchase_units"][0]["payments"]["captures"][0]
        money = capture.get("amount") or {}
        cells = {**na,
                 "amount": _known(money["value"]) if money.get("value") else _unknown("PayPal's capture has no amount"),
                 "currency": _known(money["currency_code"]) if money.get("currency_code") else _unknown("PayPal's capture has no currency"),
                 "status": _known(capture["status"])}
        return _stage("paypal_capture", capture["id"], cells, {"stored_response": "orders.capture_response"})
    if paypal.get("capture_error"):
        none_made = _unknown("PayPal made no capture")
        cells = {**na, "amount": none_made, "currency": none_made, "status": _known(paypal["capture_error"])}
        return _stage("paypal_capture", "capture attempt", cells, {"stored_response": "orders.capture_error"})
    return _stage("paypal_capture", None, {**_all(_not_reached("the buyer was never charged")), **na})


def _store_says(step: dict[str, Any] | None) -> dict[str, Any]:
    na = _cell(NOT_APPLICABLE)
    cells = {"product": na, "quantity": na, "amount": na, "currency": na}
    if step is None:
        return _stage("store_says", None, {**cells, "status": _unknown("the order page was not read")})
    status = (step.get("args") or {}).get("status")
    cell = _known(status) if status else _unknown("no order status on the page")
    return _stage("store_says", f"order page, step {step['idx']}", {**cells, "status": cell}, _step_evidence(step))


def _same(field: str, a: Any, b: Any) -> bool:
    if field == "amount":
        try:
            return Decimal(str(a)) == Decimal(str(b))
        except InvalidOperation:
            return False
    return str(a) == str(b)


def _mismatch(code: str, stage: str, field: str, expected: Any, actual: Any) -> dict[str, Any]:
    explanation, fix = EXPLANATIONS[code]
    return {"stage": stage, "field": field, "expected": expected, "actual": actual,
            "explanation": explanation.format(expected=expected, actual=actual), "fix": fix, "first": False}


def _capture_state(stage: dict[str, Any]) -> bool | None:
    """True when PayPal captured the money, False when it did not, None when the capture is not known."""
    status = stage["cells"]["status"]
    if status["kind"] == KNOWN:
        return status["value"] == CAPTURED
    return False if status["kind"] == NOT_REACHED else None


def _label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def _mismatches(stages: dict[str, dict[str, Any]], orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    wanted = stages["agent_wanted"]["cells"]
    for key in ("store_order", "paypal_order", "paypal_capture"):
        for field in COMPARED_FIELDS:
            cell = stages[key]["cells"][field]
            if cell["kind"] == KNOWN and wanted[field]["kind"] == KNOWN and not _same(field, wanted[field]["value"], cell["value"]):
                found.append(_mismatch(field, key, field, wanted[field]["value"], cell["value"]))
    if len(orders) > 1:
        found.append(_mismatch("duplicate_orders", "store_order", "status", "1 order", f"{len(orders)} orders"))
    captured = _capture_state(stages["paypal_capture"])
    for key in ("store_order", "store_says"):
        status = stages[key]["cells"]["status"]
        if status["kind"] != KNOWN or captured is None:
            continue
        if status["value"] in SUCCESS and not captured:
            found.append(_mismatch("success_without_payment", key, "status",
                                   "no paid status without a completed capture", _label(status["value"])))
        elif captured and status["value"] != "paid":
            found.append(_mismatch("paid_not_recorded", key, "status", _label("paid"), _label(status["value"])))
    order = {k: i for i, (k, _) in enumerate(STAGES)}
    found.sort(key=lambda m: (order[m["stage"]], FIELDS.index(m["field"])))
    return found


def build_trace(run: dict[str, Any], sku: str | None, store_orders: list[dict[str, Any]],
                paypal: dict[str, Any] | None) -> dict[str, Any]:
    """The trace for one run.

    run: the run payload (live, catalog_price, steps with idx, tool, args, screenshot_path).
    sku: the SKU of the run's target product, None when it is not in the demo catalog.
    store_orders: the demo store's own orders for this run, oldest first (empty if the run never started a payment).
    paypal: {"id", "order", "capture", "capture_error"} for the PayPal order the latest store order points to
        (order = PayPal's GET order response, capture = the stored capture response), or None.
    """
    steps = run.get("steps") or []
    pay_step = next((s for s in steps if s["tool"] in PAY_TOOLS), None)
    read_step = next((s for s in steps if s["tool"] == READ_BACK_TOOL), None)
    stages = [_agent_wanted(run, sku, pay_step)]
    if run.get("live"):
        stages.append(_stage("store_order", None, _all(_unknown("the store's order system is not visible to the shopper"))))
        stages += [_stage(k, None, _all(_not_reached("live stores are browse-only"))) for k in ("paypal_order", "paypal_capture", "store_says")]
    elif not store_orders:
        stages += [_stage(k, None, _all(_not_reached("the run stopped before payment"))) for k, _ in STAGES[1:]]
    else:
        stages += [_store_order(store_orders), _paypal_order(paypal), _paypal_capture(paypal), _store_says(read_step)]
    by_key = {s["key"]: s for s in stages}
    mismatches = _mismatches(by_key, store_orders) if store_orders and not run.get("live") else []
    if mismatches:
        mismatches[0]["first"] = True
    unknown = sum(c["kind"] == UNKNOWN for s in stages for c in s["cells"].values())
    return {"stages": stages, "mismatches": mismatches, "first_mismatch": mismatches[0] if mismatches else None,
            "counts": {"mismatch": len(mismatches), "unknown": unknown}}
