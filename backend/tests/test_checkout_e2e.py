"""Day 3 end-to-end: agent pays through the mock PayPal SDK/popup and the fake Orders client.

No PayPal servers are contacted (PAYPAL_MODE=mock).
"""

import json

import httpx
import pytest

from backend.app import db
from backend.app.agent.llm import ReplayLLM, resolve_cassette
from backend.app.agent.loop import RunConfig, run_shopper
from backend.app.agent.paypal_flow import MOCK_BUYER, PaymentConfigError, make_payment_handler
from backend.app.agent.recorder import load_run
from backend.app.agent.service import apply_flaws
from backend.app.config import Settings
from backend.app.main import create_app

from .live_server import LiveServer
from .test_agent_e2e import requires_browser

pytestmark = pytest.mark.anyio


@pytest.fixture
def server(tmp_path):
    settings = Settings(paypal_client_id="", paypal_client_secret="", database_path=tmp_path / "co.db",
                        app_base_url="http://unused", paypal_mode="mock", dev_options=True)  # local test server
    with LiveServer(create_app(settings)) as srv:
        srv.db_path = settings.database_path
        srv.runs_dir = tmp_path / "runs"
        yield srv


async def checkout_run(server, cassette, flaws="off", scenario="ok", checkout=True, hook=None, timeouts=None,
                       budget=None) -> dict:
    store_url = f"{server.url}/store/"
    async with httpx.AsyncClient() as http:
        (await http.put(f"{server.url}/mock-paypal/scenario", json={"scenario": scenario})).raise_for_status()
    snapshot = await apply_flaws(store_url, flaws)
    payment = (make_payment_handler("mock", store_url, server_mode="mock", server_configured=True,
                                    on_awaiting_human=hook) if checkout else None)
    if payment and timeouts:
        payment.timeouts = timeouts
    cfg = RunConfig(store_url=store_url, db_path=server.db_path, flaws=snapshot, runs_dir=server.runs_dir,
                    checkout=checkout, paypal_mode="mock" if checkout else "off", budget=budget)
    llm = ReplayLLM(cassette if hasattr(cassette, "read_text") else resolve_cassette(cassette))
    return load_run(server.db_path, await run_shopper(cfg, llm, payment))


def results(run) -> dict:
    return {c["check_key"]: c["passed"] for c in run["checks"]}


def check(run, key) -> dict:
    return next(c for c in run["checks"] if c["check_key"] == key)


@requires_browser
async def test_fixed_store_full_purchase_scores_100_and_records_the_order(server):
    run = await checkout_run(server, "day3_checkout_flaws_off")
    assert run["status"] == "completed", run["error"]
    assert run["outcome"] == "purchased"
    assert all(v == 1 for v in results(run).values()), results(run)
    assert run["score"]["total"] == 100

    order = run["order"]
    assert order["order_id"].startswith("MOCK") and order["run_id"] == run["id"]
    assert order["status"] == "COMPLETED" and order["capture_status"] == "COMPLETED"
    assert order["capture_id"].startswith("MOCKCAP")
    assert (order["amount"], order["gross_amount"], order["paypal_fee"], order["net_amount"]) == (
        "24.00", "24.00", "1.33", "22.67")  # 3.49% + $0.49 of $24.00
    cap = check(run, "capture_completed")["evidence"]
    assert cap["order_id"] == order["order_id"] and cap["paypal_fee"] == "1.33"
    pay_step = next(s for s in run["steps"] if s["tool"] == "pay_with_paypal")
    assert pay_step["ok"] == 1 and order["order_id"] in pay_step["observation"]


@requires_browser
async def test_buyer_credentials_never_reach_db_screenshots_or_observations(server):
    run = await checkout_run(server, "day3_checkout_flaws_off")
    assert run["outcome"] == "purchased"
    raw = server.db_path.read_bytes()
    for secret in (MOCK_BUYER.email, MOCK_BUYER.password):
        assert secret.encode() not in raw
        assert all(secret not in (s["observation"] or "") for s in run["steps"])
    # The only popup screenshot is taken before anything is typed.
    popup_shots = [p for p in server.runs_dir.rglob("*.png") if "popup" in p.name]
    assert [p.name for p in popup_shots] == ["paypal-popup-before-login.png"]


@requires_browser
async def test_bad_store_purchase_succeeds_but_scores_49(server):
    run = await checkout_run(server, "day3_checkout_flaws_on", flaws="on")
    assert run["status"] == "completed", run["error"]
    r = results(run)
    assert {k for k, v in r.items() if v == 0} == {
        "price_in_text", "structured_data", "stock_readable", "clear_buy_button", "no_extra_steps"}
    assert all(r[k] == 1 for k in ("paypal_button_found", "popup_opened", "payment_approved",
                                   "capture_completed", "payment_verified", "task_completed"))
    assert run["score"]["total"] == 49  # 29 browse points + 20 payment
    assert run["order"]["status"] == "COMPLETED"


