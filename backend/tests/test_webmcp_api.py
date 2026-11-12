"""WebMCP runs over the API and the external (PayPal showcase) demo: request rules, the trace and the outcome. No network."""


import pytest
from fastapi.testclient import TestClient

from backend.app.agent.service import RunConfigError, RunRequest, resolve_target
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.trace import EXTERNAL_REASON, build_trace
from backend.app.webmcp.service import prepare_webmcp
from backend.app.webmcp.shopper import EXTERNAL_DEMO_LABEL, PriceWatch, WebMCPConfig, _outcome, run_webmcp_shopper
from backend.app.webmcp.tools import PAYPAL_SHOWCASE_URL

pytestmark = pytest.mark.anyio


@pytest.fixture
def deployed(tmp_path, monkeypatch):
    monkeypatch.delenv("KERNEL_API_KEY", raising=False)
    settings = Settings(paypal_client_id="", paypal_client_secret="", database_path=tmp_path / "api.db",
                        app_base_url="https://demo.example", paypal_mode="mock", dev_options=False)
    with TestClient(create_app(settings), base_url="https://demo.example") as c:
        yield c


def start(client, **body):
    return client.post("/api/runs", json=body)


def test_path_and_store_are_open_options_but_must_make_sense(deployed):
    assert start(deployed, store="paypal_showcase").json()["detail"]["message"] == "A store can only be chosen for WebMCP checks."
    r = start(deployed, path="webmcp", store_url="https://shop.example")
    assert r.status_code == 400 and "not on a pasted link" in r.json()["detail"]["message"]
    assert start(deployed, path="webmcp", llm="scripted").json()["detail"]["message"].startswith("Only store_url can be set")


def test_the_showcase_needs_a_browser_a_person_can_reach_and_the_sandbox_buyer(deployed, monkeypatch):
    monkeypatch.delenv("SANDBOX_BUYER_EMAIL", raising=False)
    r = start(deployed, path="webmcp", store="paypal_showcase")
    assert r.status_code == 400 and r.json()["detail"]["error"] == "RUN_CONFIG"
    message = r.json()["detail"]["message"]
    assert "KERNEL_API_KEY" in message and "SANDBOX_BUYER_EMAIL" in message and "PAYPAL_CLIENT_ID" not in message


async def test_the_showcase_target_is_paypals_page_and_never_a_live_store():
    target = await resolve_target(RunRequest(path="webmcp", store="paypal_showcase"), "http://localhost:8000")
    assert target.url == PAYPAL_SHOWCASE_URL and target.demo is False


def test_payment_on_the_showcase_is_sandbox_only_and_never_replayed():
    for bad, message in ((dict(paypal="mock"), "sandbox"), (dict(paypal="sandbox", llm="mock"), "Replayed"),
                         (dict(paypal="sandbox", llm="scripted", flaws="on"), "flaws")):
        with pytest.raises(RunConfigError, match=message):
            prepare_webmcp(RunRequest(path="webmcp", store="paypal_showcase", **bad), PAYPAL_SHOWCASE_URL)


async def test_the_external_demo_flag_is_refused_anywhere_but_on_the_showcase(tmp_path):
    for url, mode in (("https://shop.example/", "sandbox"), (PAYPAL_SHOWCASE_URL, "mock")):
        cfg = WebMCPConfig(store_url=url, db_path=tmp_path / "x.db", external_demo=True, paypal_mode=mode)
        with pytest.raises(ValueError, match="only runs on PayPal's own showcase"):
            await run_webmcp_shopper(cfg, None, None)


