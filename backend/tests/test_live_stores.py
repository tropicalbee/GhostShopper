"""Real-world behaviour: any URL, browse-only live stores, polite visiting, platform detection,
plain-English fixes and the developer summary. Live stores are mocked as local fixture sites."""

import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.app import db
from backend.app.agent.loop import RunConfig, run_shopper
from backend.app.agent.platform import detect_platform
from backend.app.agent.recorder import load_run
from backend.app.agent.site import Politeness, SiteError, is_demo_store, normalize, preflight
from backend.app.devsummary import developer_summary
from backend.app.eval.navigator import ScriptedNavigator
from backend.app.eval.server import LiveServer
from backend.app.plain import PLAIN, narrate, plain_fix, status_for
from backend.app.failures import FAILURE_TYPES, STORE

from .test_agent_e2e import requires_browser

SITES = Path(__file__).parent / "fixtures" / "sites"
JARGON = ("json-ld", "jsonld", "selector", "dom", "schema.org", "<div", "css")


def site_server(name: str) -> LiveServer:
    app = FastAPI()
    app.mount("/", StaticFiles(directory=SITES / name, html=True))
    return LiveServer(app)


async def live_run(tmp_path, name: str) -> dict:
    with site_server(name) as srv:
        cfg = RunConfig(store_url=f"{srv.url}/", db_path=tmp_path / "live.db", runs_dir=tmp_path / "runs",
                        target_product=None, live=True, allow_private=True, max_steps=30,
                        politeness=Politeness(min_interval_s=0.05, allow_private=True))
        run_id = await run_shopper(cfg, ScriptedNavigator(None))
    return load_run(tmp_path / "live.db", run_id)


def status(run, key):
    return next(c for c in run["checks"] if c["check_key"] == key)


# --- Platform detection (pure) ---

@pytest.mark.parametrize("signals,expected", [
    ({"globals": ["Shopify"], "links": ["https://x.myshopify.com/"]}, "shopify"),
    ({"scripts": ["https://cdn.shopify.com/s/files/theme.js"]}, "shopify"),
    ({"generator": "Wix.com Website Builder"}, "wix"),
    ({"scripts": ["https://static.parastorage.com/services/x.js"]}, "wix"),
    ({"generator": "WooCommerce 9.3.1"}, "woocommerce"),
    ({"body_class": "home woocommerce-page woocommerce"}, "woocommerce"),
    ({"scripts": ["https://example.com/wp-content/plugins/woocommerce/assets/js/x.js"]}, "woocommerce"),
    ({"generator": "Hugo 0.120", "scripts": ["/app.js"]}, "unknown"),
    ({}, "unknown"),
])
def test_platform_detection(signals, expected):
    result = detect_platform(signals)
    assert result["platform"] == expected
    assert bool(result["evidence"]) == (expected != "unknown")


# --- Plain English (pure) ---

def test_every_store_failure_has_a_plain_jargon_free_fix():
    for code, ft in FAILURE_TYPES.items():
        if ft.cause != STORE or code in ("not_tested",):
            continue
        p = PLAIN.get(code)
        assert p is not None, f"no plain fix for {code}"
        text = " ".join([p.title, p.why, p.how, *p.steps.values()]).lower()
        assert not any(j in text for j in JARGON), f"jargon in plain text for {code}"
        assert len(re.findall(r"[.!?](\s|$)", p.why)) <= 1, f"'why' should be one sentence for {code}"


def test_platform_steps_are_used_when_the_platform_is_known():
    shop = plain_fix("price_image_only", "shopify")
    assert shop["platform"] == "shopify" and shop["steps"].startswith("In Shopify:")
    wix = plain_fix("price_image_only", "wix")
    assert "Price box" in wix["steps"]
    unknown = plain_fix("price_image_only", "unknown")
    assert unknown["steps"] is None and unknown["how"]


def test_status_always_has_words():
    assert status_for(100, 84) == {"level": "good", "text": "Ready for AI shoppers"}
    assert status_for(60, 100)["level"] == "warn"
    assert status_for(29, 80)["level"] == "bad"
    assert status_for(0, 0)["level"] == "unknown"


def test_narration_is_plain_language():
    steps = [{"id": 1, "idx": 0, "tool": "open_page", "ok": 1, "observation": "HTTP 200. Now on: Shop (http://x/)"},
             {"id": 2, "idx": 1, "tool": "click", "ok": 1, "observation": "Clicked e5 'Speckled Stoneware Mug'. Now on: x"}]
    checks = [{"step_id": 2, "check_key": "product_found", "passed": 1,
               "evidence": {"title": "Speckled Stoneware Mug | Fernhill"}},
              {"step_id": 2, "check_key": "price_in_text", "passed": 0, "cause": "store", "evidence": {}}]
    feed = [f["text"] for f in narrate(steps, checks)]
    assert feed == ["Opened Shop", "Clicked “Speckled Stoneware Mug”", "Found your Speckled Stoneware Mug",
                    "Couldn't read the price"]


# --- URLs and politeness ---

def test_urls_are_normalised_with_friendly_errors():
    assert normalize("yourshop.com") == "https://yourshop.com/"
    with pytest.raises(SiteError, match="doesn't look like a web address"):
        normalize("not a url")
    with pytest.raises(SiteError, match="Paste the address"):
        normalize("  ")
    assert is_demo_store("http://localhost:8000/store/", "http://localhost:8000")
    assert not is_demo_store("https://yourshop.com/store/", "http://localhost:8000")


