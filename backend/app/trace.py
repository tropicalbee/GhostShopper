"""The purchase trace: five records of one purchase, compared field by field, and linked by identifiers.

Stages, in the order a purchase travels: what the agent wanted, the store's own order, PayPal's order, PayPal's
capture, and what the store shows the buyer afterwards. Four link checks prove the records are the same purchase
by identifiers in both directions, never by matching amounts. The trace is evidence only. A value the source does not
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
NO_PAYPAL_ID = "the store order has no PayPal order id, so PayPal's records could not be looked up"
COMPARED_FIELDS = ("product", "quantity", "amount", "currency")  # checked against what the agent wanted

PAY_TOOLS = ("pay_with_paypal", "pay_with_saved_paypal")
READ_BACK_TOOL = "read_order_status"
SUCCESS = ("paid", "confirmed")  # what a store means by "your order went through"
CAPTURED = "COMPLETED"

KNOWN, UNKNOWN, NOT_APPLICABLE, NOT_REACHED = "known", "unknown", "n/a", "not_reached"
OK, BROKEN = "ok", "broken"  # link kinds; a link can also be UNKNOWN or NOT_APPLICABLE
# The four links: (key, label, the stage a broken link is reported at).
LINKS = (
    ("store_to_paypal_order", "Store order points to PayPal's order", "paypal_order"),
    ("paypal_order_to_store", "PayPal's order points back to the store order", "paypal_order"),
    ("capture_to_paypal_order", "The capture belongs to PayPal's order", "paypal_capture"),
    ("store_to_capture", "Store order points to PayPal's capture", "paypal_capture"),
)

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
    "paid_without_paypal_reference": (
        "The store marks the order {actual}, but its order holds no PayPal reference, so nobody can check the money "
        "arrived.",
        "Save PayPal's order id on your order when it is created, and mark the order paid only after a completed "
        "capture for that id."),
    "duplicate_orders": (
        "The store created {actual} for one intended purchase. Unpaid duplicates confuse fulfilment and the buyer.",
        "When the buyer retries a payment, reuse the pending order instead of creating a new one: keep the order "
        "number in the checkout page and send it with every attempt."),
    "records_not_linked": (
        "{what} (expected {expected}, found {actual}). The store's order and PayPal's records cannot be shown to be "
        "the same purchase, so you could not reconcile the payment with the order.",
        "Create your own order first and send its number to PayPal as the purchase unit custom_id. Save PayPal's "
        "order id and capture id on your order when they come back, and check both match before marking it paid."),
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
        return _stage("paypal_order", None, _all(_unknown(NO_PAYPAL_ID)))
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
    if paypal is None:  # only when the store order has no PayPal id: PayPal was never looked at, so never guess
        return _stage("paypal_capture", None, _all(_unknown(NO_PAYPAL_ID)))
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


def _mismatch(code: str, stage: str, field: str, expected: Any, actual: Any, what: str = "") -> dict[str, Any]:
    explanation, fix = EXPLANATIONS[code]
    return {"stage": stage, "field": field, "expected": expected, "actual": actual,
            "explanation": explanation.format(expected=expected, actual=actual, what=what), "fix": fix, "first": False}


def _link(key: str, expected: Any, actual: Any, kind: str, reason: str | None = None) -> dict[str, Any]:
    label = next(label for k, label, _ in LINKS if k == key)
    return {"key": key, "label": label, "expected": expected, "actual": actual, "kind": kind, "reason": reason}


def _compare(key: str, expected: Any, actual: Any) -> dict[str, Any]:
    return _link(key, expected, actual, OK if str(expected) == str(actual) else BROKEN)


def _captured_id(response: dict[str, Any] | None) -> str | None:
    """The id of the capture in a capture response or a GET order response, None when there is none."""
    unit = ((response or {}).get("purchase_units") or [{}])[0]
    captures = (unit.get("payments") or {}).get("captures") or []
    return captures[0].get("id") if captures else None


def _links(store_orders: list[dict[str, Any]], paypal: dict[str, Any] | None, live: bool) -> list[dict[str, Any]]:
    """The four identifier checks. Each is ok, broken (the ids disagree), unknown (an id is missing, with the reason:
    never guessed) or n/a (nothing to link yet). Amounts play no part."""
    keys = [k for k, _, _ in LINKS]
    if live or not store_orders:
        reason = "live stores are browse-only" if live else "the run stopped before payment"
        return [_link(k, None, None, NOT_APPLICABLE, reason) for k in keys]
    latest = store_orders[-1]
    number, store_paypal_id = str(latest["number"]), latest.get("paypal_order_id")
    order = (paypal or {}).get("order")
    pp_id = (order or {}).get("id")

    if not store_paypal_id:
        l1 = _link(keys[0], None, pp_id, UNKNOWN, "the store order has no PayPal order id")
    elif order is None:
        l1 = _link(keys[0], store_paypal_id, None, UNKNOWN, "PayPal's order was not read after payment")
    elif not pp_id:
        l1 = _link(keys[0], store_paypal_id, None, UNKNOWN, "PayPal's order has no id")
    else:
        l1 = _compare(keys[0], store_paypal_id, pp_id)

    unit = ((order or {}).get("purchase_units") or [{}])[0]
    if order is None:
        l2 = _link(keys[1], number, None, UNKNOWN, "PayPal's order was not read after payment")
    elif not unit.get("custom_id"):
        l2 = _link(keys[1], number, None, UNKNOWN,
                   "PayPal's order carries no custom_id (the store did not send its order number, or this purchase "
                   "predates the link)")
    else:
        l2 = _compare(keys[1], number, unit["custom_id"])

    response = (paypal or {}).get("capture")
    order_id = pp_id or store_paypal_id
    if response is None:
        if paypal is None:  # no PayPal id on the store order: PayPal's records were never looked up, so nothing is said
            l3 = _link(keys[2], None, None, UNKNOWN, NO_PAYPAL_ID)
            l4 = (_link(keys[3], latest["paypal_capture_id"], None, UNKNOWN, "PayPal's capture was not read")
                  if latest.get("paypal_capture_id") else _link(keys[3], None, None, UNKNOWN, NO_PAYPAL_ID))
            return [l1, l2, l3, l4]
        why = "PayPal made no capture" if paypal.get("capture_error") else "the buyer was never charged"
        l3 = _link(keys[2], order_id, None, NOT_APPLICABLE, why)
        if latest.get("paypal_capture_id"):
            l4 = _link(keys[3], latest["paypal_capture_id"], None, UNKNOWN, "PayPal's capture was not read")
        else:
            l4 = _link(keys[3], None, None, NOT_APPLICABLE, why)
        return [l1, l2, l3, l4]

    capture_id = _captured_id(response)
    listed = _captured_id(order)
    if not response.get("id") or not capture_id:
        l3 = _link(keys[2], order_id, response.get("id"), UNKNOWN, "PayPal's capture response has no order or capture id")
    elif not order_id:
        l3 = _link(keys[2], None, response["id"], UNKNOWN, "the PayPal order id is not known")
    elif str(response["id"]) != str(order_id):
        l3 = _link(keys[2], order_id, response["id"], BROKEN)
    elif listed and listed != capture_id:
        l3 = _link(keys[2], f"capture {listed} (listed on the order)", f"capture {capture_id}", BROKEN)
    else:
        l3 = _link(keys[2], order_id, response["id"], OK)

    if not capture_id:
        l4 = _link(keys[3], latest.get("paypal_capture_id"), None, UNKNOWN, "PayPal's capture has no id")
    elif not latest.get("paypal_capture_id"):
        l4 = _link(keys[3], None, capture_id, UNKNOWN, "the store did not save PayPal's capture id")
    else:
        l4 = _compare(keys[3], latest["paypal_capture_id"], capture_id)
    return [l1, l2, l3, l4]


def _capture_state(stage: dict[str, Any]) -> bool | None:
    """True when PayPal captured the money, False when it did not, None when the capture is not known."""
    status = stage["cells"]["status"]
    if status["kind"] == KNOWN:
        return status["value"] == CAPTURED
    return False if status["kind"] == NOT_REACHED else None


def _label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def _mismatches(stages: dict[str, dict[str, Any]], orders: list[dict[str, Any]],
                links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    where = {k: stage for k, _, stage in LINKS}
    for link in links:
        if link["kind"] == BROKEN:
            found.append(_mismatch("records_not_linked", where[link["key"]], link["key"], link["expected"],
                                   link["actual"], what=link["label"]))
    wanted = stages["agent_wanted"]["cells"]
    for key in ("store_order", "paypal_order", "paypal_capture"):
        for field in COMPARED_FIELDS:
            cell = stages[key]["cells"][field]
            if cell["kind"] == KNOWN and wanted[field]["kind"] == KNOWN and not _same(field, wanted[field]["value"], cell["value"]):
                found.append(_mismatch(field, key, field, wanted[field]["value"], cell["value"]))
    if len(orders) > 1:
        found.append(_mismatch("duplicate_orders", "store_order", "status", "1 order", f"{len(orders)} orders"))
    # A paid order with no PayPal order id is a fact about the store's own records, so it is raised once, at
    # store_order. The PayPal stages are unknown then (never guessed), so nothing else is inferred from them.
    if orders[-1]["status"] in SUCCESS and not orders[-1].get("paypal_order_id"):
        found.append(_mismatch("paid_without_paypal_reference", "store_order", "status", "a PayPal order id on the order",
                               _label(orders[-1]["status"])))
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
    # Broken links come first, in link order: if the records are not provably the same purchase, the field-by-field
    # comparison compares records that may belong to different purchases. Field mismatches follow, by stage.
    link_keys = list(where)
    found.sort(key=lambda m: (0, link_keys.index(m["field"]), 0) if m["field"] in where
               else (1, order[m["stage"]], FIELDS.index(m["field"])))
    return found


def build_trace(run: dict[str, Any], sku: str | None, store_orders: list[dict[str, Any]],
                paypal: dict[str, Any] | None) -> dict[str, Any]:
    """The trace for one run: the five stages, the four link checks and the mismatches.

    run: the run payload (live, catalog_price, steps with idx, tool, args, screenshot_path).
    sku: the SKU of the run's target product, None when it is not in the demo catalog.
    store_orders: the demo store's own orders for this run, oldest first (empty if the run never started a payment).
        Each has number, sku, quantity, amount, currency, status, paypal_order_id and, once saved, paypal_capture_id.
    paypal: {"id", "order", "capture", "capture_error"} for the PayPal order the latest store order points to
        (order = PayPal's GET order response, capture = the stored capture response), or None. The order's first
        purchase unit carries custom_id (the store order number); the capture response's top-level id is the order id.
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
    live = bool(run.get("live"))
    links = _links(store_orders, paypal, live)
    mismatches = _mismatches(by_key, store_orders, links) if store_orders and not live else []
    if mismatches:
        mismatches[0]["first"] = True
    unknown = sum(c["kind"] == UNKNOWN for s in stages for c in s["cells"].values())
    unknown += sum(link["kind"] == UNKNOWN for link in links)
    return {"stages": stages, "links": links, "mismatches": mismatches, "first_mismatch": mismatches[0] if mismatches else None,
            "counts": {"mismatch": len(mismatches), "unknown": unknown}}
