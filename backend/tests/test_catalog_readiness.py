"""Catalog readiness: JSON-LD field detection, the demo store under its existing flaws, sitemap and link discovery on
Shopify-like local sites, and the endpoint's rate limit and public-host rule. Everything runs against local servers."""

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from backend.app import catalog_readiness as cr
from backend.app.agent.service import apply_flaws
from backend.app.catalog_readiness import CatalogError, check_catalog, fields_present, machine_readable, summary_line
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.ratelimit import RateLimiter

from .live_server import LiveServer
from .test_live_stores import site_server

pytestmark = pytest.mark.anyio

FULL = {"@type": "Product", "name": "Mug", "sku": "M1", "image": "https://x/m.jpg",
        "offers": {"@type": "Offer", "price": "24.00", "priceCurrency": "USD", "availability": "https://schema.org/InStock"}}
LOCAL = "http://localhost:8000"


def test_a_complete_product_is_machine_readable():
    present = fields_present([FULL])
    assert all(present.values()) and machine_readable(present)


@pytest.mark.parametrize("field", ["price", "priceCurrency", "availability"])
def test_each_missing_offer_field_makes_the_product_unreadable(field):
    block = {**FULL, "offers": {k: v for k, v in FULL["offers"].items() if k != field}}
    present = fields_present([block])
    assert present[field] is False and not machine_readable(present)


def test_sku_and_image_are_recorded_but_not_required():
    present = fields_present([{k: v for k, v in FULL.items() if k not in ("sku", "image")}])
    assert (present["sku"], present["image"]) == (False, False) and machine_readable(present)
    assert fields_present([{**FULL, "sku": None, "gtin13": "123"}])["sku"] is True


def test_no_product_type_means_nothing_is_present():
    assert not any(fields_present([{"@type": "Organization", "name": "Shop"}]).values())


def test_offer_lists_graphs_and_blank_values_are_handled():
    graph = {"@graph": [{"@type": "WebSite"}, {**FULL, "offers": [FULL["offers"]]}]}
    assert machine_readable(fields_present([graph]))
    assert not machine_readable(fields_present([{**FULL, "offers": {**FULL["offers"], "priceCurrency": " "}}]))


def test_summary_line_is_computed_text():
    assert summary_line(5, 12) == "5 of 12 products are machine-readable (42%). PayPal's benchmark is 80% of the catalog."
    assert summary_line(1, 1).startswith("1 of 1 product is machine-readable (100%)")


@pytest.fixture
def demo(tmp_path):
    settings = Settings(paypal_client_id="", paypal_client_secret="", database_path=tmp_path / "c.db",
                        app_base_url="http://unused", dev_options=True)
    with LiveServer(create_app(settings)) as srv:
        yield srv


async def demo_report(srv, flaws: str) -> dict:
    await apply_flaws(f"{srv.url}/store/", flaws)
    return await check_catalog(None, srv.url)


async def test_demo_store_with_no_flaws_is_fully_readable(demo):
    r = await demo_report(demo, "off")
    assert (r["products_checked"], r["machine_readable"], r["percent"]) == (12, 12, 100)
    assert r["meets_benchmark"] is True and r["source"] == "demo store" and r["errors"] == []


async def test_no_structured_data_leaves_none(demo):
    r = await demo_report(demo, "no_structured_data")
    assert (r["machine_readable"], r["products_checked"], r["percent"]) == (0, 12, 0)
    assert r["meets_benchmark"] is False and "product" in r["per_product"][0]["missing"]


async def test_currency_missing_costs_every_product_its_currency(demo):
    r = await demo_report(demo, "currency_missing")
    assert (r["machine_readable"], r["products_checked"]) == (0, 12)
    assert all(p["missing"] == ["priceCurrency"] for p in r["per_product"])


async def test_sold_out_products_still_count_because_they_state_their_availability(demo):
    assert (await demo_report(demo, "oos_buyable"))["machine_readable"] == 12


async def test_demo_store_is_never_cached_so_flaw_toggles_show_at_once(demo):
    assert (await demo_report(demo, "off"))["machine_readable"] == 12
    assert (await demo_report(demo, "no_structured_data"))["machine_readable"] == 0