def test_the_showcase_trace_is_unknown_with_a_reason_and_carries_the_price_check():
    run = {"live": False, "catalog_price": None, "steps": [], "webmcp": {
        "external_demo": True, "label": EXTERNAL_DEMO_LABEL, "price_consistency": {"consistent": True, "unit_prices": {"search": "25.00"}}}}
    trace = build_trace(run, None, [], None)
    stages = {s["key"]: s for s in trace["stages"]}
    for key in ("store_order", "paypal_order", "paypal_capture", "store_says"):
        assert {c["kind"] for c in stages[key]["cells"].values()} == {"unknown"}
        assert stages[key]["cells"]["status"]["reason"] == EXTERNAL_REASON
    assert {link["kind"] for link in trace["links"]} == {"n/a"} and trace["mismatches"] == []
    assert trace["price_consistency"]["consistent"] is True
    assert "Not GhostShopper-integrated" in EXTERNAL_DEMO_LABEL and "tool responses" in EXTERNAL_DEMO_LABEL


def test_price_consistency_compares_the_unit_price_every_tool_quoted():
    watch = PriceWatch()
    watch.search({"products": [{"product_id": "A", "price": {"value": "25.00", "currency_code": "USD"}}, {"product_id": "B", "price": "9"}]})
    watch.product({"product": {"id": "A", "price": 25}})
    watch.checkout({"product_id": "A", "quantity": 2, "amount": {"value": "50.00", "currency_code": "USD"}})
    watch.capture({"amount": {"value": "50.00"}})
    report = watch.report()
    assert report["unit_prices"] == {"search": "25.00", "product": "25.00", "checkout": "25.00", "capture": "25.00"}
    assert report["consistent"] is True and report["quantity"] == 2
    watch.capture({"amount": {"value": "56.00"}})
    assert watch.report()["consistent"] is False
    assert PriceWatch().report()["consistent"] is None  # nothing readable: unknown, never guessed


def test_the_outcome_comes_from_the_tool_results_not_from_what_the_llm_claims(tmp_path):
    cfg = WebMCPConfig(store_url=PAYPAL_SHOWCASE_URL, db_path=tmp_path / "o.db", external_demo=True, paypal_mode="sandbox")
    assert _outcome(cfg, {"capture_id": "C1"}, {"approved": True}, None, "O1") == "purchased"
    assert _outcome(cfg, None, {"approved": False}, None, None) == "blocked"
    assert _outcome(cfg, None, None, None, None) == "gave_up"
    assert _outcome(cfg, {"capture_id": "C1"}, {"approved": True}, "boom", "O1") == "error"


def test_price_watch_reads_the_shapes_paypals_showcase_really_sends():
    watch = PriceWatch()
    watch.search({"products": [
        {"productId": "P-1", "title": "Starbucks Coffee", "price": {"currency": "USD", "amount": "25.00"}, "availability": "IN_STOCK"},
        {"productId": "P-2", "title": "Hulu Gift Card", "price": {"currency": "USD", "amount": "50.00"}}], "total": 2})
    watch.product({"product": {"productId": "P-2", "title": "Hulu Gift Card", "price": {"currency": "USD", "amount": "50.00"}}})
    watch.checkout({"cart_id": "c1", "checkout_mode": "external", "approval_url": "https://www.sandbox.paypal.com/checkoutnow?token=T",
                    "order_id": "T", "summary": {"subtotal": {"currency": "USD", "amount": "50.00"}, "total": {"currency": "USD", "amount": "50.00"}},
                    "items": [{"productId": "P-2", "title": "Hulu Gift Card"}]}, {"product_id": "P-2"})
    watch.capture({"cart_id": "c1", "status": "COMPLETED", "order_id": None})
    report = watch.report()
    assert report["unit_prices"] == {"search": "50.00", "product": "50.00", "checkout": "50.00", "capture": None}  # not products[0]
    assert report["consistent"] is True
    assert watch.bought() == {"product_id": "P-2", "title": "Hulu Gift Card"}


def test_price_consistency_is_unknown_with_fewer_than_two_prices():
    watch = PriceWatch()
    watch.checkout({"summary": {"total": {"currency": "USD", "amount": "25.00"}}}, {"product_id": "P-1"})
    assert watch.report()["unit_prices"]["checkout"] == "25.00" and watch.report()["consistent"] is None