@requires_browser
@pytest.mark.parametrize("scenario,failed,code,cause,score,possible", [
    # Store's fault: PayPal never rendered on its checkout.
    ("no_button", "paypal_button_found", "paypal_button_missing", "store", 75, 100),
    # Not the store's fault: excluded with every check they prevented, score renormalized.
    ("popup_blocked", "popup_opened", "popup_blocked_by_browser", "environment", 100, 79),
    ("approval_stuck", "payment_approved", "approval_timeout", "environment", 100, 82),
    ("seller_login", "payment_approved", "paypal_error_page", "environment", 100, 82),
    ("capture_declined", "capture_completed", "capture_declined", "environment", 100, 85),
])
async def test_checkout_failures_are_scored_by_cause(server, scenario, failed, code, cause, score, possible):
    run = await checkout_run(server, "day3_checkout_payment_fails", scenario=scenario)
    assert run["status"] == "completed", run["error"]
    assert run["outcome"] == "blocked"
    c = check(run, failed)
    assert (c["passed"], c["code"], c["cause"]) == (0, code, cause)
    assert c["evidence"]["screenshot"].endswith(f"check-{failed}.png")
    assert (run["score"]["total"], run["score"]["possible"]) == (score, possible)
    payment_order = ["paypal_button_found", "popup_opened", "payment_approved", "capture_completed", "payment_verified"]
    later = payment_order[payment_order.index(failed) + 1:]
    assert all(results(run)[k] is None for k in later)  # never reached, so not tested
    expected_later = "excluded" if cause == "environment" else "not_tested"
    assert all(check(run, k)["status"] == expected_later for k in later)
    task = check(run, "task_completed")
    assert task["code"] == ("blocked_by_environment" if cause == "environment" else "payment_failed")
    pay_step = next(s for s in run["steps"] if s["tool"] == "pay_with_paypal")
    assert pay_step["observation"].startswith("Payment failed:")
    card = run["scorecard"]
    if cause == "environment":
        assert failed in {n["check"] for n in card["not_store_fault"]}
        assert card["fixes"] == []  # nothing for the merchant to fix
    else:
        assert card["fixes"][0]["check"] == failed and "paypal-button" in card["fixes"][0]["fix"]
    if scenario == "capture_declined":
        assert "INSTRUMENT_DECLINED" in c["reason"]
        assert run["order"] is None  # not linked: never captured
        assert any("INSTRUMENT_DECLINED" in line and "Excluded from the score" in line for line in card["summary"])
    if scenario == "popup_blocked":
        assert "browser blocked it" in c["reason"]
    if scenario == "seller_login":
        assert c["evidence"]["issue"] == "CANNOT_PAY_SELF"
        assert "seller's own account" in c["reason"]


@pytest.mark.parametrize("url,issue", [
    # Codes as PayPal's sandbox sent them (base64 of the issue name, unpadded).
    ("https://www.sandbox.paypal.com/checkoutweb/genericError?code=Q0FOTk9UX1BBWV9TRUxG", "CANNOT_PAY_SELF"),
    ("https://www.sandbox.paypal.com/checkoutweb/genericError?code=VU5TVVBQT1JURURfUEFZ", "UNSUPPORTED_PAY"),
    ("https://www.sandbox.paypal.com/checkoutweb/genericError?code=%%%", "UNKNOWN"),
    ("https://www.sandbox.paypal.com/checkoutweb/genericError", "UNKNOWN"),
    ("https://www.sandbox.paypal.com/checkoutnow?token=ABC", None),
])
def test_error_page_issue_is_decoded_from_the_url(url, issue):
    from backend.app.agent.paypal_flow import error_page_issue

    assert error_page_issue(url) == issue


@requires_browser
async def test_extra_verification_pauses_for_a_human_then_resumes_and_captures(server):
    seen = {}

    async def human(info, popup):
        # What a person would do in the PayPal window. The agent itself never touches this step.
        seen["info"] = info
        seen["status"] = load_run(server.db_path, 1)["status"]
        await popup.fill("#otpCode", "123456")
        await popup.click("#btnVerify")
        await popup.click("#payment-submit-btn")

    run = await checkout_run(server, "day3_checkout_flaws_off", scenario="verification_required", hook=human)
    assert seen["status"] == "awaiting_human"
    assert "verification" in seen["info"]["reason"] and seen["info"]["stage"] == "blocker"
    assert run["status"] == "completed" and run["awaiting"] is None
    approved = check(run, "payment_approved")
    assert approved["passed"] == 1 and approved["evidence"]["approved_by"] == "human"
    assert check(run, "capture_completed")["passed"] == 1
    assert check(run, "payment_verified")["passed"] == 1
    assert run["outcome"] == "purchased" and run["score"]["total"] == 100
    assert "A human completed PayPal's extra check" in next(
        s for s in run["steps"] if s["tool"] == "pay_with_paypal")["observation"]


