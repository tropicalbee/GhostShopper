"""Run-start race, example protection, SQLite settings, caches, pagination and response headers."""

import asyncio
import dataclasses
import sqlite3
from pathlib import Path

import httpx
import pytest

from backend.app import db as dbm
from backend.app import market, runs
from backend.app.agent import recorder
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.owner import COOKIE
from backend.tests.test_access import ALICE, BOB, client_for, make_run
from backend.tests.test_access import settings as access_settings
from store.app import admin_cookie_value
from store.flaws import FlawStore


def dev_settings(tmp_path: Path, **kw) -> Settings:
    return Settings("", "", tmp_path / "a.db", "http://localhost:8000", paypal_mode="mock", dev_options=True,
                    runs_dir=tmp_path / "runs", frontend_dist=tmp_path / "dist", **kw)


@pytest.fixture(autouse=True)
def fresh_caches():
    recorder.clear_run_cache()
    market.clear_market_cache()
    yield
    recorder.clear_run_cache()
    market.clear_market_cache()


def async_client(app, token: str = ALICE) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000",
                             cookies={COOKIE: token})


# --- 1. Run-start race ---

@pytest.mark.anyio
async def test_two_simultaneous_starts_let_exactly_one_through(tmp_path, monkeypatch):
    calls = []

    async def slow_execute(req, url, db_path, on_start=None, **kw):
        calls.append(url)
        await asyncio.sleep(0.2)
        on_start(1)
        await asyncio.sleep(0.5)

    monkeypatch.setattr(runs, "execute", slow_execute)
    app = create_app(dev_settings(tmp_path))
    async with async_client(app) as c:
        a, b = await asyncio.gather(c.post("/api/runs", json={}), c.post("/api/runs", json={}))
        assert sorted([a.status_code, b.status_code]) == [202, 409]
        assert len(calls) == 1
        assert app.state.run_lock.locked()  # the worker still holds it
        await asyncio.gather(*app.state.run_tasks)
        await asyncio.sleep(0.05)
        assert not app.state.run_lock.locked()  # and releases it when done


@pytest.mark.anyio
async def test_a_start_that_times_out_cancels_the_task_and_frees_the_lock(tmp_path, monkeypatch):
    cancelled = asyncio.Event()

    async def never_starts(req, url, db_path, on_start=None, **kw):
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(runs, "execute", never_starts)
    monkeypatch.setattr(runs, "START_TIMEOUT_S", 0.2)
    app = create_app(dev_settings(tmp_path))
    async with async_client(app) as c:
        r = await c.post("/api/runs", json={})
        assert r.status_code == 500 and r.json()["detail"]["error"] == "RUN_START_FAILED"
        await asyncio.wait_for(cancelled.wait(), 2)  # no ghost run behind the client's back
        await asyncio.sleep(0.05)
        assert not app.state.run_lock.locked()
        assert not app.state.run_tasks


@pytest.mark.anyio
async def test_a_failed_start_frees_the_lock(tmp_path, monkeypatch):
    async def boom(req, url, db_path, on_start=None, **kw):
        raise RuntimeError("no browser")

    monkeypatch.setattr(runs, "execute", boom)
    app = create_app(dev_settings(tmp_path))
    async with async_client(app) as c:
        assert (await c.post("/api/runs", json={})).status_code == 500
        await asyncio.sleep(0.05)
        assert not app.state.run_lock.locked()


# --- 2. LLM clients are closed ---

@pytest.mark.anyio
async def test_start_closes_the_validation_llm_and_explain_closes_its_llm(tmp_path, monkeypatch):
    closed = []

    class Closable:
        model = "m"

        def __init__(self, name):
            self.name = name

        async def aclose(self):
            closed.append(self.name)

    async def quick_execute(req, url, db_path, on_start=None, **kw):
        on_start(1)

    async def fake_explain(db_path, run_id, llm):
        return []

    monkeypatch.setattr(runs, "execute", quick_execute)
    monkeypatch.setattr(runs, "prepare", lambda *a, **k: (Closable("probe-llm"), Closable("probe-pay")))
    monkeypatch.setattr(runs, "make_llm", lambda *a, **k: Closable("explain-llm"))
    monkeypatch.setattr(runs, "explain_run", fake_explain)
    app = create_app(dev_settings(tmp_path))
    mine = make_run(tmp_path / "a.db", ALICE)
    async with async_client(app) as c:
        assert (await c.post("/api/runs", json={})).status_code == 202
        assert (await c.post(f"/api/runs/{mine}/explain", json={})).status_code == 200
    assert {"probe-llm", "probe-pay", "explain-llm"} <= set(closed)


