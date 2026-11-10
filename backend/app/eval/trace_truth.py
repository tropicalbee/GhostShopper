"""Hand-written ground truth for the purchase trace benchmark (trace_matrix.py).

Every expectation comes from what the store flaw and the PayPal outcome mean for a merchant, written before looking
at any trace output. The first mismatch is (code, stage): code is a key of trace.EXPLANATIONS or a compared field
name, stage is where a merchant would look first. None means the trace must report no mismatch. links lists the four
link kinds in trace.LINKS order. An expectation is never edited to make a scenario pass.
"""

from dataclasses import dataclass

OK, BROKEN, UNKNOWN, NA = "ok", "broken", "unknown", "n/a"
ALL_OK = (OK, OK, OK, OK)
NO_CAPTURE = (OK, OK, NA, NA)  # PayPal's order exists and points both ways; no capture exists to link

# The PayPal outcomes of the matrix and the mock PayPal scenario that produces each.
PAYPAL = {
    "captured": "ok",
    "declined": "capture_declined",
    "cancelled": "buyer_cancels",
    "retry": "first_attempt_fails",  # a temporary 503 on the first capture, the buyer pays again
    "capture_amount": "capture_amount_mismatch",  # PayPal captures 1.00 more than the order
}

# PayPal scenarios left out of the matrix, with the reason. Not silently dropped.
SKIPPED = {
    "fee_mismatch": "only the PayPal fee differs; the trace compares product, quantity, amount, currency and status, not fees",
    "no_button / popup_blocked / approval_stuck / captcha / verification_required / seller_login":
        "the purchase never starts or never reaches a capture, so no store order or PayPal record exists to trace",
    "price_mismatch x capture_amount_mismatch": "two causes in one record; the first mismatch would not isolate either",
}


@dataclass(frozen=True)
class Case:
    id: str
    category: str  # healthy, flaw, control (a flaw whose trigger is not in this purchase), price, capture, links
    flaw: str  # a store flaw key, "healthy" for none, or "tampered" for the link cases
    paypal: str  # a key of PAYPAL, or the tampering applied for link cases
    first: tuple[str, str] | None
    links: tuple[str, ...] | None  # None = not stated (never the case in this table)
    why: str


def _c(id: str, category: str, flaw: str, paypal: str, first, links, why: str) -> Case:
    return Case(id, category, flaw, paypal, first, links, why)


