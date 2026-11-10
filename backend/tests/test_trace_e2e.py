"""The purchase trace on real mock runs: the agent pays through the mock PayPal, and each purchase flaw shows up
as the first place the five records disagree. Nothing here touches the readiness score."""

import httpx
import pytest

from backend.app.agent.llm import ReplayLLM, resolve_cassette
from backend.app.agent.loop import RunConfig, run_shopper
from backend.app.agent.recorder import load_run
from backend.app.agent.service import apply_flaws
from backend.app.agent.vault_flow import make_vault_handler
from backend.app.config import Settings

from .test_agent_e2e import requires_browser
from .test_checkout_e2e import checkout_run, server  # noqa: F401  (server is a fixture)
from .test_vault import mock_settings, save_token

pytestmark = pytest.mark.anyio

PAID = "day3_checkout_flaws_off"
FAILS = "day3_checkout_payment_fails"


def trace_of(server, run) -> dict:
    r = httpx.get(f"{server.url}/api/runs/{run['id']}")
    r.raise_for_status()
    return r.json()["trace"]


def stage(trace, key) -> dict:
    return next(s for s in trace["stages"] if s["key"] == key)


def says(trace) -> str:
    return stage(trace, "store_says")["cells"]["status"]["value"]


def stages_of(trace, field) -> dict:
    return {s["key"]: s["cells"][field]["value"] for s in trace["stages"]}


@requires_browser
async def test_a_healthy_purchase_agrees_at_every_stage(server):  # noqa: F811
    run = await checkout_run(server, PAID)
    assert run["outcome"] == "purchased" and run["score"]["total"] == 100
    trace = trace_of(server, run)
    assert trace["mismatches"] == [] and trace["first_mismatch"] is None
    assert trace["counts"] == {"mismatch": 0, "unknown": 0}
    assert stages_of(trace, "status") == {
        "agent_wanted": "buy", "store_order": "paid", "paypal_order": "COMPLETED", "paypal_capture": "COMPLETED",
        "store_says": "paid"}
    assert stages_of(trace, "product")["paypal_order"] == "FH-MUG-01"
    assert stages_of(trace, "amount")["paypal_capture"] == "24.00"
    read = next(s for s in run["steps"] if s["tool"] == "read_order_status")
    assert read["ok"] == 1 and "Status: Paid" in read["observation"] and read["screenshot_path"]
    assert stage(trace, "store_says")["source"] == f"order page, step {read['idx']}"
    assert stage(trace, "store_order")["source"] == "#1042"
    assert stage(trace, "paypal_order")["source"] == run["order"]["order_id"]
    assert [(link["key"], link["kind"]) for link in trace["links"]] == [
        ("store_to_paypal_order", "ok"), ("paypal_order_to_store", "ok"),
        ("capture_to_paypal_order", "ok"), ("store_to_capture", "ok")]
    back = next(link for link in trace["links"] if link["key"] == "paypal_order_to_store")
    assert back["expected"] == back["actual"] == "1042"


@requires_browser
async def test_never_marks_paid_shows_a_paid_capture_and_an_unpaid_store(server):  # noqa: F811
    run = await checkout_run(server, PAID, flaws="never_marks_paid")
    assert run["outcome"] == "purchased" and run["score"]["total"] == 100  # the score does not see it
    trace = trace_of(server, run)
    first = trace["first_mismatch"]
    assert (first["stage"], first["field"], first["actual"]) == ("store_order", "status", "Awaiting payment")
    assert stages_of(trace, "status")["paypal_capture"] == "COMPLETED" and says(trace) == "awaiting_payment"
    assert [m["stage"] for m in trace["mismatches"]] == ["store_order", "store_says"]


@requires_browser
async def test_declined_payment_is_a_clean_failure_on_a_fixed_store(server):  # noqa: F811
    run = await checkout_run(server, FAILS, scenario="capture_declined")
    trace = trace_of(server, run)
    assert stages_of(trace, "status")["store_order"] == "payment_failed" and says(trace) == "payment_failed"
    assert stages_of(trace, "status")["paypal_capture"] == "INSTRUMENT_DECLINED"
    assert trace["mismatches"] == []


