"""Payment verification: order <-> capture <-> advertised amount <-> fees. Pure and deterministic."""

from decimal import Decimal, InvalidOperation
from typing import Any

from .failures import STORE, cause_of


def _dec(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value is not None else None
    except InvalidOperation:
        return None


def verify_payment(order: dict[str, Any], capture_response: dict[str, Any] | None,
                   advertised_unit_price: Decimal, advertised_currency: str) -> dict[str, Any]:
    """order: our DB row. capture_response: PayPal's raw capture JSON. Returns ok, primary code, mismatches."""
    mismatches: list[dict[str, str]] = []

    def miss(code: str, detail: str) -> None:
        mismatches.append({"code": code, "detail": detail})

    qty = int(order["quantity"])
    expected = advertised_unit_price * qty
    order_amount = _dec(order.get("amount"))
    currency = order.get("currency")
    checked: dict[str, Any] = {"expected_amount": f"{expected:.2f}", "order_amount": order.get("amount"),
                               "currency": currency}

    if order_amount != expected:
        miss("amount_mismatch", f"Order charges {order.get('amount')} {currency} but the store advertises "
                                f"{expected:.2f} {advertised_currency} for {qty} item(s).")
    if currency != advertised_currency:
        miss("currency_mismatch", f"Order currency {currency} differs from the advertised {advertised_currency}.")

    try:
        capture = capture_response["purchase_units"][0]["payments"]["captures"][0]  # type: ignore[index]
    except (TypeError, KeyError, IndexError):
        capture = None
    if capture is None:
        miss("order_capture_mismatch", "No capture found in PayPal's response for this order.")
        return _result(mismatches, checked)

    captured = _dec((capture.get("amount") or {}).get("value"))
    cap_currency = (capture.get("amount") or {}).get("currency_code")
    checked.update({"captured_amount": (capture.get("amount") or {}).get("value"), "capture_id": capture.get("id"),
                    "capture_status": capture.get("status")})
    if captured != order_amount:
        miss("capture_amount_mismatch", f"Captured {captured} but the order was for {order.get('amount')}.")
    if cap_currency and cap_currency != currency:
        miss("currency_mismatch", f"Captured in {cap_currency} but the order is in {currency}.")
    if capture.get("id") != order.get("capture_id"):
        miss("order_capture_mismatch", f"Stored capture id {order.get('capture_id')} does not match PayPal's {capture.get('id')}.")
    if capture.get("status") != "COMPLETED":
        miss("capture_pending", f"Capture status is {capture.get('status')}, not COMPLETED.")

    breakdown = capture.get("seller_receivable_breakdown") or {}
    gross = _dec((breakdown.get("gross_amount") or {}).get("value"))
    fee = _dec((breakdown.get("paypal_fee") or {}).get("value"))
    net = _dec((breakdown.get("net_amount") or {}).get("value"))
    checked.update({"paypal_fee": None if fee is None else f"{fee:.2f}", "net_amount": None if net is None else f"{net:.2f}"})
    if fee is None or net is None:
        miss("fee_missing", "PayPal returned no fee breakdown (paypal_fee / net_amount) for this capture.")
    else:
        if gross is not None and gross != captured:
            miss("capture_amount_mismatch", f"Fee breakdown gross {gross} differs from the captured amount {captured}.")
        if (gross if gross is not None else captured) - fee != net:
            miss("fee_inconsistent", f"Net {net} is not gross {gross if gross is not None else captured} minus fee {fee}.")
    return _result(mismatches, checked)


def _result(mismatches: list[dict[str, str]], checked: dict[str, Any]) -> dict[str, Any]:
    # A store-caused mismatch is the primary code, so a store problem is never hidden behind a PayPal one.
    store = [m for m in mismatches if cause_of(m["code"]) == STORE]
    primary = (store or mismatches or [{"code": None}])[0]["code"]
    return {"ok": not mismatches, "code": primary, "mismatches": mismatches, "checked": checked}