@requires_browser
async def test_captcha_with_nobody_to_approve_is_not_the_stores_fault(server):
    from backend.app.agent.paypal_flow import MOCK_TIMEOUTS, Timeouts

    short = Timeouts(**{**MOCK_TIMEOUTS.__dict__, "human_s": 2})
    run = await checkout_run(server, "day3_checkout_payment_fails", scenario="captcha", timeouts=short)
    c = check(run, "payment_approved")
    assert (c["passed"], c["code"], c["cause"]) == (0, "human_approval_timeout", "environment")
    assert run["status"] == "completed" and run["awaiting"] is None
    assert (run["score"]["total"], run["score"]["possible"]) == (100, 82)


@requires_browser
@pytest.mark.parametrize("scenario,code,cause,score,possible", [
    ("capture_amount_mismatch", "capture_amount_mismatch", "store", 95, 100),
    ("fee_mismatch", "fee_inconsistent", "environment", 100, 95),
])
async def test_verification_mismatches_are_scored_checks(server, scenario, code, cause, score, possible):
    run = await checkout_run(server, "day3_checkout_flaws_off", scenario=scenario)
    v = check(run, "payment_verified")
    assert (v["passed"], v["code"], v["cause"]) == (0, code, cause)
    assert v["evidence"]["mismatches"][0]["code"] == code
    assert check(run, "capture_completed")["passed"] == 1
    assert (run["score"]["total"], run["score"]["possible"]) == (score, possible)


@requires_browser
async def test_browse_run_cannot_press_the_payment_button(server, tmp_path):
    turns = [("open_page", {"url": "/store/checkout?sku=FH-MUG-01"}), ("read_text", {}), ("find_elements", {}),
             ("click", {"element_id": "e4"}), ("finish", {"outcome": "gave_up", "summary": "x"})]
    cassette = tmp_path / "press.json"
    cassette.write_text(json.dumps({"responses": [
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": f"c{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a)}}]}
        for i, (n, a) in enumerate(turns)]}))
    await apply_flaws(f"{server.url}/store/", "off")
    run = await checkout_run(server, cassette, checkout=False)
    listing = run["steps"][2]["observation"]
    assert "e4 paypal-button 'PayPal'" in listing
    assert run["steps"][3]["ok"] == 0
    assert "Payment is not part of this run" in run["steps"][3]["observation"]
    with db.connect(server.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0


def test_live_checkout_refuses_without_credentials(monkeypatch):
    monkeypatch.delenv("SANDBOX_BUYER_EMAIL", raising=False)
    monkeypatch.delenv("SANDBOX_BUYER_PASSWORD", raising=False)
    with pytest.raises(PaymentConfigError, match="SANDBOX_BUYER_EMAIL"):
        make_payment_handler("sandbox", "http://x/store/", server_mode="sandbox", server_configured=True)
    with pytest.raises(PaymentConfigError, match="PAYPAL_CLIENT_ID"):
        make_payment_handler("sandbox", "http://x/store/", server_mode="sandbox", server_configured=False)


def test_checkout_mode_must_match_the_server(monkeypatch):
    with pytest.raises(PaymentConfigError, match="PAYPAL_MODE=mock"):
        make_payment_handler("sandbox", "http://x/store/", server_mode="mock", server_configured=True)
    with pytest.raises(PaymentConfigError, match="PAYPAL_MODE=sandbox"):
        make_payment_handler("mock", "http://x/store/", server_mode="sandbox", server_configured=True)


def test_live_handler_reads_only_the_sandbox_buyer_env(monkeypatch):
    monkeypatch.setenv("SANDBOX_BUYER_EMAIL", "env-buyer@example.test")
    monkeypatch.setenv("SANDBOX_BUYER_PASSWORD", "env-pass")
    h = make_payment_handler("sandbox", "http://x/store/", server_mode="sandbox", server_configured=True)
    assert h.secrets == ("env-buyer@example.test", "env-pass")
    assert "env-pass" not in repr(h._buyer)


@requires_browser
async def test_account_wall_blocks_payment_with_the_right_failure(server):
    run = await checkout_run(server, "day3_checkout_flaws_off", flaws="no_guest_checkout")
    assert run["status"] == "completed", run["error"]
    assert run["order"] is None
    c = check(run, "paypal_button_found")
    assert (c["passed"], c["code"], c["cause"]) == (0, "account_required", "store")
    assert results(run)["capture_completed"] is None
    assert run["outcome"] != "purchased"
