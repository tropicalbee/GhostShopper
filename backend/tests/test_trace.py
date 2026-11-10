"""The purchase trace builder: pure functions over plain dicts, no browser and no database."""

from backend.app.trace import build_trace

SKU = "FH-MUG-01"
PRICE = {"amount": "24.00", "currency": "USD"}


def run(live=False, price=PRICE, steps=None):
    pay = {"idx": 6, "tool": "pay_with_paypal", "args": {}, "screenshot_path": "runs/run-1/step-06.png"}
    return {"live": live, "catalog_price": price, "steps": [pay] if steps is None else steps}


def read_step(status, idx=7):
    return {"idx": idx, "tool": "read_order_status", "args": {"store_order": 1042, "status": status},
            "screenshot_path": f"runs/run-1/step-{idx:02d}.png"}


def store_order(number=1042, status="paid", **over):
    return {"number": number, "sku": SKU, "quantity": 1, "amount": "24.00", "currency": "USD", "status": status,
            "paypal_order_id": "MOCKORDER1", **over}


def paypal_order(status="COMPLETED", items=True, value="24.00", currency="USD"):
    unit = {"amount": {"currency_code": currency, "value": value}}
    if items:
        unit["items"] = [{"name": "Mug", "sku": SKU, "quantity": "1"}]
    return {"id": "MOCKORDER1", "status": status, "purchase_units": [unit]}


def capture(status="COMPLETED", value="24.00"):
    return {"id": "MOCKORDER1", "status": "COMPLETED", "purchase_units": [{"payments": {"captures": [
        {"id": "MOCKCAP1", "status": status, "amount": {"currency_code": "USD", "value": value}}]}}]}


def paypal(order=None, cap=None, error=None, order_status="COMPLETED"):
    return {"id": "MOCKORDER1", "order": order or paypal_order(order_status), "capture": cap, "capture_error": error}


def trace(steps=None, orders=None, pp=None, r=None):
    steps = [{"idx": 6, "tool": "pay_with_paypal", "args": {}, "screenshot_path": None}, *(steps or [])]
    return build_trace(r or run(steps=steps), SKU, [store_order()] if orders is None else orders, pp)


def stage(t, key):
    return next(s for s in t["stages"] if s["key"] == key)


def test_all_five_records_agree():
    t = trace([read_step("paid")], pp=paypal(cap=capture()))
    assert [s["key"] for s in t["stages"]] == ["agent_wanted", "store_order", "paypal_order", "paypal_capture", "store_says"]
    assert t["mismatches"] == [] and t["first_mismatch"] is None
    assert t["counts"] == {"mismatch": 0, "unknown": 0}
    wanted = stage(t, "agent_wanted")
    assert wanted["source"] == "intent, step 6"
    assert wanted["cells"]["product"] == {"kind": "known", "value": SKU, "reason": None}
    assert stage(t, "store_order")["source"] == "#1042"
    assert stage(t, "paypal_order")["source"] == "MOCKORDER1"
    cap = stage(t, "paypal_capture")
    assert cap["source"] == "MOCKCAP1"
    assert cap["cells"]["product"]["kind"] == "n/a" and cap["cells"]["quantity"]["kind"] == "n/a"
    says = stage(t, "store_says")
    assert says["source"] == "order page, step 7"
    assert says["evidence"] == {"step": 7, "screenshot": "step-07.png"}
    assert says["cells"]["status"]["value"] == "paid"


def test_store_never_marks_the_order_paid():
    t = trace([read_step("awaiting_payment")], orders=[store_order(status="awaiting_payment")], pp=paypal(cap=capture()))
    first = t["first_mismatch"]
    assert (first["stage"], first["field"], first["first"]) == ("store_order", "status", True)
    assert first["expected"] == "Paid" and first["actual"] == "Awaiting payment"
    assert "never ship" in first["explanation"] and "mark the order paid" in first["fix"]
    assert [(m["stage"], m["first"]) for m in t["mismatches"]] == [("store_order", True), ("store_says", False)]


def test_declined_payment_shown_as_paid():
    t = trace([read_step("paid")], pp=paypal(order_status="CREATED", error="INSTRUMENT_DECLINED"))
    assert stage(t, "paypal_capture")["cells"]["status"]["value"] == "INSTRUMENT_DECLINED"
    assert stage(t, "paypal_capture")["cells"]["amount"]["kind"] == "unknown"
    assert [(m["stage"], m["field"]) for m in t["mismatches"]] == [("store_order", "status"), ("store_says", "status")]
    assert t["first_mismatch"]["actual"] == "Paid"
    assert "not paid" in t["first_mismatch"]["fix"] or "declined" in t["first_mismatch"]["fix"]


def test_success_after_cancel():
    t = trace([read_step("confirmed")], orders=[store_order(status="confirmed")], pp=paypal(order_status="CREATED"))
    assert stage(t, "paypal_capture")["cells"]["status"]["kind"] == "not_reached"
    first = t["first_mismatch"]
    assert (first["stage"], first["actual"]) == ("store_order", "Confirmed")
    assert t["counts"]["mismatch"] == 2


