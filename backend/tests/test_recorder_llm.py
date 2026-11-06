import json

import httpx
import pytest

from backend.app import db
from backend.app.agent.llm import CassetteExhausted, GroqLLM, LLMConfigError, ReplayLLM, make_llm
from backend.app.agent.recorder import Redactor, RunRecorder, load_run
from backend.app.scoring import CHECKS, compute_score

SECRET_EMAIL = "buyer-secret@example.test"
SECRET_PASS = "hunter2-very-secret"


def start(tmp_path, **kw):
    return RunRecorder.start(
        tmp_path / "t.db", store_url="http://shop/", goal="g", target_product="Mug", checkout=True,
        paypal_mode="mock", flaws={"price_as_image": True}, llm="mock", model="m", **kw,
    )


def test_redactor_replaces_every_secret():
    r = Redactor([SECRET_EMAIL, SECRET_PASS, ""])
    assert r(f"login {SECRET_EMAIL} / {SECRET_PASS}") == "login [REDACTED] / [REDACTED]"
    assert SECRET_PASS not in r.json({"nested": [SECRET_PASS]})


def test_secrets_never_reach_the_database(tmp_path):
    rec = start(tmp_path, secrets=[SECRET_EMAIL, SECRET_PASS])
    step = rec.add_step(idx=0, tool="pay_with_paypal", args={"x": SECRET_EMAIL}, thought=f"use {SECRET_PASS}",
                        observation=f"typed {SECRET_EMAIL}", ok=True, url=f"http://pp/?e={SECRET_EMAIL}",
                        screenshot_path=None, duration_ms=1)
    rec.record_check("payment_approved", False, f"login failed for {SECRET_EMAIL}", {"note": SECRET_PASS}, step)
    rec.finish(status="completed", outcome="blocked", step_count=1, summary=SECRET_PASS, report={"e": SECRET_EMAIL})
    raw = (tmp_path / "t.db").read_bytes()
    assert SECRET_EMAIL.encode() not in raw
    assert SECRET_PASS.encode() not in raw


def test_recorder_redacts_text_bound_for_the_llm(tmp_path):
    rec = start(tmp_path, secrets=[SECRET_PASS])
    assert rec.redact(f"Error: typed {SECRET_PASS}") == "Error: typed [REDACTED]"


def test_first_check_outcome_wins_and_untested_are_filled(tmp_path):
    rec = start(tmp_path)
    assert rec.record_check("price_in_text", False, "no price") is True
    assert rec.record_check("price_in_text", True, "later pass") is False
    rec.mark_untested({"payment": "payment skipped"})
    results = rec.results()
    assert set(results) == set(CHECKS)
    assert results["price_in_text"] == "fail"
    assert results["capture_completed"] == "not_tested"
    rec.save_score(compute_score(results))
    run = load_run(tmp_path / "t.db", rec.run_id)
    assert run["score"]["total"] == 0
    assert run["flaws_snapshot"] == {"price_as_image": True}
    reasons = {c["check_key"]: c["reason"] for c in run["checks"]}
    assert reasons["capture_completed"] == "payment skipped"


def test_failure_code_decides_the_cause_and_environment_failures_are_excluded(tmp_path):
    rec = start(tmp_path)
    rec.record_check("price_in_text", False, "image only", code="price_image_only")
    rec.record_check("capture_completed", False, "declined", code="capture_declined")
    rec.record_check("popup_opened", False, "no code given")  # unknown/missing code -> store's fault
    rec.mark_untested({}, blocked_by_environment=True)
    rows = {r["check_key"]: r for r in rec.rows()}
    assert (rows["price_in_text"]["cause"], rows["capture_completed"]["cause"]) == ("store", "environment")
    assert rows["popup_opened"]["cause"] == "store"
    r = rec.results()
    assert (r["price_in_text"], r["capture_completed"], r["popup_opened"]) == ("fail", "excluded", "fail")
    assert r["payment_verified"] == "excluded"  # never ran because of the declined capture
    assert rec.has_environment_failure()