# --- 3. Examples can't be rewritten through explain ---

def test_explain_on_an_example_is_forbidden_and_other_peoples_runs_stay_404(tmp_path):
    app = create_app(access_settings(tmp_path))
    example = make_run(tmp_path / "a.db", None)
    alices = make_run(tmp_path / "a.db", ALICE)
    with client_for(app, BOB) as bob:
        r = bob.post(f"/api/runs/{example}/explain", json={})
        assert r.status_code == 403 and r.json()["detail"]["error"] == "EXAMPLE"
        assert bob.post(f"/api/runs/{alices}/explain", json={}).status_code == 404
        assert bob.post("/api/runs/99999/explain", json={}).status_code == 404


# --- 5. SQLite settings and indexes ---

def test_indexes_exist_and_a_second_init_is_a_noop(tmp_path):
    path = tmp_path / "i.db"
    dbm.init_db(path)

    def snapshot():
        with dbm.connect(path) as conn:
            return sorted(r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'"))

    before = snapshot()
    for name in ("idx_runs_owner_store_id", "idx_runs_started_at", "idx_steps_run_idx", "idx_orders_run"):
        assert name in before
    dbm.init_db(path)
    assert snapshot() == before
    with dbm.connect(path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    with sqlite3.connect(path) as raw:
        assert raw.execute("PRAGMA index_info(idx_runs_owner_store_id)").fetchall()[0][2] == "owner_hash"


def test_the_store_connection_waits_for_a_busy_database(tmp_path):
    from store.flaws import FlawStore

    store = FlawStore(tmp_path / "f.db")
    with store._connect() as conn:
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


# --- 7. load_run cache ---

def test_finished_runs_are_cached_and_invalidated_by_explain_and_delete(tmp_path, monkeypatch):
    app = create_app(access_settings(tmp_path))
    db = tmp_path / "a.db"
    run = make_run(db, ALICE)
    builds = []
    real = recorder._build_run

    async def fake_explain(db_path, run_id, llm):
        return []

    monkeypatch.setattr(recorder, "_build_run", lambda *a: builds.append(a) or real(*a))
    monkeypatch.setattr(runs, "explain_run", fake_explain)
    monkeypatch.setattr(runs, "make_llm", lambda *a, **k: type("L", (), {"model": "m"})())
    with client_for(app, ALICE) as alice, client_for(app, BOB) as bob:
        first = alice.get(f"/api/runs/{run}").json()
        assert alice.get(f"/api/runs/{run}").json() == first
        assert len(builds) == 1  # the second poll came from the cache
        assert bob.get(f"/api/runs/{run}").status_code == 404  # the ownership check still runs on a cached run
        assert alice.post(f"/api/runs/{run}/explain", json={}).status_code == 200
        alice.get(f"/api/runs/{run}")
        assert len(builds) == 2  # explain invalidated it
        assert alice.delete(f"/api/runs/{run}").status_code == 204
        assert alice.get(f"/api/runs/{run}").status_code == 404
        assert bob.get(f"/api/runs/{run}").status_code == 404


def test_callers_cannot_corrupt_the_cache_and_running_runs_are_never_cached(tmp_path):
    db = tmp_path / "a.db"
    run = make_run(db, ALICE)
    first = recorder.load_run(db, run)
    first["owner_hash"] = "tampered"
    first["checks"].clear()
    again = recorder.load_run(db, run)
    assert again["owner_hash"] != "tampered" and again["checks"]
    with dbm.connect(db) as conn:
        conn.execute("UPDATE runs SET status = 'running' WHERE id = ?", (run,))
    recorder.clear_run_cache()
    assert recorder.load_run(db, run)["status"] == "running"
    with dbm.connect(db) as conn:
        conn.execute("UPDATE runs SET status = 'awaiting_human' WHERE id = ?", (run,))
    assert recorder.load_run(db, run)["status"] == "awaiting_human"  # a stale 'running' was not kept
    assert not recorder._cache


def test_the_cache_is_per_database_and_bounded(tmp_path, monkeypatch):
    a, b = tmp_path / "a.db", tmp_path / "b.db"
    ra, rb = make_run(a, None, store="https://one.example/"), make_run(b, None, store="https://two.example/")
    assert ra == rb == 1
    assert recorder.load_run(a, 1)["store_url"] != recorder.load_run(b, 1)["store_url"]
    monkeypatch.setattr(recorder, "CACHE_SIZE", 2)
    ids = [make_run(a, None) for _ in range(3)]
    for i in ids:
        recorder.load_run(a, i)
    assert len(recorder._cache) == 2


# --- 8. Market cache ---

@pytest.mark.anyio
async def test_market_results_are_cached_for_ten_minutes_but_errors_are_not(monkeypatch):
    from store import catalog

    monkeypatch.delenv("CHANNEL3_API_KEY", raising=False)
    product = catalog.get_by_sku("FH-MUG-01")
    searches = []

    class Counting:
        source = "recorded"

        async def search(self, query, sku, limit=20):
            searches.append(sku)
            if len(searches) == 1:
                raise market.MarketError("down")
            return await market.RecordedSearch().search(query, sku, limit)

    monkeypatch.setattr(market, "make_search", Counting)
    with pytest.raises(market.MarketError):
        await market.market_check(product)
    first = await market.market_check(product)  # the error was not stored
    second = await market.market_check(product)
    assert len(searches) == 2 and first == second
    second["verdict"] = "tampered"
    assert (await market.market_check(product))["verdict"] != "tampered"
    clock = market.time.monotonic()
    monkeypatch.setattr(market.time, "monotonic", lambda: clock + market.MARKET_CACHE_TTL_S + 1)
    await market.market_check(product)
    assert len(searches) == 3  # expired


# --- 9. Pagination ---

def test_runs_paginate_with_limit_and_before(tmp_path):
    app = create_app(access_settings(tmp_path))
    ids = [make_run(tmp_path / "a.db", ALICE) for _ in range(5)]
    make_run(tmp_path / "a.db", BOB)
    with client_for(app, ALICE) as c:
        page1 = c.get("/api/runs?limit=2").json()
        assert [r["id"] for r in page1] == ids[::-1][:2]
        page2 = c.get(f"/api/runs?limit=2&before={page1[-1]['id']}").json()
        assert [r["id"] for r in page2] == ids[::-1][2:4]
        page3 = c.get(f"/api/runs?limit=2&before={page2[-1]['id']}").json()
        assert [r["id"] for r in page3] == ids[:1] and len(page3) < 2  # fewer than limit: the end
        assert len(c.get("/api/runs").json()) == 5  # default limit 50, only my runs
        for bad in ("limit=0", "limit=101", "before=0", "limit=x"):
            assert c.get(f"/api/runs?{bad}").status_code == 422, bad


# --- 10. Compression and cache headers ---

def test_cache_and_compression_headers(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>GhostShopper</title>", encoding="utf-8")
    (dist / "assets" / "app-abc123.js").write_text("export const x = 1;\n" * 200, encoding="utf-8")
    app = create_app(access_settings(tmp_path))
    run = make_run(tmp_path / "a.db", ALICE, runs_dir=tmp_path / "runs")
    with client_for(app, ALICE) as c:
        assets = c.get("/assets/app-abc123.js")
        assert assets.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert assets.headers["content-encoding"] == "gzip" and "export const x = 1;" in assets.text  # decodes
        assert c.get("/").headers["cache-control"] == "no-cache"
        assert c.get("/api/rubric").headers["cache-control"] == "public, max-age=3600"
        assert c.get("/api/health").headers["cache-control"] == "private, no-store"
        assert c.get("/api/runs").headers["cache-control"] == "private, no-store"
        assert c.get(f"/api/runs/{run}/files/step-0.png").headers["cache-control"] == "private, max-age=3600"
        assert c.get("/api/runs/999999").headers["cache-control"] == "private, no-store"  # errors too
        big = c.get(f"/api/runs/{run}")
        assert big.headers["content-encoding"] == "gzip" and big.json()["id"] == run
        raw = c.get(f"/api/runs/{run}", headers={"Accept-Encoding": "identity"})
        assert "content-encoding" not in raw.headers and raw.json()["id"] == run
        assert c.get("/api/health").headers["x-content-type-options"] == "nosniff"  # other middleware intact


def test_a_response_that_sets_the_owner_cookie_is_never_publicly_cacheable(tmp_path):
    app = create_app(access_settings(tmp_path))
    with client_for(app, None) as c:
        r = c.get("/api/rubric")
    assert COOKIE in r.headers["set-cookie"]
    assert r.headers["cache-control"] == "private, max-age=3600"


def test_health_keeps_its_keys(tmp_path):
    with client_for(create_app(access_settings(tmp_path)), None) as c:
        assert set(c.get("/api/health").json()) == {"status", "paypal_configured", "paypal_env", "paypal_mode",
                                                    "groq_configured", "demo_admin_open", "retention_days",
                                                    "real_checkout_available", "real_checkout_missing",
                                                    "real_payment_allowed"}


# --- Per-run PayPal mode on a deployed server ---

REAL_ENV = {"KERNEL_API_KEY": "k-1", "SANDBOX_BUYER_EMAIL": "b@example.com", "SANDBOX_BUYER_PASSWORD": "pw"}


def deployed(tmp_path: Path, **kw) -> Settings:
    return Settings(kw.pop("client_id", ""), kw.pop("client_secret", ""), tmp_path / "a.db", "https://ghostshopper.example",
                    paypal_mode="mock", runs_dir=tmp_path / "runs", frontend_dist=tmp_path / "dist",
                    demo_admin_token=PRESENTER, **kw)


PRESENTER = "t0ken-for-the-presenter"


def unlock(c):
    c.cookies.set("fh_admin", admin_cookie_value(PRESENTER))
    return c


def capture_start(monkeypatch):
    """Replace the run itself; returns the RunRequest the server built and the PayPal mode active during it."""
    seen = {}

    async def fake_execute(req, url, db_path, on_start=None, server=None, **kw):
        seen.update(req=req, server=server)
        on_start(1)

    monkeypatch.setattr(runs, "execute", fake_execute)
    monkeypatch.setattr(runs, "prepare", lambda *a, **k: (None, None))
    return seen


def test_a_deployed_server_runs_mock_paypal_by_default(tmp_path, monkeypatch):
    seen = capture_start(monkeypatch)
    app = create_app(deployed(tmp_path))
    with client_for(app, ALICE) as c:
        r = c.post("/api/runs", json={})
    assert r.status_code == 202
    assert seen["req"].paypal == "mock" and seen["req"].checkout and seen["req"].headless


def test_the_real_option_is_refused_naming_what_is_missing(tmp_path, monkeypatch):
    for key in REAL_ENV:
        monkeypatch.delenv(key, raising=False)
    seen = capture_start(monkeypatch)
    app = create_app(deployed(tmp_path))
    with unlock(client_for(app, ALICE)) as c:
        health = c.get("/api/health").json()
        r = c.post("/api/runs", json={"real_payment": True})
    assert health["real_checkout_available"] is False
    assert r.status_code == 400 and r.json()["detail"]["error"] == "RUN_CONFIG"
    message = r.json()["detail"]["message"]
    assert all(name in message for name in ("PAYPAL_CLIENT_ID", "KERNEL_API_KEY", "SANDBOX_BUYER_EMAIL"))
    assert not seen  # no silent fallback to the mock


def test_the_real_option_needs_the_kernel_key_even_with_paypal_keys(tmp_path, monkeypatch):
    for key, value in REAL_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("KERNEL_API_KEY")
    capture_start(monkeypatch)
    app = create_app(deployed(tmp_path, client_id="id", client_secret="secret"))
    with unlock(client_for(app, ALICE)) as c:
        r = c.post("/api/runs", json={"real_payment": True})
    assert r.status_code == 400 and "KERNEL_API_KEY" in r.json()["detail"]["message"]
    assert "PAYPAL_CLIENT_ID" not in r.json()["detail"]["message"]


def test_the_real_option_runs_the_sandbox_in_a_visible_kernel_browser(tmp_path, monkeypatch):
    for key, value in REAL_ENV.items():
        monkeypatch.setenv(key, value)
    seen = capture_start(monkeypatch)
    app = create_app(deployed(tmp_path, client_id="id", client_secret="secret"))
    with unlock(client_for(app, ALICE)) as c:
        assert c.get("/api/health").json()["real_checkout_available"] is True
        r = c.post("/api/runs", json={"real_payment": True})
        assert r.status_code == 202
    req = seen["req"]
    assert (req.paypal, req.browser, req.headless, req.checkout) == ("sandbox", "kernel", False, True)
    assert seen["server"].paypal_mode == "sandbox" and seen["server"].paypal_configured


def test_the_real_option_does_not_unlock_developer_options_or_live_stores(tmp_path, monkeypatch):
    for key, value in REAL_ENV.items():
        monkeypatch.setenv(key, value)
    capture_start(monkeypatch)
    app = create_app(deployed(tmp_path, client_id="id", client_secret="secret"))
    with unlock(client_for(app, ALICE)) as c:
        r = c.post("/api/runs", json={"real_payment": True, "max_steps": 5})
        assert r.status_code == 400 and "max_steps" in r.json()["detail"]["message"]
        r = c.post("/api/runs", json={"real_payment": True, "store_url": "https://shop.example"})
        assert r.status_code == 400 and "demo store" in r.json()["detail"]["message"]


@pytest.mark.anyio
async def test_the_store_and_orders_follow_the_active_mode_and_reset_after_the_run(tmp_path, monkeypatch):
    for key, value in REAL_ENV.items():
        monkeypatch.setenv(key, value)
    modes = []

    pages = []

    async def fake_execute(req, url, db_path, on_start=None, **kw):
        modes.append(app.state.paypal_active)
        pages.append((await async_client(app).get("/store/checkout?sku=FH-MUG-01")).text)  # what the shopper would load
        on_start(1)

    monkeypatch.setattr(runs, "execute", fake_execute)
    monkeypatch.setattr(runs, "prepare", lambda *a, **k: (None, None))
    app = create_app(deployed(tmp_path, client_id="id", client_secret="secret"))
    FlawStore(app.state.settings.database_path).set_many({"extra_checkout_step": False})  # straight to the PayPal page
    async with unlock(async_client(app)) as c:
        assert (await c.post("/api/runs", json={"real_payment": True})).status_code == 202
        await asyncio.gather(*app.state.run_tasks)
        await asyncio.sleep(0.05)
        assert modes == ["sandbox"] and app.state.paypal_active == "mock"
        page = (await c.get("/store/checkout?sku=FH-MUG-01")).text
    assert "/mock-paypal/sdk.js" in page  # back to the default store page
    assert "paypal.com/web-sdk/v6/core" in pages[0] and "/mock-paypal/" not in pages[0]


def test_the_real_option_is_locked_without_the_presenter_cookie(tmp_path, monkeypatch):
    for key, value in REAL_ENV.items():
        monkeypatch.setenv(key, value)
    seen = capture_start(monkeypatch)
    app = create_app(deployed(tmp_path, client_id="id", client_secret="secret"))
    with client_for(app, ALICE) as c:
        assert c.get("/api/health").json()["real_payment_allowed"] is False
        r = c.post("/api/runs", json={"real_payment": True})
        assert r.status_code == 403 and r.json()["detail"]["error"] == "REAL_PAYMENT_LOCKED"
        c.cookies.set("fh_admin", "wrong-token")
        assert c.post("/api/runs", json={"real_payment": True}).status_code == 403
        assert c.post("/api/runs", json={}).status_code == 202  # the practice PayPal stays open to everyone
    assert seen["req"].paypal == "mock"


def test_the_real_option_works_with_the_presenter_cookie(tmp_path, monkeypatch):
    for key, value in REAL_ENV.items():
        monkeypatch.setenv(key, value)
    capture_start(monkeypatch)
    app = create_app(deployed(tmp_path, client_id="id", client_secret="secret"))
    with unlock(client_for(app, ALICE)) as c:
        assert c.get("/api/health").json()["real_payment_allowed"] is True
        assert c.post("/api/runs", json={"real_payment": True}).status_code == 202


def test_the_unlock_form_sets_a_cookie_the_api_accepts(tmp_path):
    app = create_app(deployed(tmp_path))
    with client_for(app, ALICE) as c:
        assert c.post("/store/admin/unlock", data={"token": PRESENTER}, follow_redirects=False).status_code == 303
        assert c.get("/api/health").json()["real_payment_allowed"] is True


def test_a_dev_server_needs_no_unlock_for_the_real_option(tmp_path, monkeypatch):
    for key, value in REAL_ENV.items():
        monkeypatch.setenv(key, value)
    capture_start(monkeypatch)
    app = create_app(dataclasses.replace(dev_settings(tmp_path), paypal_client_id="id", paypal_client_secret="secret"))
    with client_for(app, ALICE) as c:
        assert c.get("/api/health").json()["real_payment_allowed"] is True
        assert c.post("/api/runs", json={"real_payment": True}).status_code == 202
