from backend.app.scoring import CHECKS, compute_score


def all_results(passed: bool) -> dict:
    return {key: passed for key in CHECKS}


def test_every_check_passing_scores_100_with_no_fixes():
    score = compute_score(all_results(True))
    assert score.total == 100
    assert score.fixes == []


def test_failed_check_loses_its_points_and_becomes_a_fix():
    results = all_results(True) | {"price_in_text": False}
    score = compute_score(results)
    assert score.total == 85
    assert [(f.key, f.points, f.status) for f in score.fixes] == [("price_in_text", 15, "failed")]


def test_untested_checks_earn_nothing_and_rank_after_failures():
    # Reached checkout through an extra step; payment never tested.
    results = {
        "product_found": True,
        "price_in_text": True,
        "structured_data": True,
        "stock_readable": True,
        "clear_buy_button": True,
        "no_extra_steps": False,
        "checkout_reached": True,
    }
    score = compute_score(results)
    assert score.total == 70
    assert [(f.key, f.status) for f in score.fixes] == [
        ("no_extra_steps", "failed"),
        ("paypal_button_found", "not_tested"),
        ("capture_completed", "not_tested"),
        ("popup_opened", "not_tested"),
        ("payment_approved", "not_tested"),
    ]


def test_stage_subscores():
    results = {
        "product_found": True,
        "price_in_text": True,
        "structured_data": True,
        "stock_readable": True,
        "clear_buy_button": True,
        "no_extra_steps": False,
        "checkout_reached": True,
    }
    assert compute_score(results).stages == {
        "discover": (10, 10),
        "details": (50, 50),
        "checkout": (10, 20),
        "payment": (0, 20),
    }


def test_nothing_tested_scores_zero():
    score = compute_score({})
    assert score.total == 0
    assert len(score.fixes) == len(CHECKS)
    assert all(f.status == "not_tested" for f in score.fixes)


def test_weights_sum_to_100():
    assert compute_score(all_results(True)).total == 100
    assert compute_score(all_results(False)).total == 0


def test_unknown_check_key_is_rejected():
    import pytest

    with pytest.raises(ValueError, match="price_as_text"):
        compute_score({"price_as_text": True})


def test_fixes_ordered_by_points_then_severity():
    results = all_results(True) | {"stock_readable": False, "structured_data": False, "clear_buy_button": False}
    score = compute_score(results)
    assert score.total == 65
    # clear_buy_button (15, critical) before structured_data (15, major) before stock_readable (5, minor)
    assert [f.key for f in score.fixes] == ["clear_buy_button", "structured_data", "stock_readable"]
