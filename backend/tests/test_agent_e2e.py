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
                        app_base_url="http://unused", dev_options=True)  # local test server, like localhost
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
    assert all(run["flaws_snapshot"][k] for k in ("price_as_image", "no_structured_data", "ambiguous_buttons", "extra_checkout_step"))
    r = results(run)
    assert r["product_found"] == 1 and r["checkout_reached"] == 1
    for flaw_check in ("price_in_text", "structured_data", "stock_readable", "clear_buy_button", "no_extra_steps"):
        assert r[flaw_check] == 0, flaw_check
    assert r["capture_completed"] is None  # payment not part of a Day 2 run
    # The classic flaws don't touch these, so they pass ...
    for ok in ("stock_consistent", "image_alt_text", "sale_claim_consistent", "buy_button_unobstructed"):
        assert r[ok] == 1, ok
    # ... and these can't be judged when no price is readable as text (not tested, 0 points).
    assert r["currency_stated"] is None and r["price_consistent"] is None
    # 5 product_found + 3+3+3 (stock_consistent, alt, sale) + 4 unobstructed + 6 checkout + 5 task = 29
    assert run["score"]["total"] == 29

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
    assert run["agent_report"] == {"claimed_outcome": "reached_checkout", "price": "$24.00", "in_stock": "In stock"}
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


# --- Robustness: step limit, loop detection, timeouts, clean give-up (all scored via task_completed) ---

def write_cassette(path, turns) -> "Path":
    import json

    path.write_text(json.dumps({"responses": [
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": f"c{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a)}}]}
        for i, (n, a) in enumerate(turns)]}))
    return path


async def run_turns(server, tmp_path, turns, flaws="off", llm=None, **cfg_overrides) -> dict:
    store_url = f"{server.url}/store/"
    await apply_flaws(store_url, flaws)
    cfg = RunConfig(store_url=store_url, db_path=server.db_path, runs_dir=server.runs_dir, **cfg_overrides)
    llm = llm or ReplayLLM(write_cassette(tmp_path / "turns.json", turns))
    return load_run(server.db_path, await run_shopper(cfg, llm))


def check_row(run, key):
    return next(c for c in run["checks"] if c["check_key"] == key)


@requires_browser
async def test_repeating_the_same_action_is_stopped_as_a_loop(server, tmp_path):
    turns = [("open_page", {"url": "/store/"})] + [("read_text", {})] * 3 + [("finish", {"outcome": "gave_up", "summary": "x"})]
    run = await run_turns(server, tmp_path, turns)
    assert run["status"] == "completed"
    assert (run["outcome"], run["end_reason"]) == ("gave_up", "agent_loop")
    assert len(run["steps"]) == 4  # stopped on the third identical read_text, before finish
    assert "Warning: you already did exactly this" in run["steps"][2]["observation"]
    task = check_row(run, "task_completed")
    assert (task["passed"], task["code"], task["cause"]) == (0, "agent_loop", "store")


@requires_browser
async def test_step_limit_ends_the_run_cleanly(server, tmp_path):
    run = await run_turns(server, tmp_path, [], llm=ReplayLLM(resolve_cassette("day2_flaws_off")), max_steps=3)
    assert (run["status"], run["outcome"], run["end_reason"]) == ("completed", "gave_up", "step_limit")
    assert run["step_count"] == 3
    assert check_row(run, "task_completed")["code"] == "step_limit"
    assert check_row(run, "product_found")["passed"] == 1  # what it did reach is still scored


@requires_browser
async def test_steps_that_time_out_stop_the_run(server, tmp_path):
    turns = [("open_page", {"url": "/store/"})] * 3 + [("finish", {"outcome": "gave_up", "summary": "x"})]
    run = await run_turns(server, tmp_path, turns, step_timeout_s=0.001)
    assert (run["outcome"], run["end_reason"]) == ("gave_up", "step_timeouts")
    assert all(s["ok"] == 0 and "timed out" in s["observation"] for s in run["steps"])
    assert check_row(run, "task_completed")["code"] == "step_timeouts"


@requires_browser
async def test_a_hung_llm_is_a_run_error_and_not_the_stores_fault(server, tmp_path):
    import asyncio

    class HungLLM:
        kind, model = "mock", "hung"

        async def complete(self, messages, tools):
            await asyncio.sleep(10)

    run = await run_turns(server, tmp_path, [], llm=HungLLM(), llm_timeout_s=0.2)
    assert (run["status"], run["outcome"]) == ("error", "error")
    assert "LLM call timed out" in run["error"]
    assert run["score"]["possible"] == 0  # nothing was the store's fault, nothing was tested
    assert check_row(run, "task_completed")["code"] == "run_error"


@requires_browser
async def test_agent_giving_up_is_a_clean_scored_outcome(server, tmp_path):
    turns = [("open_page", {"url": "/store/"}), ("finish", {"outcome": "gave_up", "summary": "Could not find it."})]
    run = await run_turns(server, tmp_path, turns)
    assert (run["status"], run["outcome"], run["end_reason"]) == ("completed", "gave_up", "finished")
    assert run["agent_report"]["claimed_outcome"] == "gave_up"
    task = check_row(run, "task_completed")
    assert (task["passed"], task["code"]) == (0, "agent_gave_up")
    assert check_row(run, "product_found")["code"] == "product_not_found"


@requires_browser
async def test_llm_claiming_success_does_not_change_the_outcome(server, tmp_path):
    turns = [("open_page", {"url": "/store/"}), ("finish", {"outcome": "purchased", "summary": "Bought it!"})]
    run = await run_turns(server, tmp_path, turns)
    assert run["outcome"] == "gave_up"  # decided by checks, not by the LLM's claim
    assert run["agent_report"]["claimed_outcome"] == "purchased"