def test_scorecard_explains_a_declined_capture(tmp_path):
    rec = start(tmp_path)
    for key in CHECKS:
        if key not in ("capture_completed", "payment_verified", "task_completed"):
            rec.record_check(key, True, "ok")
    rec.record_check("capture_completed", False, "The buyer's funding source declined the payment (INSTRUMENT_DECLINED).",
                     code="capture_declined")
    rec.record_check("task_completed", None, "The payment did not complete for a reason outside the store.",
                     code="blocked_by_environment")
    rec.mark_untested({}, blocked_by_environment=True)
    rec.save_score(compute_score(rec.results()))
    card = load_run(tmp_path / "t.db", rec.run_id)["scorecard"]
    assert card["total"] == 100 and card["possible"] == 85
    assert sum(card["stage_possible"].values()) == 85 and card["stages"] == card["stage_possible"]
    assert {n["check"] for n in card["not_store_fault"]} == {"capture_completed", "payment_verified", "task_completed"}
    assert card["fixes"] == []
    text = " ".join(card["summary"])
    assert "judged on 85 of 100 points" in text
    assert "INSTRUMENT_DECLINED" in text and "No store change needed" in text
    assert "payment_verified" in text


def test_failures_view_lists_failed_and_untested(tmp_path):
    rec = start(tmp_path)
    rec.record_check("product_found", True, "ok")
    rec.record_check("price_in_text", False, "no price")
    with db.connect(tmp_path / "t.db") as conn:
        keys = {r["check_key"] for r in conn.execute("SELECT check_key FROM failures WHERE run_id = ?", (rec.run_id,))}
    assert keys == {"price_in_text"}


def test_day1_orders_table_gets_run_id_column(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE orders (order_id TEXT PRIMARY KEY, sku TEXT, quantity INTEGER, currency TEXT,"
                 " amount TEXT, status TEXT, created_at TEXT)")
    conn.close()
    db.init_db(path)
    with db.connect(path) as c:
        assert "run_id" in {r["name"] for r in c.execute("PRAGMA table_info(orders)")}


ASSISTANT = {
    "role": "assistant",
    "content": "Looking around",
    "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "read_text", "arguments": "{}"}}],
}
TOOLS = [{"type": "function", "function": {"name": "read_text", "parameters": {"type": "object", "properties": {}}}}]


@pytest.mark.anyio
async def test_replay_llm_plays_in_order_then_fails_loudly(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"responses": [ASSISTANT]}))
    llm = ReplayLLM(path)
    reply = await llm.complete([], TOOLS)
    assert reply.tool_calls[0].name == "read_text"
    with pytest.raises(CassetteExhausted):
        await llm.complete([], TOOLS)


@pytest.mark.anyio
async def test_replay_llm_rejects_tools_not_offered(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"responses": [ASSISTANT]}))
    with pytest.raises(CassetteExhausted, match="not offered"):
        await ReplayLLM(path).complete([], [])


@pytest.mark.anyio
async def test_groq_llm_parses_tool_calls_and_retries_429():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "0"})
        msg = {**ASSISTANT, "tool_calls": [{**ASSISTANT["tool_calls"][0],
                                            "function": {"name": "click", "arguments": '{"element_id": "e3"}'}}]}
        return httpx.Response(200, json={"choices": [{"message": msg}]})

    http = httpx.AsyncClient(base_url="https://groq.test", transport=httpx.MockTransport(handler))
    reply = await GroqLLM("key", "some-model", http=http).complete([{"role": "user", "content": "hi"}], TOOLS)
    assert len(calls) == 2
    assert calls[1]["model"] == "some-model" and calls[1]["tools"] == TOOLS
    assert reply.tool_calls[0].arguments == {"element_id": "e3"}


def test_make_llm_requires_explicit_config(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    with pytest.raises(LLMConfigError, match="GROQ_API_KEY"):
        make_llm("groq")
    with pytest.raises(LLMConfigError, match="cassette"):
        make_llm("mock")
    with pytest.raises(LLMConfigError, match="Invalid cassette"):
        make_llm("mock", "../etc")
