"""End-to-end: real agent loop + real Playwright browser + real store, with a replayed (mock) LLM."""

from pathlib import Path

import pytest

from backend.app.agent.llm import ReplayLLM, resolve_cassette
from backend.app.agent.loop import RunConfig, run_shopper
from backend.app.agent.recorder import load_run
from backend.app.agent.service import apply_flaws
from backend.app.config import Settings
from backend.app.main import create_app

from .live_server import LiveServer

pytestmark = pytest.mark.anyio


def _chromium_available() -> bool:
    import os

    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            p.chromium.launch(channel=os.getenv("PLAYWRIGHT_CHANNEL") or None).close()
        return True
    except Exception:
        return False


requires_browser = pytest.mark.skipif(not _chromium_available(), reason="Playwright Chromium not installed")


@pytest.fixture
def server(tmp_path):
    settings = Settings(paypal_client_id="", paypal_client_secret="", database_path=tmp_path / "e2e.db",
                        app_base_url="http://unused")
    with LiveServer(create_app(settings)) as srv:
        srv.db_path = settings.database_path
        srv.runs_dir = tmp_path / "runs"
        yield srv


async def run_cassette(server, cassette: str, flaws: str) -> dict:
    store_url = f"{server.url}/store/"
    snapshot = await apply_flaws(store_url, flaws)
    cfg = RunConfig(store_url=store_url, db_path=server.db_path, flaws=snapshot, runs_dir=server.runs_dir)
    run_id = await run_shopper(cfg, ReplayLLM(resolve_cassette(cassette)))
    return load_run(server.db_path, run_id)


def results(run) -> dict:
    return {c["check_key"]: c["passed"] for c in run["checks"]}


@requires_browser
async def test_bad_store_reaches_checkout_with_every_flaw_logged(server):
    run = await run_cassette(server, "day2_flaws_on", "on")
    assert run["status"] == "completed", run["error"]
    assert run["outcome"] == "reached_checkout"
    assert run["flaws_snapshot"] == {k: True for k in run["flaws_snapshot"]}
    r = results(run)
    assert r["product_found"] == 1 and r["checkout_reached"] == 1
    for flaw_check in ("price_in_text", "structured_data", "stock_readable", "clear_buy_button", "no_extra_steps"):
        assert r[flaw_check] == 0, flaw_check
    assert r["capture_completed"] is None  # payment not part of a Day 2 run
    assert run["score"]["total"] == 20

    failed = {c["check_key"]: c for c in run["checks"] if c["passed"] == 0}
    assert failed["price_in_text"]["evidence"]["selector"].endswith("img.price-img")
    assert failed["clear_buy_button"]["evidence"]["selector"].endswith("div.actions > div.act.act-a")
    assert failed["no_extra_steps"]["evidence"]["url"].endswith("/store/checkout/details?sku=FH-MUG-01")
    for c in failed.values():
        assert Path(c["evidence"]["screenshot"]).is_file()
    assert len(run["steps"]) == 14
    assert all(Path(s["screenshot_path"]).is_file() for s in run["steps"])
    # The wrong turn is visible in the log.
    assert "Pour-Over Coffee Dripper" in run["steps"][5]["observation"]


@requires_browser
async def test_fixed_store_passes_every_browse_check(server):
    run = await run_cassette(server, "day2_flaws_off", "off")
    assert run["status"] == "completed", run["error"]
    r = results(run)
    assert all(r[k] == 1 for k in ("product_found", "price_in_text", "structured_data", "stock_readable",
                                   "clear_buy_button", "no_extra_steps", "checkout_reached"))
    assert run["score"]["total"] == 80  # payment (20) not tested in a Day 2 run
    assert run["agent_report"] == {"price": "$24.00", "in_stock": "In stock"}
    assert len(run["steps"]) == 8


@requires_browser
async def test_jumping_straight_to_checkout_does_not_count_as_finding_the_product(server, tmp_path):
    import json

    cassette = tmp_path / "c.json"
    turns = [("open_page", {"url": "/store/checkout?sku=FH-MUG-01"}), ("find_elements", {}),
             ("finish", {"outcome": "gave_up", "summary": "x"})]
    cassette.write_text(json.dumps({"responses": [
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": f"c{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a)}}]}
        for i, (n, a) in enumerate(turns)]}))
    store_url = f"{server.url}/store/"
    await apply_flaws(store_url, "off")
    cfg = RunConfig(store_url=store_url, db_path=server.db_path, runs_dir=server.runs_dir)
    run = load_run(server.db_path, await run_shopper(cfg, ReplayLLM(cassette)))
    assert run["status"] == "completed"
    assert results(run)["product_found"] == 0  # never visited the product page


@requires_browser
async def test_exhausted_cassette_is_an_explicit_error(server, tmp_path):
    import json

    cassette = tmp_path / "short.json"
    cassette.write_text(json.dumps({"responses": [
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "open_page", "arguments": '{"url": "/store/"}'}}]}]}))
    cfg = RunConfig(store_url=f"{server.url}/store/", db_path=server.db_path, runs_dir=server.runs_dir)
    run = load_run(server.db_path, await run_shopper(cfg, ReplayLLM(cassette)))
    assert run["status"] == "error"
    assert "CassetteExhausted" in run["error"]
    assert run["score"]["total"] == 0
