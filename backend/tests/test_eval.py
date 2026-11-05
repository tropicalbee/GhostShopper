import json

import pytest

from backend.app import db
from backend.app.agent.explain import explain_run
from backend.app.agent.llm import ReplayLLM, resolve_cassette
from backend.app.agent.recorder import load_run
from backend.app.eval.benchmark import RunResult, summarize
from backend.app.eval.ground_truth import LABELS
from backend.app.eval.judge import invented_numbers, judge_run, parse_ratings
from backend.app.eval.saboteur import classic_matrix, implemented_flaws, propose_flaws, random_combos
from store.flaws import CLASSIC_FLAWS

from .test_compare import CLASSIC_FAILS, make_run

pytestmark = pytest.mark.anyio


# --- LLM-as-judge: secondary metric, never the score ---

async def test_judge_rates_explanations_without_touching_the_score(tmp_path):
    path = tmp_path / "j.db"
    run_id = make_run(path, CLASSIC_FAILS, {})
    await explain_run(path, run_id, ReplayLLM(resolve_cassette("fixes_rephrase_classic")))
    before = load_run(path, run_id)["score"]
    result = await judge_run(path, run_id, ReplayLLM(resolve_cassette("judge_classic")))
    assert load_run(path, run_id)["score"] == before  # the judge never affects the readiness score
    assert result["valid"] is False and "Not valid until run live" in result["note"]
    assert result["summary"]["rated"] == 5
    assert result["summary"]["mean_actionable"] == 4.4  # (5 + 3 + 5 + 5 + 4) / 5
    assert result["summary"]["invented_rate"] == 0.0
    with db.connect(path) as conn:
        rows = conn.execute("SELECT valid, judge_model FROM judge_ratings WHERE run_id = ?", (run_id,)).fetchall()
    assert len(rows) == 5 and all(r["valid"] == 0 for r in rows)


async def test_judge_needs_explanations_first(tmp_path):
    path = tmp_path / "j.db"
    run_id = make_run(path, CLASSIC_FAILS, {})
    result = await judge_run(path, run_id, ReplayLLM(resolve_cassette("judge_classic")))
    assert result["items"] == [] and "run explain first" in result["note"]


def test_numbers_not_in_the_evidence_are_flagged():
    assert invented_numbers("Fix it in 5 minutes; it costs $9.99.", ["price 24.00", "fix the button"]) == ["5", "9.99"]
    assert invented_numbers("Show $24.00 as text.", ["Price text found: $24.00"]) == []


def test_judge_output_is_validated():
    assert parse_ratings("not json", {"a"}) == {}
    r = parse_ratings(json.dumps({"a": {"matches_evidence": 9, "actionable": 4, "invented": "yes"}, "b": {}}), {"a"})
    assert r == {"a": {"matches_evidence": None, "actionable": 4, "invented": None, "notes": ""}}


# --- Saboteur ---

def test_classic_matrix_is_all_16_combinations():
    m = classic_matrix()
    assert len(m) == len(set(m)) == 16 and () in m and tuple(CLASSIC_FLAWS) in m


def test_random_combos_are_seeded_distinct_and_implemented_only():
    a, b = random_combos(20, seed=3), random_combos(20, seed=3)
    assert a == b and len(set(a)) == 20
    assert all(set(c) <= set(implemented_flaws()) and 1 <= len(c) <= 4 for c in a)


async def test_llm_flaw_ideas_are_stored_but_never_counted_until_implemented(tmp_path):
    path = tmp_path / "p.db"
    props = await propose_flaws(ReplayLLM(resolve_cassette("flaw_ideas")), path)
    status = {p.key: p.status for p in props}
    assert status["cookie_banner"] == "implemented"
    assert status["infinite_scroll_product"] == "proposed"
    assert "infinite_scroll_product" not in implemented_flaws()
    with db.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM flaw_proposals WHERE status = 'proposed'").fetchone()[0] == 3
    with pytest.raises(ValueError):
        from backend.app.eval.ground_truth import expected

        expected({"infinite_scroll_product"}, checkout=True)  # no ground truth: cannot be evaluated


# --- Benchmark arithmetic ---

def result(combo, tp=(), fp=(), fn=(), per_flaw=None):
    return RunResult(list(combo), 1, 0, "purchased", 90, 1.0, sorted(set(tp) | set(fn)), [], sorted(set(tp) | set(fp)),
                     list(tp), list(fp), list(fn), [], per_flaw or {})


def test_precision_recall_and_missed_flaws():
    runs = [
        result(["price_as_image"], tp=["price_in_text"],
               per_flaw={"price_as_image": {"expected": ["price_in_text"], "missed": [], "masked": []}}),
        result(["cookie_banner"], fn=["buy_button_unobstructed"],
               per_flaw={"cookie_banner": {"expected": ["buy_button_unobstructed"],
                                           "missed": ["buy_button_unobstructed"], "masked": []}}),
        result([], fp=["image_alt_text"]),
    ]
    s = summarize(runs, [], checkout=True, label="t", seconds=1)
    assert s["micro"] == {"tp": 1, "fp": 1, "fn": 1, "precision": 0.5, "recall": 0.5}
    assert s["per_flaw"]["cookie_banner"]["missed"] == 1
    assert s["per_flaw"]["cookie_banner"]["missed_checks"] == {"buy_button_unobstructed": 1}
    assert s["per_check"]["image_alt_text"]["fp"] == 1
    assert set(LABELS) >= {"price_as_image", "cookie_banner"}