async def test_links_on_the_home_page_find_products_on_a_shopify_like_store():
    cr._cache.clear()
    with site_server("shopify") as srv:
        r = await check_catalog(f"{srv.url}/", LOCAL, min_interval_s=0.01)
    assert r["source"] == "live store" and (r["products_checked"], r["machine_readable"]) == (1, 1)
    assert r["per_product"][0]["name"] == "Speckled Stoneware Mug"
    assert r["per_product"][0]["missing"] == ["image"]


async def test_sitemap_index_is_followed_to_the_product_sitemap_and_capped_at_twelve(tmp_path):
    cr._cache.clear()
    ld = ('<script type="application/ld+json">{"@type":"Product","name":"P%d","offers":'
          '{"price":"1","priceCurrency":"USD","availability":"InStock"}}</script>')
    for i in range(15):
        d = tmp_path / "products" / f"p{i}"
        d.mkdir(parents=True)
        (d / "index.html").write_text(f"<html><title>P{i}</title>{ld % i}</html>")
    (tmp_path / "index.html").write_text("<html><title>Shop</title></html>")
    app = FastAPI()
    app.mount("/", StaticFiles(directory=tmp_path, html=True))
    srv = LiveServer(app)
    (tmp_path / "sitemap.xml").write_text(
        f"<sitemapindex><sitemap><loc>{srv.url}/sitemap_pages_1.xml</loc></sitemap>"
        f"<sitemap><loc>{srv.url}/sitemap_products_1.xml</loc></sitemap></sitemapindex>")
    (tmp_path / "sitemap_products_1.xml").write_text("<urlset>" + "".join(
        f"<url><loc>{srv.url}/products/p{i}/</loc></url>" for i in range(15))
        + "<url><loc>https://other.example/products/x</loc></url></urlset>")
    with srv:
        r = await check_catalog(f"{srv.url}/", LOCAL, min_interval_s=0.01)
    assert (r["products_checked"], r["machine_readable"]) == (12, 12)
    assert all(p["url"].startswith(srv.url) for p in r["per_product"])


async def test_a_store_with_no_product_pages_is_an_explicit_error():
    cr._cache.clear()
    with site_server("blocked") as srv, pytest.raises(CatalogError):
        await check_catalog(f"{srv.url}/", LOCAL, min_interval_s=0.01)


async def test_live_results_are_cached_for_ten_minutes():
    cr._cache.clear()
    with site_server("shopify") as srv:
        first = await check_catalog(f"{srv.url}/", LOCAL, min_interval_s=0.01)
        second = await check_catalog(f"{srv.url}/", LOCAL, min_interval_s=0.01)
    assert second is first


@pytest.fixture
def deployed(tmp_path, monkeypatch):
    """The router on its own app, as main.py includes it, with deployed-mode settings (main.py is not edited here)."""
    monkeypatch.setenv("ALLOW_PRIVATE_URLS", "false")
    app = FastAPI()
    app.state.settings = Settings(paypal_client_id="", paypal_client_secret="", database_path=tmp_path / "d.db",
                                  app_base_url="https://ghostshopper.example", dev_options=False)
    app.state.api_limiter = RateLimiter(*app.state.settings.api_rate_limit)

    @app.middleware("http")
    async def owner(request, call_next):
        request.state.owner = "test-owner"
        return await call_next(request)

    app.include_router(cr.router)
    with TestClient(app) as c:
        yield c


def test_private_live_url_is_refused_when_deployed(deployed):
    r = deployed.get("/api/catalog", params={"store_url": "http://127.0.0.1:9/"})
    assert r.status_code == 400
    assert r.json()["detail"] == {"error": "CATALOG_UNAVAILABLE", "message": "For safety we can only check public websites."}


def test_catalog_endpoint_is_rate_limited_when_deployed(deployed):
    codes = [deployed.get("/api/catalog", params={"store_url": "http://127.0.0.1:9/"}).status_code for _ in range(32)]
    assert codes[0] == 400 and codes[-1] == 429


# --- Politeness on real stores: Retry-After, not enough pages, time budget ---