CASES: tuple[Case, ...] = (
    # Healthy store: the trace must stay silent whatever PayPal does.
    _c("healthy-captured", "healthy", "healthy", "captured", None, ALL_OK,
       "A good purchase: every record agrees and every id points to the same purchase."),
    _c("healthy-retry", "healthy", "healthy", "retry", None, ALL_OK,
       "A temporary PayPal failure, then a paid retry on a store that reuses its order: one order, no problem."),
    _c("healthy-declined", "healthy", "healthy", "declined", None, NO_CAPTURE,
       "PayPal declined, the store says Payment failed: they agree, so nothing to report."),
    _c("healthy-cancelled", "healthy", "healthy", "cancelled", None, NO_CAPTURE,
       "The buyer cancelled, the store says Cancelled: they agree, so nothing to report."),
    # The four purchase flaws, where they bite.
    _c("never_marks_paid-captured", "flaw", "never_marks_paid", "captured", ("paid_not_recorded", "store_order"), ALL_OK,
       "PayPal took the money, the store still shows Awaiting payment: the order may never ship."),
    _c("never_marks_paid-retry", "flaw", "never_marks_paid", "retry", ("paid_not_recorded", "store_order"), ALL_OK,
       "The retry is captured, the store still shows Awaiting payment."),
    _c("declined_marked_paid-declined", "flaw", "declined_marked_paid", "declined", ("success_without_payment", "store_order"), NO_CAPTURE,
       "PayPal declined but the store shows Paid: goods would ship unpaid."),
    _c("success_after_cancel-cancelled", "flaw", "success_after_cancel", "cancelled", ("success_without_payment", "store_order"), NO_CAPTURE,
       "The buyer cancelled but the store shows Confirmed: goods would ship unpaid."),
    _c("duplicate_on_retry-retry", "flaw", "duplicate_on_retry", "retry", ("duplicate_orders", "store_order"), ALL_OK,
       "One intended purchase left two store orders, one of them never paid."),
    # price_mismatch: the buyer is charged 3.00 more than the page advertised, whatever PayPal then does.
    _c("price_mismatch-captured", "price", "price_mismatch", "captured", ("amount", "store_order"), ALL_OK,
       "The store's own order already carries 27.00 against the advertised 24.00."),
    _c("price_mismatch-retry", "price", "price_mismatch", "retry", ("amount", "store_order"), ALL_OK,
       "Same overcharge; the temporary failure and retry do not change which record shows it first."),
    _c("price_mismatch-declined", "price", "price_mismatch", "declined", ("amount", "store_order"), NO_CAPTURE,
       "The order was created at 27.00 even though PayPal then declined: the wrong price is still on record."),
    _c("price_mismatch-cancelled", "price", "price_mismatch", "cancelled", ("amount", "store_order"), NO_CAPTURE,
       "The order was created at 27.00 even though the buyer cancelled."),
    # PayPal captures a different amount than the order, on a healthy store.
    _c("healthy-capture_amount", "capture", "healthy", "capture_amount", ("amount", "paypal_capture"), ALL_OK,
       "The store and PayPal's order say 24.00 but PayPal captured 25.00: the first record that differs is the capture."),
    # Controls: a purchase flaw switched on, but this PayPal outcome never triggers it.
    _c("never_marks_paid-declined", "control", "never_marks_paid", "declined", None, NO_CAPTURE,
       "never_marks_paid only affects captured payments; a declined one is correctly Payment failed."),
    _c("never_marks_paid-cancelled", "control", "never_marks_paid", "cancelled", None, NO_CAPTURE,
       "never_marks_paid only affects captured payments; a cancelled one is correctly Cancelled."),
    _c("declined_marked_paid-captured", "control", "declined_marked_paid", "captured", None, ALL_OK,
       "The flaw only acts on a decline; a captured payment is correctly Paid."),
    _c("declined_marked_paid-retry", "control", "declined_marked_paid", "retry", None, ALL_OK,
       "A temporary failure is not a decline and the retry is captured, so Paid is correct."),
    _c("declined_marked_paid-cancelled", "control", "declined_marked_paid", "cancelled", None, NO_CAPTURE,
       "The flaw only acts on a decline; a cancelled payment is correctly Cancelled."),
    _c("success_after_cancel-captured", "control", "success_after_cancel", "captured", None, ALL_OK,
       "The flaw only acts on a cancel; a captured payment is correctly Paid."),
    _c("success_after_cancel-retry", "control", "success_after_cancel", "retry", None, ALL_OK,
       "No cancel happens; the retry is captured and Paid is correct."),
    _c("success_after_cancel-declined", "control", "success_after_cancel", "declined", None, NO_CAPTURE,
       "The flaw only acts on a cancel; a decline is correctly Payment failed."),
    _c("duplicate_on_retry-captured", "control", "duplicate_on_retry", "captured", None, ALL_OK,
       "With no failed first attempt there is no retry, so one order is correct."),
    _c("duplicate_on_retry-declined", "control", "duplicate_on_retry", "declined", None, NO_CAPTURE,
       "A decline is not retried, so one order, Payment failed, is correct."),
    _c("duplicate_on_retry-cancelled", "control", "duplicate_on_retry", "cancelled", None, NO_CAPTURE,
       "A cancel is not retried, so one order, Cancelled, is correct."),
    # Link integrity: a healthy captured purchase whose recorded ids are tampered with before the trace is built.
    _c("link-custom_id-missing", "links", "tampered", "custom_id removed from PayPal's order", None, (OK, UNKNOWN, OK, OK),
       "PayPal's order no longer says which store order it belongs to: the back link cannot be checked, and nothing may be guessed."),
    _c("link-custom_id-wrong", "links", "tampered", "custom_id names another store order", ("records_not_linked", "paypal_order"),
       (OK, BROKEN, OK, OK),
       "PayPal's order says it belongs to store order 9999, not this one: the records are not the same purchase."),
    _c("link-store-points-to-other-order", "links", "tampered", "store paypal_order_id is another order",
       ("records_not_linked", "paypal_order"), (OK, BROKEN, OK, BROKEN),
       "The store points at a PayPal order that belongs to another store order and holds another capture."),
    _c("link-capture-for-other-order", "links", "tampered", "capture response is for another order",
       ("records_not_linked", "paypal_capture"), (OK, OK, BROKEN, OK),
       "The stored capture response names a different PayPal order than the one the store order points to."),
    _c("link-store-capture-id-wrong", "links", "tampered", "store capture id is wrong",
       ("records_not_linked", "paypal_capture"), (OK, OK, OK, BROKEN),
       "The store saved a capture id that PayPal's capture does not have."),
    _c("link-store-capture-id-missing", "links", "tampered", "store capture id removed", None, (OK, OK, OK, UNKNOWN),
       "The store never saved the capture id: that link cannot be checked, and nothing may be guessed."),
    # Expectation changed 2026-11-11 by design decision (user): a Paid order with no PayPal reference is flagged as such;
    # PayPal-side stages are unknown, never guessed.
    _c("link-store-order-id-missing", "links", "tampered", "store paypal_order_id removed",
       ("paid_without_paypal_reference", "store_order"), (UNKNOWN, UNKNOWN, UNKNOWN, UNKNOWN),
       "The store says Paid but its order holds no PayPal reference, so nobody can check the money arrived. That is a "
       "fact about the store's own records. Every PayPal record is unknown: the trace cannot tell 'never charged' from "
       "'cannot find the charge'."),
    _c("link-store-order-id-missing-unpaid", "links", "tampered", "store paypal_order_id removed, status awaiting_payment",
       None, (UNKNOWN, UNKNOWN, UNKNOWN, UNKNOWN),
       "An unpaid order with no PayPal id is the normal result of a failed PayPal create: nothing to flag, and every "
       "PayPal record is unknown."),
)