@pytest.mark.anyio
async def test_unknown_domain_gets_a_friendly_message():
    with pytest.raises(SiteError, match="couldn't find that website"):
        await preflight("https://ghostshopper-does-not-exist.invalid/", "http://localhost:8000")


@pytest.mark.anyio
async def test_private_addresses_are_refused_when_deployed(monkeypatch):
    monkeypatch.setenv("ALLOW_PRIVATE_URLS", "false")
    with pytest.raises(SiteError, match="only check public websites"):
        await preflight("http://127.0.0.1:9/", "https://ghostshopper.onrender.com")


@pytest.mark.anyio
async def test_robots_txt_disallow_is_respected_before_starting(monkeypatch):
    monkeypatch.setenv("ALLOW_PRIVATE_URLS", "true")
    with site_server("robots-all") as srv:
        with pytest.raises(SiteError, match="robots.txt asks automated visitors"):
            await preflight(f"{srv.url}/", "http://localhost:8000")


@pytest.mark.anyio
async def test_politeness_waits_between_page_loads(monkeypatch):
    import time

    monkeypatch.setenv("ALLOW_PRIVATE_URLS", "true")
    with site_server("shopify") as srv:
        polite = Politeness(min_interval_s=0.3, allow_private=True)
        started = time.monotonic()
        for _ in range(3):
            await polite.wait_turn(f"{srv.url}/")
        await polite.aclose()
    assert time.monotonic() - started >= 0.6  # three loads, two gaps


# --- Live runs on mocked platforms ---

pytestmark_anyio = pytest.mark.anyio


@requires_browser
@pytest.mark.anyio
@pytest.mark.parametrize("name,platform", [("shopify", "shopify"), ("wix", "wix"), ("woocommerce", "woocommerce")])
async def test_live_store_is_checked_up_to_paypal_and_never_pays(tmp_path, name, platform):
    run = await live_run(tmp_path, name)
    assert run["live"] is True and run["platform"] == platform
    assert run["status"] == "completed", run["error"]
    assert run["outcome"] == "paypal_ready"
    pp = status(run, "paypal_button_found")
    assert pp["passed"] == 1 and "Not clicked" in pp["reason"]
    for key in ("popup_opened", "payment_approved", "capture_completed", "payment_verified"):
        c = status(run, key)
        assert (c["status"], c["code"]) == ("excluded", "live_store_browse_only"), key
    assert run["order"] is None and run["paypal_mode"] == "off"
    with db.connect(tmp_path / "live.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0
    card = run["scorecard"]
    assert (card["total"], card["possible"]) == (100, 84)  # perfect store, judged on what it controls
    assert {n["check"] for n in card["not_checked_live"]} == {"popup_opened", "payment_approved",
                                                              "capture_completed", "payment_verified"}
    assert card["not_store_fault"] == []
    assert card["simple"]["status"] == "good"
    assert any("PayPal" in f["text"] for f in run["feed"])


@requires_browser
@pytest.mark.anyio
async def test_store_without_paypal_gets_a_plain_fix(tmp_path):
    run = await live_run(tmp_path, "unknown")
    assert run["platform"] == "unknown"
    pp = status(run, "paypal_button_found")
    assert (pp["passed"], pp["code"], pp["cause"]) == (0, "paypal_button_missing", "store")
    top = run["scorecard"]["simple"]["top_fixes"][0]
    assert top["title"] == "AI shoppers couldn't find a PayPal button"
    assert top["steps"] is None and top["how"]  # platform unknown: the generic how-to


@requires_browser
@pytest.mark.anyio
async def test_bot_check_is_reported_as_not_the_stores_fault(tmp_path):
    run = await live_run(tmp_path, "blocked")
    assert run["outcome"] == "blocked" and run["end_reason"] == "site_blocked"
    pf = status(run, "product_found")
    assert (pf["code"], pf["cause"]) == ("site_blocked", "environment")
    card = run["scorecard"]
    assert card["possible"] == 0 and card["simple"]["status"] == "unknown"
    assert any("blocked our visit" in n["plain"] for n in card["not_store_fault"])


@requires_browser
@pytest.mark.anyio
async def test_robots_disallowed_pages_are_never_opened(tmp_path):
    run = await live_run(tmp_path, "robots-products")
    assert run["status"] == "completed"
    assert any("robots.txt" in (s["observation"] or "") for s in run["steps"])
    assert status(run, "product_found")["passed"] == 0  # it never loaded the disallowed product page


@requires_browser
@pytest.mark.anyio
async def test_developer_summary_is_technical_and_complete(tmp_path):
    run = await live_run(tmp_path, "unknown")
    md = developer_summary(run)
    assert md.startswith(f"# GhostShopper report: run {run['id']}")
    assert "live store (browse-only, no payment)" in md
    assert "paypal_button_missing" in md and "## Not counted against the store" not in md
    assert "Payment steps only tested on the demo store" not in md
    assert "## Not tested in this run" not in md or "popup_opened" not in md.split("## Not tested in this run")[1]


def test_live_store_refuses_purchases():
    import asyncio

    from backend.app.agent.service import RunConfigError, RunRequest, resolve_target

    async def go():
        return await resolve_target(RunRequest(store_url="https://ghostshopper-does-not-exist.invalid/", checkout=True),
                                    "http://localhost:8000")

    with pytest.raises(RunConfigError):
        asyncio.run(go())