@requires_browser
async def test_declined_marked_paid_tells_the_buyer_it_worked(server):  # noqa: F811
    run = await checkout_run(server, FAILS, flaws="declined_marked_paid", scenario="capture_declined")
    trace = trace_of(server, run)
    assert stages_of(trace, "status")["store_order"] == "paid" and says(trace) == "paid"
    assert trace["first_mismatch"]["stage"] == "store_order" and trace["first_mismatch"]["actual"] == "Paid"
    assert stage(trace, "paypal_capture")["cells"]["amount"]["kind"] == "unknown"


@requires_browser
async def test_a_cancelled_payment_is_a_clean_failure_on_a_fixed_store(server):  # noqa: F811
    run = await checkout_run(server, FAILS, scenario="buyer_cancels")
    trace = trace_of(server, run)
    assert stages_of(trace, "status")["store_order"] == "cancelled" and says(trace) == "cancelled"
    assert stage(trace, "paypal_capture")["cells"]["status"]["kind"] == "not_reached"
    assert trace["mismatches"] == []


@requires_browser
async def test_success_after_cancel_confirms_an_order_nobody_paid(server):  # noqa: F811
    run = await checkout_run(server, FAILS, flaws="success_after_cancel", scenario="buyer_cancels")
    trace = trace_of(server, run)
    assert stages_of(trace, "status")["store_order"] == "confirmed" and says(trace) == "confirmed"
    first = trace["first_mismatch"]
    assert (first["stage"], first["actual"]) == ("store_order", "Confirmed")
    assert stage(trace, "paypal_capture")["cells"]["status"]["kind"] == "not_reached"


@requires_browser
async def test_the_agent_retries_once_and_a_fixed_store_keeps_one_order(server):  # noqa: F811
    run = await checkout_run(server, PAID, scenario="first_attempt_fails")
    assert run["outcome"] == "purchased"
    pay = next(s for s in run["steps"] if s["tool"] == "pay_with_paypal")
    assert "paid again once" in pay["observation"]
    trace = trace_of(server, run)
    assert stage(trace, "store_order")["source"] == "#1042"
    assert trace["mismatches"] == [] and says(trace) == "paid"


@requires_browser
async def test_duplicate_on_retry_leaves_two_orders_for_one_purchase(server):  # noqa: F811
    run = await checkout_run(server, PAID, flaws="duplicate_on_retry", scenario="first_attempt_fails")
    assert run["outcome"] == "purchased"
    trace = trace_of(server, run)
    first = trace["first_mismatch"]
    assert (first["stage"], first["field"], first["expected"], first["actual"]) == (
        "store_order", "status", "1 order", "2 orders")
    assert stage(trace, "store_order")["source"] == "#1042, #1043"
    assert stages_of(trace, "status")["store_order"] == "paid"


@requires_browser
async def test_a_run_that_never_pays_has_a_trace_that_stops_before_payment(server):  # noqa: F811
    run = await checkout_run(server, "day2_flaws_off", checkout=False)
    trace = trace_of(server, run)
    assert {c["kind"] for key in ("store_order", "paypal_order", "paypal_capture", "store_says")
            for c in stage(trace, key)["cells"].values()} == {"not_reached"}
    assert trace["mismatches"] == [] and not any(s["tool"] == "read_order_status" for s in run["steps"])


@requires_browser
async def test_the_saved_paypal_payment_makes_the_same_trace(server):  # noqa: F811
    settings = Settings(**{**mock_settings(server.db_path.parent).__dict__, "database_path": server.db_path})
    await save_token(settings)
    store_url = f"{server.url}/store/"
    snapshot = await apply_flaws(store_url, "never_marks_paid")
    payment = make_vault_handler("mock", store_url, server.db_path, server_mode="mock", server_configured=True)
    cfg = RunConfig(store_url=store_url, db_path=server.db_path, flaws=snapshot, runs_dir=server.runs_dir,
                    checkout=True, paypal_mode="mock")
    run = load_run(server.db_path, await run_shopper(cfg, ReplayLLM(resolve_cassette("day3_checkout_vault")), payment))
    assert run["outcome"] == "purchased"
    trace = trace_of(server, run)
    assert stage(trace, "store_order")["source"] == "#1042"
    assert says(trace) == "awaiting_payment" and stages_of(trace, "status")["paypal_capture"] == "COMPLETED"
    assert trace["first_mismatch"]["stage"] == "store_order"
    assert {link["kind"] for link in trace["links"]} == {"ok"}  # the saved-PayPal path links the records too
