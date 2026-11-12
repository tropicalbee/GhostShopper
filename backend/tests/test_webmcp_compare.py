"""Browser agent vs WebMCP: the comparison on recorded runs, and who may ask for it. No network."""

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.agent.recorder import RunRecorder
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.webmcp.compare import PathCompareError, compare_paths, latest_of_path, latest_pair

from .test_agent_e2e import requires_browser
from .test_checkout_e2e import checkout_run, server  # noqa: F401  (server is a fixture)
from .test_webmcp_e2e import trace_of, webmcp_run

pytestmark = pytest.mark.anyio

PAID = "day3_checkout_flaws_off"
MISMATCH = {"stage": "store_order", "field": "status", "expected": "Paid", "actual": "Awaiting payment", "explanation": "x"}


def synthetic(path, outcome="purchased", agent_calls=4, mismatch=None, run_id=1, **extra) -> dict:
    tools = {"browser": "click", "webmcp": "shopping.getProduct"}[path]
    steps = [{"tool": tools, "args": {}} for _ in range(agent_calls)] + [{"tool": "finish", "args": {}}]
    cell = {"kind": "known", "value": "paid"}
    return {
        "id": run_id, "path": path, "outcome": outcome, "step_count": len(steps), "steps": steps,
        "store_url": "http://s/store/", "target_product": "Mug", "flaws_snapshot": {}, "order": None, "catalog_price": None,
        "started_at": "2026-01-01T00:00:00+00:00", "finished_at": "2026-01-01T00:00:30+00:00",
        "webmcp": {"llm_turns": agent_calls} if path == "webmcp" else None,
        "score": {"total": 49} if path == "browser" else None,
        "trace": {"stages": [{"key": "store_order", "cells": {"status": cell}}, {"key": "store_says", "cells": {"status": cell}}],
                  "links": [{"kind": "ok"}] * 4, "first_mismatch": mismatch},
        **extra,
    }


def test_the_verdict_says_how_many_calls_each_path_took_and_whether_they_agree():
    same = compare_paths(synthetic("browser", agent_calls=23, mismatch=MISMATCH), synthetic("webmcp", mismatch=MISMATCH))
    assert same["verdict"] == ("WebMCP bought in 4 tool calls; the browser agent took 23 steps. "
                               "Both paths hit the same first mismatch: the store order still says Awaiting payment.")
    assert same["browser"]["score"] == 49 and same["webmcp"]["score"] is None
    assert same["webmcp"]["llm_turns"] == 4 and same["browser"]["llm_turns"] is None
    assert same["browser"]["duration_s"] == 30.0 and same["webmcp"]["final"]["links_ok"] == 4
    assert "Both purchases reconcile" in compare_paths(synthetic("browser"), synthetic("webmcp"))["verdict"]
    one = compare_paths(synthetic("webmcp"), synthetic("browser", mismatch=MISMATCH))["verdict"]
    assert one.endswith("Only the browser path hit a mismatch: the store order still says Awaiting payment.")


def test_the_verdict_names_a_path_that_did_not_buy():
    verdict = compare_paths(synthetic("browser", outcome="blocked"), synthetic("webmcp"))["verdict"]
    assert verdict == "WebMCP bought in 4 tool calls; the browser agent did not buy (outcome: blocked)."


def test_two_checks_of_the_same_path_or_of_different_stores_do_not_compare():
    with pytest.raises(PathCompareError, match="one browser check with one WebMCP"):
        compare_paths(synthetic("webmcp"), synthetic("webmcp", run_id=2))
    with pytest.raises(PathCompareError, match="same store"):
        compare_paths(synthetic("webmcp"), synthetic("browser", store_url="http://other/"))


@requires_browser
async def test_both_paths_hit_the_same_first_mismatch_on_a_real_pair(server):  # noqa: F811
    browser = await checkout_run(server, PAID, flaws="never_marks_paid")
    webmcp = await webmcp_run(server, flaws="never_marks_paid")
    assert latest_pair(server.db_path) == (browser["id"], webmcp["id"])
    r = httpx.get(f"{server.url}/api/runs/{webmcp['id']}/compare-path")
    r.raise_for_status()
    result = r.json()
    assert result["verdict"].startswith("WebMCP bought in 4 tool calls; the browser agent took ")
    assert result["verdict"].endswith("Both paths hit the same first mismatch: the store order still says Awaiting payment.")
    assert result["browser"]["run_id"] == browser["id"] and result["webmcp"]["run_id"] == webmcp["id"]
    assert result["browser"]["handoff"] == "browser popup (PayPal button)" and result["webmcp"]["handoff"].startswith("WebMCP approval_url")
    assert result["webmcp"]["price"] == {"catalog": "24.00", "captured": "24.00"} and result["webmcp"]["score"] is None
    assert result["browser"]["score"] == 100 and result["webmcp"]["final"]["store_order_status"] == "awaiting_payment"
    assert httpx.get(f"{server.url}/api/runs/{browser['id']}/compare-path?other={webmcp['id']}").json()["verdict"] == result["verdict"]
    assert trace_of(server, webmcp)["first_mismatch"]["stage"] == "store_order"


@pytest.fixture
def client(tmp_path):
    settings = Settings(paypal_client_id="", paypal_client_secret="", database_path=tmp_path / "cp.db",
                        app_base_url="http://localhost:8000", paypal_mode="mock", dev_options=True)
    with TestClient(create_app(settings)) as c:
        yield c


def finished_run(db_path, path, owner) -> int:
    rec = RunRecorder.start(db_path, store_url="http://s/store/", goal="g", target_product="Mug", checkout=True,
                            paypal_mode="mock", flaws=None, llm="scripted", model=None, owner_hash=owner, path=path)
    rec.finish(status="completed", outcome="gave_up", step_count=0)
    return rec.run_id


def test_compare_path_follows_the_ownership_rules_of_the_other_run_endpoints(client):
    db_path = client.app.state.settings.database_path
    browser, webmcp = finished_run(db_path, "browser", "someone-else"), finished_run(db_path, "webmcp", "someone-else")
    for run_id in (browser, webmcp):
        assert client.get(f"/api/runs/{run_id}/compare-path?other={webmcp + browser - run_id}").status_code == 404
    shared_b, shared_w = finished_run(db_path, "browser", None), finished_run(db_path, "webmcp", None)
    assert client.get(f"/api/runs/{shared_b}/compare-path?other={shared_w}").status_code == 200
    assert client.get(f"/api/runs/{shared_b}/compare-path?other={webmcp}").status_code == 404  # someone else's check
    assert client.get(f"/api/runs/{shared_b}/compare-path").json()["webmcp"]["run_id"] == shared_w  # the latest of the other path
    assert latest_of_path(db_path, {"id": shared_w, "store_url": "http://s/store/", "owner_hash": None}, "browser") == shared_b
    assert client.get(f"/api/runs/{shared_w}/compare-path?other={shared_w}").status_code == 400


def test_compare_path_without_a_check_of_the_other_path_is_a_404(client):
    only = finished_run(client.app.state.settings.database_path, "webmcp", None)
    r = client.get(f"/api/runs/{only}/compare-path")
    assert r.status_code == 404 and r.json()["detail"]["error"] == "NO_OTHER_PATH"