def throttled_store(tmp_path, refuse, retry_after="1", pages=12):
    """A store whose product pages answer 429 until `refuse(path, hits)` is False. Returns (server, hits)."""
    ld = ('<script type="application/ld+json">{"@type":"Product","name":"P","offers":'
          '{"price":"1","priceCurrency":"USD","availability":"InStock"}}</script>')
    hits: dict[str, int] = {}
    app = FastAPI()
    from fastapi.responses import HTMLResponse, Response

    @app.get("/")
    def home():
        return HTMLResponse("".join(f'<a href="/products/p{i}">p{i}</a>' for i in range(pages)))

    @app.get("/products/{slug}")
    def product(slug: str):
        hits[slug] = hits.get(slug, 0) + 1
        if refuse(slug, hits[slug]):
            return Response(status_code=429, headers={"Retry-After": retry_after} if retry_after else {})
        return HTMLResponse(f"<html><title>{slug}</title>{ld}</html>")

    return LiveServer(app), hits


def test_retry_after_is_read_as_seconds_or_http_date():
    from email.utils import format_datetime
    from datetime import datetime, timedelta, timezone

    assert cr.retry_after_s("3") == 3.0 and cr.retry_after_s("") is None and cr.retry_after_s("soon") is None
    soon = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=30), usegmt=True)
    assert 25 <= cr.retry_after_s(soon) <= 30


def test_a_figure_needs_five_pages_or_half_of_those_found():
    assert cr.enough_checked(5, 12) and not cr.enough_checked(4, 12)
    assert cr.enough_checked(1, 1) and cr.enough_checked(1, 2) and not cr.enough_checked(1, 3)
    assert not cr.enough_checked(0, 1)


async def test_a_429_with_retry_after_is_waited_out_then_the_page_is_checked(tmp_path):
    import time

    cr._cache.clear()
    srv, hits = throttled_store(tmp_path, lambda slug, n: slug == "p0" and n == 1, pages=6)
    with srv:
        started = time.monotonic()
        r = await check_catalog(f"{srv.url}/", LOCAL, min_interval_s=0.01)
    assert hits["p0"] == 2 and time.monotonic() - started >= 1.0  # Retry-After: 1 was honoured
    assert (r["products_checked"], r["machine_readable"], r["percent"]) == (6, 6, 100) and r["errors"] == []


async def test_repeated_429s_give_no_percent_and_say_the_store_refused(tmp_path):
    cr._cache.clear()
    srv, hits = throttled_store(tmp_path, lambda slug, n: slug != "p0", retry_after="0")
    with srv:
        r = await check_catalog(f"{srv.url}/", LOCAL, min_interval_s=0.01)
    assert hits["p1"] == 3  # the first try and two retries
    assert (r["products_found"], r["products_checked"]) == (12, 1)
    assert r["percent"] is None and r["meets_benchmark"] is None
    assert r["summary"] == "Checked 1 of 12 product pages; the store refused the rest (rate limited). Not enough to judge the catalog."
    assert len(r["errors"]) == 11 and all("the store rate-limited us" in e for e in r["errors"])
    assert cr._cache == {}  # a refused crawl is never cached


async def test_the_retry_wait_is_capped(tmp_path, monkeypatch):
    import time

    cr._cache.clear()
    monkeypatch.setattr(cr, "MAX_RETRY_WAIT_S", 0.2)
    srv, _ = throttled_store(tmp_path, lambda slug, n: slug == "p0" and n == 1, retry_after="3600", pages=2)
    with srv:
        started = time.monotonic()
        r = await check_catalog(f"{srv.url}/", LOCAL, min_interval_s=0.01)
    assert time.monotonic() - started < 5 and r["products_checked"] == 2


async def test_the_time_budget_stops_the_crawl_and_reports_what_was_checked(tmp_path):
    cr._cache.clear()
    srv, hits = throttled_store(tmp_path, lambda slug, n: False)
    with srv:
        r = await check_catalog(f"{srv.url}/", LOCAL, min_interval_s=0.4, budget_s=2.6)
    # How many pages fit in the budget depends on the machine; that the budget stops the crawl and says so does not.
    checked = r["products_checked"]
    assert 1 <= checked < r["products_found"] == 12 and len(hits) < 12
    assert any("time budget ran out" in e for e in r["errors"])
    if checked < 5:  # the minimum-sample rule: min(5, half of 12)
        assert r["percent"] is None and "ran out of time" in r["summary"]
    else:
        assert r["percent"] is not None and f"Checked {checked} of 12" in r["summary"]
