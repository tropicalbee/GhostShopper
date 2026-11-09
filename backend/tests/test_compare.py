import pytest

from backend.app.agent.compare import CompareError, compare_runs, last_two_finished, main
from backend.app.agent.recorder import RunRecorder
from backend.app.scoring import CHECKS, compute_score

CLASSIC_FAILS = {"price_in_text": "price_image_only", "structured_data": "jsonld_missing",
                 "stock_readable": "stock_missing", "clear_buy_button": "buy_button_nonsemantic",
                 "no_extra_steps": "extra_form_step"}


def make_run(db, failing: dict[str, str], flaws: dict[str, bool], checkout=True) -> int:
    rec = RunRecorder.start(db, store_url="http://s/", goal="g", target_product="Mug", checkout=checkout,
                            paypal_mode="mock", flaws=flaws, llm="mock", model="m")
    for key in CHECKS:
        if key in failing:
            rec.record_check(key, False, f"{key} failed", code=failing[key])
        else:
            rec.record_check(key, True, "ok")
    rec.save_score(compute_score(rec.results()))
    rec.finish(status="completed", outcome="purchased", step_count=3)
    return rec.run_id


@pytest.fixture
def db(tmp_path):
    return tmp_path / "c.db"


def test_bad_to_fixed_store(db):
    bad = make_run(db, CLASSIC_FAILS, {"price_as_image": True, "ambiguous_buttons": True})
    good = make_run(db, {}, {"price_as_image": False, "ambiguous_buttons": False})
    c = compare_runs(db, bad, good)
    expected_before = 100 - sum(CHECKS[k].points for k in CLASSIC_FAILS)
    assert (c["before"]["score"], c["after"]["score"], c["score_change"]) == (expected_before, 100, 100 - expected_before)
    assert {i["check"] for i in c["fixed"]} == set(CLASSIC_FAILS)
    assert c["remaining"] == [] and c["new_failures"] == []
    assert c["flaws_turned_off"] == ["ambiguous_buttons", "price_as_image"]
    assert c["headline"].startswith(f"Score {expected_before} -> 100 (+{100 - expected_before}). 5 failure(s) fixed, 0 remaining, 0 new.")
    assert c["warnings"] == []


def test_partial_fix_lists_what_still_fails_with_its_fix(db):
    bad = make_run(db, CLASSIC_FAILS, {})
    half = make_run(db, {"price_in_text": "price_image_only", "stock_readable": "stock_missing",
                         "paypal_button_found": "paypal_button_missing"}, {})
    c = compare_runs(db, bad, half)
    assert {i["check"] for i in c["remaining"]} == {"price_in_text", "stock_readable"}
    assert [i["check"] for i in c["new_failures"]] == ["paypal_button_found"]
    price = next(i for i in c["remaining"] if i["check"] == "price_in_text")
    assert "as text" in price["fix"]


def test_comparing_browse_with_checkout_runs_warns(db):
    a = make_run(db, {}, {}, checkout=False)
    b = make_run(db, {}, {}, checkout=True)
    assert any("payment" in w for w in compare_runs(db, a, b)["warnings"])


def test_unknown_or_unscored_runs_are_errors(db):
    a = make_run(db, {}, {})
    with pytest.raises(CompareError, match="No run 99"):
        compare_runs(db, a, 99)
    unscored = RunRecorder.start(db, store_url="s", goal="g", target_product="M", checkout=False,
                                 paypal_mode="off", flaws={}, llm="mock", model="m").run_id
    with pytest.raises(CompareError, match="finished"):
        compare_runs(db, a, unscored)


def test_last_two_finished_and_cli(db, monkeypatch, capsys):
    a = make_run(db, CLASSIC_FAILS, {})
    b = make_run(db, {}, {})
    assert last_two_finished(db) == (a, b)
    monkeypatch.setenv("DATABASE_PATH", str(db))
    assert main(["--last"]) == 0
    out = capsys.readouterr().out
    assert f"Run {a} -> run {b}" in out and "Fixed:" in out


def test_compare_endpoint(db):
    from fastapi.testclient import TestClient

    from backend.app.config import Settings
    from backend.app.main import create_app

    a = make_run(db, CLASSIC_FAILS, {})
    b = make_run(db, {}, {})
    with TestClient(create_app(Settings("", "", db, "http://x"))) as client:
        r = client.get(f"/api/runs/compare?before={a}&after={b}")
        assert r.status_code == 200 and len(r.json()["fixed"]) == 5
        assert client.get(f"/api/runs/{b}/compare").json()["before"]["run_id"] == a  # previous check, same store
        assert client.get("/api/runs/compare").status_code == 422  # no global "last two runs"
        assert client.get(f"/api/runs/compare?before={a}&after=999").status_code == 404


def _client(db):
    from fastapi.testclient import TestClient

    from backend.app.config import Settings
    from backend.app.main import create_app

    return TestClient(create_app(Settings("", "", db, "http://x")))


def test_compare_rows_points_and_fix_text(db):
    bad = make_run(db, CLASSIC_FAILS, {"price_as_image": True})
    good = make_run(db, {}, {"price_as_image": False})
    with _client(db) as client:
        body = client.get(f"/api/runs/{good}/compare?before={bad}").json()
    rows = {i["check"]: i for i in body["checks"]}
    assert len(rows) == len(CHECKS)
    price = rows["price_in_text"]
    assert (price["before"], price["after"], price["stage"], price["points"]) == ("fail", "pass", "details", CHECKS["price_in_text"].points)
    assert price["fix_applied"]
    assert rows["product_found"]["before"] == rows["product_found"]["after"] == "pass"
    assert rows["product_found"]["fix_applied"] is None
    gained = sum(i["points"] for i in body["checks"] if i["before"] == "fail" and i["after"] == "pass")
    assert gained == body["score_change"]
    assert body["before"]["catalog_price"] == body["after"]["catalog_price"] or body["before"]["catalog_price"] is None


def test_compare_default_prefers_different_flaws(db):
    old_bad = make_run(db, CLASSIC_FAILS, {"price_as_image": True})
    same = make_run(db, {}, {"price_as_image": False})
    after = make_run(db, {}, {"price_as_image": False})
    with _client(db) as client:
        assert client.get(f"/api/runs/{after}/compare").json()["before"]["run_id"] == old_bad
        assert client.get(f"/api/runs/{after}/compare?before={same}").json()["before"]["run_id"] == same
        assert client.get(f"/api/runs/{same}/compare?before={after}").status_code == 400


def test_compare_with_no_earlier_run_says_so(db):
    only = make_run(db, {}, {})
    with _client(db) as client:
        r = client.get(f"/api/runs/{only}/compare")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "NO_EARLIER_CHECK"
    assert "check again" in r.json()["detail"]["message"]
