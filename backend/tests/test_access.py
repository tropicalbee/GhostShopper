"""Who can see and change what: each browser only reaches its own checks, plus the shared examples.

Abuse cases first: another browser guessing run ids, a public caller setting developer options,
anyone flipping the shared demo store, request floods, and server-side fetches aimed inward.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import db as dbm
from backend.app.agent.recorder import RunRecorder
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.owner import COOKIE, hash_token, new_token
from backend.app.scoring import CHECKS, compute_score

ALICE, BOB = new_token(), new_token()


def make_run(db: Path, owner: str | None, store: str = "https://shop-a.example/", failing: tuple[str, ...] = (),
             runs_dir: Path | None = None) -> int:
    rec = RunRecorder.start(db, store_url=store, goal="g", target_product=None, checkout=False, paypal_mode="off",
                            flaws=None, llm="scripted", model="m", live=True,
                            owner_hash=hash_token(owner) if owner else None)
    for key in CHECKS:
        rec.record_check(key, key not in failing, "seen", code="price_image_only" if key in failing else None)
    rec.save_score(compute_score(rec.results()))
    if runs_dir is not None:
        folder = runs_dir / f"run-{rec.run_id}"
        folder.mkdir(parents=True)
        (folder / "step-0.png").write_bytes(b"\x89PNG")
        rec.add_step(idx=0, tool="open_page", args={}, thought=None, observation="o", ok=True, url=store,
                     screenshot_path=str(folder / "step-0.png"), duration_ms=1)
    rec.finish(status="completed", outcome="reached_checkout", step_count=1)
    return rec.run_id


def settings(tmp_path: Path, **kw) -> Settings:
    return Settings("", "", tmp_path / "a.db", "https://ghostshopper.example", runs_dir=tmp_path / "runs",
                    frontend_dist=tmp_path / "dist", **kw)


def client_for(app, token: str | None) -> TestClient:
    c = TestClient(app, base_url="https://testserver")
    if token:
        c.cookies.set(COOKIE, token)
    return c


@pytest.fixture
def app(tmp_path):
    return create_app(settings(tmp_path))


def test_a_first_visit_gets_a_private_owner_cookie(app):
    with client_for(app, None) as c:
        r = c.get("/api/health")
    cookie = r.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE}=") and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert "Secure" in cookie and "Max-Age=" in cookie


def test_a_valid_cookie_is_kept_not_replaced(app):
    with client_for(app, ALICE) as c:
        assert "set-cookie" not in c.get("/api/health").headers


def test_another_browser_cannot_reach_my_run(app, tmp_path):
    run = make_run(tmp_path / "a.db", ALICE, runs_dir=tmp_path / "runs")
    with client_for(app, BOB) as bob:
        for path in (f"/api/runs/{run}", f"/api/runs/{run}/developer-summary", f"/api/runs/{run}/files/step-0.png",
                     f"/api/runs/{run}/compare"):
            assert bob.get(path).status_code == 404, path
        assert bob.post(f"/api/runs/{run}/explain", json={}).status_code == 404
        assert bob.delete(f"/api/runs/{run}").status_code == 404
        assert all(r["id"] != run for r in bob.get("/api/runs").json())


def test_a_browser_without_a_cookie_cannot_reach_my_run(app, tmp_path):
    run = make_run(tmp_path / "a.db", ALICE)
    with client_for(app, None) as anon:
        assert anon.get(f"/api/runs/{run}").status_code == 404


def test_i_can_reach_my_run_and_the_owner_hash_never_leaves_the_server(app, tmp_path):
    run = make_run(tmp_path / "a.db", ALICE)
    with client_for(app, ALICE) as alice:
        body = alice.get(f"/api/runs/{run}").json()
        listed = alice.get("/api/runs").json()
    assert body["mine"] is True and body["example"] is False
    assert "owner_hash" not in body and all("owner_hash" not in r for r in listed)
    assert [r["id"] for r in listed if r["mine"]] == [run]


def test_example_runs_are_readable_by_everyone_but_not_deletable(app, tmp_path):
    example = make_run(tmp_path / "a.db", None)
    with client_for(app, BOB) as bob:
        body = bob.get(f"/api/runs/{example}").json()
        assert body["example"] is True and body["mine"] is False
        assert bob.delete(f"/api/runs/{example}").status_code == 403


def test_before_and_after_compares_my_previous_check_of_the_same_store(app, tmp_path):
    db = tmp_path / "a.db"
    mine_before = make_run(db, ALICE, failing=("price_in_text",))
    make_run(db, ALICE, store="https://other-shop.example/")  # a different store of mine
    make_run(db, BOB)  # someone else's check of the same store
    mine_after = make_run(db, ALICE)
    with client_for(app, ALICE) as alice:
        c = alice.get(f"/api/runs/{mine_after}/compare").json()
    assert (c["before"]["run_id"], c["after"]["run_id"]) == (mine_before, mine_after)
    assert c["score_change"] == CHECKS["price_in_text"].points


def test_before_and_after_needs_an_earlier_check(app, tmp_path):
    run = make_run(tmp_path / "a.db", ALICE)
    with client_for(app, ALICE) as alice:
        r = alice.get(f"/api/runs/{run}/compare")
    assert r.status_code == 404 and "check again" in r.json()["detail"]["message"].lower()


def test_compare_by_ids_refuses_other_peoples_runs_and_mixed_stores(app, tmp_path):
    db = tmp_path / "a.db"
    a1, a2 = make_run(db, ALICE), make_run(db, ALICE, store="https://other-shop.example/")
    b1 = make_run(db, BOB)
    with client_for(app, ALICE) as alice:
        assert alice.get(f"/api/runs/compare?before={b1}&after={a1}").status_code == 404
        assert alice.get(f"/api/runs/compare?before={a1}&after={a2}").status_code == 400
        assert alice.get("/api/runs/compare").status_code == 422


def test_public_callers_cannot_set_developer_options(tmp_path):
    app = create_app(settings(tmp_path, run_rate_limit=(50, 600)))
    with client_for(app, ALICE) as c:
        for body in ({"llm": "mock"}, {"cassette": "day3_checkout_flaws_on"}, {"record": "x"},
                     {"flaws": "off"}, {"checkout": True}, {"browser": "kernel"}, {"max_steps": 60}):
            r = c.post("/api/runs", json={"store_url": "https://shop-a.example/", **body})
            assert r.status_code == 400 and "only" in r.json()["detail"]["message"].lower(), body


def test_starting_checks_is_rate_limited(tmp_path):
    app = create_app(settings(tmp_path, run_rate_limit=(3, 600)))
    with client_for(app, ALICE) as c:
        codes = [c.post("/api/runs", json={"store_url": "not a url"}).status_code for _ in range(4)]
    assert codes[:3] == [400, 400, 400] and codes[3] == 429


def test_the_demo_store_settings_are_locked_when_deployed(app):
    with client_for(app, None) as c:
        assert c.get("/store/admin").status_code == 403
        assert c.post("/store/admin", data={}).status_code == 403
        assert c.put("/store/admin/flaws.json", json={"flaws": {}}).status_code == 403
        assert c.get("/store/admin/flaws.json").status_code == 200
        assert c.get("/api/health").json()["demo_admin_open"] is False


def test_the_demo_admin_token_unlocks_the_settings(tmp_path):
    app = create_app(settings(tmp_path, demo_admin_token="t0ken-for-the-presenter"))
    with client_for(app, None) as c:
        assert c.get("/store/admin?token=wrong").status_code == 403
        r = c.get("/store/admin?token=t0ken-for-the-presenter")
        assert r.status_code == 200 and "HttpOnly" in r.headers["set-cookie"]
        assert c.put("/store/admin/flaws.json", json={"flaws": {}}).status_code == 200  # the cookie now carries it


def test_security_headers_on_every_response(app):
    with client_for(app, None) as c:
        h = c.get("/api/health").headers
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
    assert h["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "max-age=" in h["strict-transport-security"]


def test_the_dashboard_is_served_with_a_strict_csp(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>GhostShopper</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("export {}", encoding="utf-8")
    with client_for(create_app(settings(tmp_path)), None) as c:
        r = c.get("/")
        assert r.status_code == 200 and "GhostShopper" in r.text
        csp = r.headers["content-security-policy"]
        assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp and "script-src 'self'" in csp
        assert c.get("/assets/app.js").status_code == 200


def test_a_missing_dashboard_build_is_an_explicit_error(app):
    with client_for(app, None) as c:
        r = c.get("/")
    assert r.status_code == 503 and r.json()["error"] == "FRONTEND_NOT_BUILT"


def test_deleting_my_check_removes_its_rows_and_screenshots(app, tmp_path):
    db, runs = tmp_path / "a.db", tmp_path / "runs"
    run = make_run(db, ALICE, runs_dir=runs)
    with client_for(app, ALICE) as alice:
        assert alice.delete(f"/api/runs/{run}").status_code == 204
        assert alice.get(f"/api/runs/{run}").status_code == 404
    assert not (runs / f"run-{run}").exists()
    with dbm.connect(db) as conn:
        for table in ("steps", "checks", "scores"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE run_id = ?", (run,)).fetchone()[0] == 0


def test_old_checks_are_purged_but_examples_stay(tmp_path):
    db, runs = tmp_path / "a.db", tmp_path / "runs"
    old, fresh, example = make_run(db, ALICE, runs_dir=runs), make_run(db, ALICE), make_run(db, None)
    long_ago = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat(timespec="seconds")
    with dbm.connect(db) as conn:
        conn.execute("UPDATE runs SET started_at = ? WHERE id IN (?, ?)", (long_ago, old, example))
    assert dbm.purge_old_runs(db, runs, days=30) == [old]
    with dbm.connect(db) as conn:
        left = {r[0] for r in conn.execute("SELECT id FROM runs")}
    assert left == {fresh, example} and not (runs / f"run-{old}").exists()


# --- Server-side fetches can't be aimed inward (SSRF) ---

@pytest.mark.anyio
async def test_robots_and_preflight_redirects_to_private_hosts_are_refused():
    from backend.app.agent.site import Politeness

    hops = []

    def handler(request: httpx.Request) -> httpx.Response:
        hops.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})

    polite = Politeness(allow_private=False, transport=httpx.MockTransport(handler))
    try:
        assert await polite.allowed("http://93.184.216.34/") is False  # robots.txt redirected inward: disallowed
    finally:
        await polite.aclose()
    assert hops == ["http://93.184.216.34/robots.txt"]  # the inward hop was never requested


@pytest.mark.anyio
async def test_the_browser_blocks_frames_and_images_that_point_inward():
    from backend.app.agent.browser import BrowserSession

    session = BrowserSession.__new__(BrowserSession)
    session.allow_private, session.refused, session.politeness, session._host_ok = False, {}, None, {}
    outcomes = []
    route = SimpleNamespace(abort=lambda reason: _record(outcomes, "abort"), continue_=lambda: _record(outcomes, "go"))
    for kind, url in (("image", "http://169.254.169.254/latest/meta-data"), ("document", "http://10.0.0.5/")):
        frame = SimpleNamespace(parent_frame=object())  # an iframe, not the main page
        request = SimpleNamespace(resource_type=kind, url=url, frame=frame, is_navigation_request=lambda: kind == "document")
        await session._guard(route, request)
    assert outcomes == ["abort", "abort"]


async def _record(outcomes: list, what: str) -> None:
    outcomes.append(what)


def test_runs_from_before_ownership_are_hidden_not_made_public(tmp_path):
    import sqlite3

    db = tmp_path / "old.db"
    run = make_run(db, None)
    conn = sqlite3.connect(db)  # turn it back into a database from before the owner column existed
    conn.execute("ALTER TABLE runs DROP COLUMN owner_hash")
    conn.commit()
    conn.close()
    app = create_app(Settings("", "", db, "https://ghostshopper.example", runs_dir=tmp_path / "runs",
                              frontend_dist=tmp_path / "dist"))
    with client_for(app, ALICE) as c:
        assert c.get(f"/api/runs/{run}").status_code == 404
        assert c.get("/api/runs").json() == []
    long_ago = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat(timespec="seconds")
    with dbm.connect(db) as conn:
        conn.execute("UPDATE runs SET started_at = ?", (long_ago,))
    assert dbm.purge_old_runs(db, tmp_path / "runs", days=1) == []  # and never purged as someone's check


def test_rubric_lists_points_per_stage_from_the_scoring_rules(app):
    with client_for(app, None) as c:
        body = c.get("/api/rubric").json()
    assert [s["key"] for s in body["stages"]] == ["discover", "details", "checkout", "payment", "outcome"]
    assert sum(s["points"] for s in body["stages"]) == 100
    assert sum(s["checks"] for s in body["stages"]) == len(CHECKS)
