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
                        app_base_url="http://unused", paypal_mode="mock")
    with LiveServer(create_app(settings)) as srv:
        srv.db_path = settings.database_path
        srv.runs_dir = tmp_path / "runs"
        yield srv


async def checkout_run(server, cassette, flaws="off", scenario="ok", checkout=True) -> dict:
    store_url = f"{server.url}/store/"
    async with httpx.AsyncClient() as http:
        (await http.put(f"{server.url}/mock-paypal/scenario", json={"scenario": scenario})).raise_for_status()
    snapshot = await apply_flaws(store_url, flaws)
    payment = make_payment_handler("mock", store_url, server_mode="mock", server_configured=True) if checkout else None
    cfg = RunConfig(store_url=store_url, db_path=server.db_path, flaws=snapshot, runs_dir=server.runs_dir,
                    checkout=checkout, paypal_mode="mock" if checkout else "off")
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
async def test_bad_store_purchase_succeeds_but_scores_40(server):
    run = await checkout_run(server, "day3_checkout_flaws_on", flaws="on")
    assert run["status"] == "completed", run["error"]
    r = results(run)
    assert [k for k, v in r.items() if v == 1] == [
        "product_found", "checkout_reached", "paypal_button_found", "popup_opened", "payment_approved", "capture_completed"]
    assert run["score"]["total"] == 40
    assert run["order"]["status"] == "COMPLETED"


@requires_browser
@pytest.mark.parametrize("scenario,failed,score", [
    ("no_button", "paypal_button_found", 80),
    ("popup_blocked", "popup_opened", 85),
    ("approval_stuck", "payment_approved", 90),
    ("capture_declined", "capture_completed", 95),
])
async def test_checkout_failures_are_scored_checks(server, scenario, failed, score):
    run = await checkout_run(server, "day3_checkout_payment_fails", scenario=scenario)
    assert run["status"] == "completed", run["error"]
    c = check(run, failed)
    assert c["passed"] == 0
    assert c["evidence"]["screenshot"].endswith(f"check-{failed}.png")
    assert run["score"]["total"] == score
    payment_order = ["paypal_button_found", "popup_opened", "payment_approved", "capture_completed"]
    later = payment_order[payment_order.index(failed) + 1:]
    assert all(results(run)[k] is None for k in later)  # never reached, so not tested
    pay_step = next(s for s in run["steps"] if s["tool"] == "pay_with_paypal")
    assert pay_step["observation"].startswith("Payment failed:")
    if scenario == "capture_declined":
        assert "INSTRUMENT_DECLINED" in c["reason"]
        assert run["order"] is None  # not linked: never captured
    if scenario == "popup_blocked":
        assert "Popup blocked" in c["reason"]


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
