import json

import pytest

from backend.app.agent.explain import explain_run, parse_rephrasings
from backend.app.agent.llm import ReplayLLM, resolve_cassette
from backend.app.agent.recorder import load_run
from backend.app.failures import FAILURE_TYPES

from .test_compare import CLASSIC_FAILS, make_run

pytestmark = pytest.mark.anyio


def text_llm(tmp_path, content):
    path = tmp_path / "t.json"
    path.write_text(json.dumps({"responses": [{"role": "assistant", "content": content}]}))
    return ReplayLLM(path)


def test_every_failure_type_has_a_concrete_fix_and_a_known_cause():
    from backend.app.scoring import CHECKS

    for code, ft in FAILURE_TYPES.items():
        assert ft.cause in ("store", "environment"), code
        assert ft.check in CHECKS, code
        assert len(ft.fix) > 20, code


async def test_llm_rephrases_but_never_changes_the_fix_or_score(tmp_path):
    db = tmp_path / "e.db"
    run_id = make_run(db, CLASSIC_FAILS, {})
    before = load_run(db, run_id)
    out = await explain_run(db, run_id, ReplayLLM(resolve_cassette("fixes_rephrase_classic")))
    assert {o["code"] for o in out} == set(CLASSIC_FAILS.values())
    assert all(o["source"].startswith("llm:") for o in out)
    after = load_run(db, run_id)
    assert after["score"] == before["score"]  # rephrasing never touches the score
    price = next(f for f in after["scorecard"]["fixes"] if f["check"] == "price_in_text")
    assert price["fix"] == FAILURE_TYPES["price_image_only"].fix  # deterministic fix unchanged
    assert "picture" in price["fix_explained"]


async def test_bad_llm_output_falls_back_to_the_deterministic_fix(tmp_path):
    db = tmp_path / "e.db"
    run_id = make_run(db, CLASSIC_FAILS, {})
    out = await explain_run(db, run_id, text_llm(tmp_path, "Sorry, I can't help with that."))
    assert all(o["source"] == "deterministic" and o["explained"] == o["fix"] for o in out)
    assert all(f["fix_explained"] is None for f in load_run(db, run_id)["scorecard"]["fixes"])


def test_parser_keeps_only_asked_codes_with_sane_text():
    content = "```json\n" + json.dumps({"price_image_only": "Type the price.", "made_up_code": "x",
                                        "stock_missing": "", "jsonld_missing": "y" * 600}) + "\n```"
    assert parse_rephrasings(content, {"price_image_only", "stock_missing", "jsonld_missing"}) == {
        "price_image_only": "Type the price."}
    assert parse_rephrasings("[1, 2]", {"a"}) == {}


async def test_run_without_store_failures_has_nothing_to_explain(tmp_path):
    db = tmp_path / "e.db"
    run_id = make_run(db, {"capture_completed": "capture_declined"}, {})
    assert await explain_run(db, run_id, text_llm(tmp_path, "{}")) == []