def test_cancel_handled_correctly_has_no_mismatch():
    t = trace([read_step("cancelled")], orders=[store_order(status="cancelled")], pp=paypal(order_status="CREATED"))
    assert t["mismatches"] == []


def test_duplicate_orders_for_one_purchase():
    orders = [store_order(1042, "awaiting_payment"), store_order(1043, "paid")]
    t = trace([read_step("paid")], orders=orders, pp=paypal(cap=capture()))
    first = t["first_mismatch"]
    assert (first["stage"], first["field"]) == ("store_order", "status")
    assert (first["expected"], first["actual"]) == ("1 order", "2 orders")
    assert "2 orders" in first["explanation"]
    assert stage(t, "store_order")["source"] == "#1042, #1043"
    assert t["counts"]["mismatch"] == 1


def test_missing_item_list_is_unknown_never_guessed():
    t = trace([read_step("paid")], pp=paypal(order=paypal_order(items=False), cap=capture()))
    cells = stage(t, "paypal_order")["cells"]
    assert cells["product"] == {"kind": "unknown", "value": None, "reason": "store sent no item list"}
    assert cells["quantity"]["kind"] == "unknown"
    assert t["mismatches"] == [] and t["counts"]["unknown"] == 2


def test_amount_that_differs_from_the_advertised_price_is_flagged_at_the_first_stage_that_has_it():
    orders = [store_order(amount="27.00")]
    t = trace([read_step("paid")], orders=orders, pp=paypal(order=paypal_order(value="27.00"), cap=capture(value="27.00")))
    assert [(m["stage"], m["field"]) for m in t["mismatches"]] == [
        ("store_order", "amount"), ("paypal_order", "amount"), ("paypal_capture", "amount")]
    assert t["first_mismatch"]["expected"] == "24.00" and t["first_mismatch"]["actual"] == "27.00"


def test_amounts_compare_as_numbers():
    t = trace([read_step("paid")], orders=[store_order(amount="24.0")], pp=paypal(cap=capture()))
    assert t["mismatches"] == []


def test_wrong_product_and_quantity():
    t = trace([read_step("paid")], orders=[store_order(sku="FH-BOWL-02", quantity=2)], pp=paypal(cap=capture()))
    assert [(m["stage"], m["field"]) for m in t["mismatches"]] == [("store_order", "product"), ("store_order", "quantity")]


def test_no_order_status_text_on_the_page_is_unknown():
    t = trace([read_step(None)], pp=paypal(cap=capture()))
    cell = stage(t, "store_says")["cells"]["status"]
    assert cell == {"kind": "unknown", "value": None, "reason": "no order status on the page"}
    assert [m["stage"] for m in t["mismatches"]] == []


def test_unread_order_page_is_unknown():
    t = trace(None, pp=paypal(cap=capture()))
    assert stage(t, "store_says")["cells"]["status"]["reason"] == "the order page was not read"


def test_paypal_order_that_was_never_read_is_unknown():
    t = trace([read_step("awaiting_payment")], orders=[store_order(status="awaiting_payment")],
              pp={"id": "MOCKORDER1", "order": None, "capture": None, "capture_error": None})
    assert stage(t, "paypal_order")["cells"]["amount"]["reason"] == "PayPal's order was not read after payment"


def test_run_stopped_before_payment_is_not_reached():
    t = build_trace(run(steps=[]), SKU, [], None)
    assert stage(t, "agent_wanted")["source"] == "intent"
    for key in ("store_order", "paypal_order", "paypal_capture", "store_says"):
        assert {c["kind"] for c in stage(t, key)["cells"].values()} == {"not_reached"}
    assert t["mismatches"] == [] and t["counts"]["unknown"] == 0


def test_payment_started_but_never_captured_is_not_a_mismatch():
    t = trace([read_step("awaiting_payment")], orders=[store_order(status="awaiting_payment")],
              pp=paypal(order_status="CREATED"))
    assert stage(t, "paypal_capture")["cells"]["status"]["kind"] == "not_reached"
    assert t["mismatches"] == []


def test_live_store_has_no_visible_order_system():
    t = build_trace(run(live=True, price=None, steps=[]), None, [], None)
    cells = stage(t, "store_order")["cells"]
    assert {c["kind"] for c in cells.values()} == {"unknown"}
    assert cells["status"]["reason"] == "the store's order system is not visible to the shopper"
    assert stage(t, "agent_wanted")["cells"]["product"]["kind"] == "unknown"
    assert {c["kind"] for c in stage(t, "paypal_capture")["cells"].values()} == {"not_reached"}
    assert t["mismatches"] == []


def test_unknown_catalog_price_skips_the_comparison():
    t = build_trace(run(price=None), SKU, [store_order(amount="99.00")], paypal(cap=capture(value="99.00")))
    assert stage(t, "agent_wanted")["cells"]["amount"]["kind"] == "unknown"
    assert [m for m in t["mismatches"] if m["field"] == "amount"] == []


def test_capture_completed_but_store_says_confirmed_is_flagged():
    t = trace([read_step("confirmed")], orders=[store_order(status="paid")], pp=paypal(cap=capture()))
    assert [(m["stage"], m["actual"]) for m in t["mismatches"]] == [("store_says", "Confirmed")]
