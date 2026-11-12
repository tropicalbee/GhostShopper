"""The agent's spending limit: enforced in code before the PayPal button, and recorded as not the store's fault."""

import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.app import db, runs
from backend.app.agent.loop import goal_text
from backend.app.agent.service import RunConfigError, parse_budget
from backend.app.main import create_app
from backend.app.owner import COOKIE, new_token

from .test_agent_e2e import requires_browser
from .test_api import make_settings
from .test_checkout_e2e import check, checkout_run, results, server  # noqa: F401  (server is a fixture)

pytestmark = pytest.mark.anyio


@requires_browser
async def test_budget_above_the_price_buys_and_records_the_limit_check(server):
    run = await checkout_run(server, "day3_checkout_flaws_off", budget=Decimal("30.00"))
    assert run["budget"] == "30.00"
    assert run["outcome"] == "purchased" and run["order"]["capture_status"] == "COMPLETED"
    assert run["score"]["total"] == 100
    verified = check(run, "payment_verified")
    assert verified["passed"] == 1
    assert verified["evidence"]["budget"] == {"limit": "30.00", "captured": "24.00", "within": True}
    assert "within the 30.00 limit" in verified["reason"]
    assert f"${Decimal('30.00')}" in run["goal"]


@requires_browser
async def test_budget_below_the_price_does_not_pay_and_is_not_the_stores_fault(server):
    run = await checkout_run(server, "day3_checkout_flaws_off", budget=Decimal("20.00"))
    assert run["status"] == "completed", run["error"]
    assert run["outcome"] == "blocked" and run["order"] is None
    c = check(run, "paypal_button_found")
    assert (c["passed"], c["code"], c["cause"]) == (0, "over_budget", "environment")
    assert c["evidence"]["budget"] == "20.00" and c["evidence"]["checkout_total"] == "24.00"
    assert "over the $20.00 spending limit" in c["reason"]
    pay_step = next(s for s in run["steps"] if s["tool"] == "pay_with_paypal")
    assert pay_step["observation"].startswith("Not paid:") and "20.00" in pay_step["observation"]
    # The rest of the payment never ran and none of it counts against the store.
    later = ["popup_opened", "payment_approved", "capture_completed", "payment_verified"]
    assert all(check(run, k)["status"] == "excluded" for k in later)
    assert run["score"]["total"] == 100  # every check the store controls passed
    assert run["scorecard"]["fixes"] == []
    assert "paypal_button_found" in {n["check"] for n in run["scorecard"]["not_store_fault"]}
    with db.connect(server.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM orders WHERE status = 'COMPLETED'").fetchone()[0] == 0


@requires_browser
async def test_shopper_that_obeys_the_limit_and_never_pays_is_not_blamed(server, tmp_path):
    turns = [("open_page", {"url": "/store/checkout?sku=FH-MUG-01"}), ("read_text", {}),
             ("finish", {"outcome": "gave_up", "summary": "The total is over my limit."})]
    cassette = tmp_path / "obeys.json"
    cassette.write_text(json.dumps({"responses": [
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": f"c{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a)}}]}
        for i, (n, a) in enumerate(turns)]}))
    run = await checkout_run(server, cassette, budget=Decimal("20.00"))
    c = check(run, "paypal_button_found")
    assert (c["code"], c["cause"]) == ("over_budget", "environment")
    assert results(run)["paypal_button_found"] == 0 and run["order"] is None


@pytest.mark.parametrize("value,expected", [("30", "30.00"), ("30.5", "30.50"), ("$24.00", "24.00"), (" 0.01 ", "0.01"),
                                            (None, None), ("", None)])
def test_parse_budget_accepts_amounts(value, expected):
    got = parse_budget(value)
    assert (None if got is None else f"{got:.2f}") == expected


@pytest.mark.parametrize("value", ["abc", "0", "-5", "10.005", "NaN", "sNaN", "Infinity", "-Infinity", "10001", "1,000",
                                   "1E+30", "1e999999999", "1E-999999999"])
def test_parse_budget_refuses_bad_amounts(value):
    with pytest.raises(RunConfigError):
        parse_budget(value)


def test_goal_names_the_limit_only_when_there_is_one():
    assert "spending limit is $25.00" in goal_text("Mug", "http://x/store/", True, budget=Decimal("25.00"))
    assert "spending limit" not in goal_text("Mug", "http://x/store/", True)
    assert "spending limit" not in goal_text("Mug", "http://x/store/", False, budget=Decimal("25.00"))


@pytest.mark.parametrize("budget", ["abc", "0", "-1", "10.005", "99999"])
def test_api_refuses_bad_budgets_with_a_plain_message(tmp_path, budget, monkeypatch):
    monkeypatch.setattr(runs, "live_llm_configured", lambda: True)  # otherwise the missing LLM is refused first
    with TestClient(create_app(make_settings(tmp_path))) as c:
        c.cookies.set(COOKIE, new_token())
        r = c.post("/api/runs", json={"budget": budget})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["error"] == "RUN_CONFIG" and "spending limit" in detail["message"]


def test_budget_is_open_to_everyone_not_a_developer_option(tmp_path):
    with TestClient(create_app(make_settings(tmp_path))) as c:
        c.cookies.set(COOKIE, new_token())
        r = c.post("/api/runs", json={"store_url": "not a url", "budget": "30"})
        assert "only store_url" not in json.dumps(r.json()).lower()
        r = c.post("/api/runs", json={"store_url": "not a url", "max_steps": 5})
        assert "only store_url" in json.dumps(r.json()).lower()


@requires_browser
async def test_limit_is_checked_against_the_real_order_amount_not_the_page(server):
    # price_mismatch: the page shows 24.00 but the order is created for more. A limit between the two stops the
    # payment after the order exists and before approval, so nothing is captured.
    run = await checkout_run(server, "day3_checkout_flaws_off", flaws="price_mismatch", budget=Decimal("25.00"))
    assert run["status"] == "completed", run["error"]
    assert run["outcome"] == "blocked" and run["order"] is None
    c = check(run, "paypal_button_found")
    assert (c["passed"], c["code"], c["cause"]) == (0, "over_budget", "environment")
    assert Decimal(c["evidence"]["checkout_total"]) > Decimal("25.00")
    assert all(check(run, k)["status"] == "excluded" for k in ["payment_approved", "capture_completed", "payment_verified"])
    with db.connect(server.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM orders WHERE status = 'COMPLETED'").fetchone()[0] == 0


@requires_browser
async def test_other_prices_in_the_page_text_do_not_block_a_purchase_that_fits(server, monkeypatch):
    # Text like "Free shipping over $50" reads as a 50.00 price; the order itself is 24.00, within the 30.00 limit.
    from backend.app.agent import checks
    monkeypatch.setattr(checks, "checkout_total", lambda facts: Decimal("50.00"))
    run = await checkout_run(server, "day3_checkout_flaws_off", budget=Decimal("30.00"))
    assert run["outcome"] == "purchased" and run["order"]["capture_status"] == "COMPLETED"
    assert check(run, "payment_verified")["evidence"]["budget"]["within"] is True
