"""The WebMCP tool checklist, from fixture run data. Pure: no browser, no network."""

import copy

from backend.app.webmcp.checks import tool_checks
from backend.app.webmcp.tools import SHOPPING_TOOLS

CATALOG = {"amount": "24.00", "currency": "USD"}


def tool(name, read_only=False):
    return {"name": name, "description": f"{name} tool", "input_schema": {"type": "object"}, "read_only": read_only}


REPORT = {
    "discovery": {"tools": [tool(n, n in SHOPPING_TOOLS[:2]) for n in SHOPPING_TOOLS]},
    "tool_calls": [{"tool": "shopping.searchProducts"}], "search": {"count": 1, "matched": True},
    "handoff": {"approved": True, "approval_url_host": "www.sandbox.paypal.com", "cart_id": "1042"},
    "completion": {"status": "COMPLETED", "capture_id": "C1", "amount": {"value": "24.00"}},
    "price_consistency": {"unit_prices": {"search": "24.00", "product": "24.00", "checkout": "24.00", "capture": "24.00"}},
}


def trace(first=None, says="paid"):
    cell = {"kind": "known", "value": says} if says else {"kind": "unknown"}
    return {"stages": [{"key": "store_says", "cells": {"status": cell}}], "first_mismatch": first}


def run(report=REPORT, **kwargs):
    options = {"trace": trace(), "catalog_price": CATALOG, "external": False, "mock_paypal": False, **kwargs}
    return {c["key"]: c for c in tool_checks(report, **options)}


def edited(**changes):
    return {**copy.deepcopy(REPORT), **changes}


def test_a_healthy_run_passes_every_check_in_order():
    checks = tool_checks(REPORT, trace=trace(), catalog_price=CATALOG, external=False, mock_paypal=False)
    assert [c["key"] for c in checks] == ["tools_discovered", "schemas_valid", "product_found", "price_consistent",
                                         "buyer_approval_required", "handoff_to_paypal", "checkout_completed", "order_recorded"]
    assert {c["status"] for c in checks} == {"pass"}


def test_missing_tools_are_named():
    report = edited(discovery={"tools": [tool("shopping.searchProducts", True)]})
    found = run(report)["tools_discovered"]
    assert found["status"] == "fail" and "missing shopping.getProduct" in found["evidence"]
    assert run(edited(discovery={"tools": []}))["schemas_valid"]["status"] == "not_tested"


def test_schemas_must_be_objects_with_a_description_and_checkout_tools_must_not_be_read_only():
    broken = tool("shopping.getProduct", True) | {"description": ""}
    assert run(edited(discovery={"tools": [broken]}))["schemas_valid"]["status"] == "fail"
    read_only_checkout = [tool("shopping.initiateCheckout", True)]
    assert "initiateCheckout" in run(edited(discovery={"tools": read_only_checkout}))["schemas_valid"]["evidence"]


def test_product_found_needs_a_search_that_matched_the_target():
    assert run(edited(search={"count": 3, "matched": False}))["product_found"]["status"] == "fail"
    assert run(edited(tool_calls=[]))["product_found"]["status"] == "not_tested"


def test_price_must_agree_across_tools_and_with_the_catalog():
    off = edited(price_consistency={"unit_prices": {"search": "24.00", "checkout": "27.00", "product": None, "capture": "27.00"}})
    assert run(off)["price_consistent"]["status"] == "fail"
    same_but_not_catalog = edited(price_consistency={"unit_prices": {"search": "27.00", "checkout": "27.00"}})
    assert run(same_but_not_catalog)["price_consistent"]["status"] == "fail"
    assert run(same_but_not_catalog, catalog_price=None)["price_consistent"]["status"] == "pass"  # the showcase has no catalog
    assert run(edited(price_consistency={"unit_prices": {"search": "24.00"}}))["price_consistent"]["status"] == "not_tested"


def test_money_must_not_move_before_the_buyer_approves():
    assert run(edited(handoff=None, completion=None))["buyer_approval_required"]["status"] == "not_tested"
    early = edited(handoff={**REPORT["handoff"], "approved": False})
    assert run(early)["buyer_approval_required"]["status"] == "fail"
    assert run(edited(handoff={**REPORT["handoff"], "approved": False}, completion=None))["buyer_approval_required"]["status"] == "pass"


def test_the_hand_off_goes_to_paypal_or_is_labelled_mock():
    local = edited(handoff={**REPORT["handoff"], "approval_url_host": "127.0.0.1"})
    assert run(local)["handoff_to_paypal"]["status"] == "fail"
    mock = run(local, mock_paypal=True)["handoff_to_paypal"]
    assert mock["status"] == "pass" and "mock PayPal" in mock["evidence"]
    assert run(edited(handoff={**REPORT["handoff"], "approval_url_host": "paypal.com.evil.test"}))["handoff_to_paypal"]["status"] == "fail"


def test_checkout_completed_needs_a_capture():
    assert run(edited(completion=None))["checkout_completed"]["status"] == "not_tested"
    assert run(edited(completion={"status": "DECLINED"}))["checkout_completed"]["status"] == "fail"


def test_order_recorded_follows_the_trace_and_is_not_tested_on_the_showcase():
    first = {"stage": "store_order", "field": "status", "actual": "Awaiting payment"}
    bad = run(trace=trace(first))["order_recorded"]
    assert bad["status"] == "fail" and "Awaiting payment" in bad["evidence"]
    assert run(trace=trace(says=None))["order_recorded"]["status"] == "not_tested"
    external = run(external=True, catalog_price=None)["order_recorded"]
    assert external["status"] == "not_tested" and "PayPal's merchant" in external["evidence"]


SHOWCASE = edited(
    search={"count": 2, "matched": False, "products": {"P-1": "Starbucks Coffee", "P-2": "Hulu Gift Card"}}, target="gift card",
    bought={"product_id": "P-2", "title": "Hulu Gift Card"})


def test_on_the_showcase_the_product_bought_must_appear_in_a_search_result():
    found = run(SHOWCASE, external=True, catalog_price=None)["product_found"]
    assert found["status"] == "pass" and "Hulu Gift Card" in found["evidence"] and "P-2" in found["evidence"]
    unlisted = edited(**{**SHOWCASE, "bought": {"product_id": "P-9", "title": None}})
    assert run(unlisted, external=True, catalog_price=None)["product_found"]["status"] == "fail"


def test_on_the_demo_store_the_bought_title_must_also_match_the_target():
    assert run(edited(**{**SHOWCASE, "target": "Speckled Stoneware Mug"}))["product_found"]["status"] == "fail"
    demo = edited(search={"count": 1, "matched": True, "products": {"FH-MUG-01": "Speckled Stoneware Mug"}},
                  target="Speckled Stoneware Mug", bought={"product_id": "FH-MUG-01", "title": "Speckled Stoneware Mug"})
    assert run(demo)["product_found"]["status"] == "pass"
