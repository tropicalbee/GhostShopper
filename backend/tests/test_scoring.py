import pytest

from backend.app.scoring import CHECKS, EXCLUDED, FAIL, NOT_TESTED, PASS, STAGES, compute_score


def pts(key: str) -> int:
    return CHECKS[key].points


def all_results(value) -> dict:
    return {key: value for key in CHECKS}


def test_every_check_passing_scores_100_with_no_fixes():
    score = compute_score(all_results(True))
    assert score.total == 100
    assert score.possible == 100
    assert score.fixes == [] and score.excluded == []


def test_weights_sum_to_100_and_every_stage_is_known():
    assert sum(c.points for c in CHECKS.values()) == 100
    assert {c.stage for c in CHECKS.values()} <= set(STAGES)


def test_failed_check_loses_its_points_and_becomes_a_fix():
    score = compute_score(all_results(True) | {"price_in_text": False})
    assert score.total == 100 - pts("price_in_text")
    assert [(f.key, f.points, f.status) for f in score.fixes] == [("price_in_text", pts("price_in_text"), "failed")]


def test_bool_and_status_inputs_are_equivalent():
    assert compute_score({"price_in_text": False}) == compute_score({"price_in_text": FAIL})
    assert compute_score({"price_in_text": True}) == compute_score({"price_in_text": PASS})
    assert compute_score({"price_in_text": None}) == compute_score({"price_in_text": NOT_TESTED})


def test_untested_checks_earn_nothing_and_rank_after_failures():
    results = all_results(None) | {"price_in_text": True, "no_extra_steps": False}
    score = compute_score(results)
    assert score.total == pts("price_in_text")
    assert score.fixes[0].key == "no_extra_steps" and score.fixes[0].status == "failed"
    assert all(f.status == "not_tested" for f in score.fixes[1:])


def test_not_the_stores_fault_is_excluded_and_the_score_renormalized():
    # Payment declined by the buyer's bank: the store did everything right.
    results = all_results(True) | {"capture_completed": EXCLUDED}
    score = compute_score(results)
    assert score.total == 100
    assert score.possible == 100 - pts("capture_completed")
    assert [e.key for e in score.excluded] == ["capture_completed"]
    assert score.fixes == []


def test_store_failure_still_counts_alongside_an_exclusion():
    results = all_results(True) | {"price_in_text": False, "capture_completed": EXCLUDED}
    possible = 100 - pts("capture_completed")
    earned = possible - pts("price_in_text")
    score = compute_score(results)
    assert score.possible == possible
    assert score.total == (200 * earned + possible) // (2 * possible)  # round half up
    assert [f.key for f in score.fixes] == ["price_in_text"]


def test_worked_example_rounding():
    # 90 of 95 possible points -> 94.7 -> 95 (independent arithmetic, not the implementation).
    results = {k: True for k in CHECKS}
    excluded_key = next(k for k, c in CHECKS.items() if c.points == 5)
    failed_key = next(k for k, c in CHECKS.items() if c.points == 5 and k != excluded_key)
    results[excluded_key] = EXCLUDED
    results[failed_key] = False
    score = compute_score(results)
    assert (score.possible, score.total) == (95, 95)


def test_everything_excluded_means_no_score():
    score = compute_score(all_results(EXCLUDED))
    assert (score.total, score.possible) == (0, 0)
    assert score.fixes == []
    assert len(score.excluded) == len(CHECKS)


def test_stage_subscores_exclude_points_that_are_not_the_stores_fault():
    results = all_results(True) | {"capture_completed": EXCLUDED, "price_in_text": False}
    stages = compute_score(results).stages
    pay_possible = sum(c.points for c in CHECKS.values() if c.stage == "payment") - pts("capture_completed")
    assert stages["payment"] == (pay_possible, pay_possible)
    det_possible = sum(c.points for c in CHECKS.values() if c.stage == "details")
    assert stages["details"] == (det_possible - pts("price_in_text"), det_possible)


def test_nothing_tested_scores_zero():
    score = compute_score({})
    assert score.total == 0 and score.possible == 100
    assert len(score.fixes) == len(CHECKS)


def test_unknown_check_key_and_status_are_rejected():
    with pytest.raises(ValueError, match="price_as_text"):
        compute_score({"price_as_text": True})
    with pytest.raises(ValueError, match="maybe"):
        compute_score({"price_in_text": "maybe"})


def test_outcome_summary_check_is_listed_after_the_failures_that_caused_it():
    score = compute_score(all_results(True) | {"paypal_button_found": False, "task_completed": False})
    assert [f.key for f in score.fixes] == ["paypal_button_found", "task_completed"]


def test_fixes_ordered_by_points_then_severity():
    keys = sorted(CHECKS, key=lambda k: (-CHECKS[k].points, k))[:3]
    score = compute_score(all_results(True) | {k: False for k in keys})
    got = [f.key for f in score.fixes]
    sev = {"critical": 0, "major": 1, "minor": 2}
    assert got == sorted(keys, key=lambda k: (-CHECKS[k].points, sev[CHECKS[k].severity], list(CHECKS).index(k)))
