"""Product feed: built from what the shopper read, with gaps reported honestly. Never a submission to PayPal."""

import csv
import io

import pytest
from fastapi.testclient import TestClient

from backend.app.agent.recorder import RunRecorder
from backend.app.feed import COLUMNS, REQUIRED, build_feed, feed_csv
from backend.app.main import create_app
from backend.app.owner import hash_token, new_token
from backend.app.scoring import CHECKS, compute_score

from .test_access import client_for, settings
from .test_agent_e2e import requires_browser, run_cassette, server  # noqa: F401  (server is a fixture)

pytestmark = pytest.mark.anyio

FULL = {
    "url": "https://shop.example/products/mug",
    "title": "Mug | Shop",
    "product": {
        "@type": "Product", "name": "Mug", "sku": "M-1", "description": "A mug.", "image": "/img/mug.jpg",
        "brand": {"@type": "Brand", "name": "Fernhill"}, "gtin13": "0123456789012", "mpn": "FH-1",
        "offers": {"price": "24", "priceCurrency": "USD", "availability": "https://schema.org/InStock",
                   "itemCondition": "https://schema.org/NewCondition", "url": "https://shop.example/products/mug"},
    },
    "meta_description": None, "canonical": None, "prices": [], "images": [], "stock_text": None, "sku_text": None,
}


def fields(feed):
    return {f["field"]: f for f in feed["fields"]}


def test_a_complete_product_page_fills_every_column():
    feed = build_feed(FULL)
    assert feed["ready"] and feed["required_found"] == feed["required_total"] == len(REQUIRED)
    assert feed["row"] == {
        "id": "M-1", "title": "Mug", "description": "A mug.", "link": "https://shop.example/products/mug",
        "image_link": "https://shop.example/img/mug.jpg", "price": "24.00 USD", "availability": "in_stock",
        "brand": "Fernhill", "gtin": "0123456789012", "mpn": "FH-1", "condition": "new"}
    assert all(f["status"] == "found" and f["fix"] is None for f in feed["fields"])


def test_text_only_pages_fill_what_they_can_and_say_where_it_came_from():
    snap = {"url": "https://shop.example/p/mug", "title": "Mug | Shop", "product": None, "meta_description": "Hand thrown.",
            "canonical": "/p/mug", "prices": [{"text": "$24.00", "value": "24.00"}], "images": [{"src": "a.jpg", "alt": ""}],
            "stock_text": "In stock", "sku_text": "M-1"}
    f = fields(build_feed(snap))
    assert (f["title"]["value"], f["title"]["source"]) == ("Mug", "page title")
    assert (f["price"]["value"], f["price"]["source"]) == ("24.00 USD", "page text")
    assert (f["availability"]["value"], f["id"]["value"]) == ("in_stock", "M-1")
    assert f["link"]["value"] == "https://shop.example/p/mug" and f["image_link"]["value"] == "https://shop.example/p/a.jpg"
    assert f["brand"]["status"] == "missing" and f["brand"]["fix"]


def test_a_price_without_a_currency_is_only_partial():
    snap = {**FULL, "product": {**FULL["product"], "offers": {"price": "24.00"}}}
    f = fields(build_feed(snap))
    assert f["price"]["status"] == "partial" and f["price"]["value"] == "24.00" and "currency" in f["price"]["note"]
    assert not build_feed(snap)["ready"]


def test_nothing_read_means_no_feed():
    assert build_feed(None) is None


def test_csv_has_the_feed_columns_and_neutralises_spreadsheet_formulas():
    feed = build_feed({**FULL, "product": {**FULL["product"], "name": "=HYPERLINK(\"http://evil\")"}})
    rows = list(csv.reader(io.StringIO(feed_csv(feed))))
    assert tuple(rows[0]) == COLUMNS and len(rows) == 2
    assert rows[1][1].startswith("'=")


@requires_browser
async def test_fixed_store_run_has_every_required_field(server):
    run = await run_cassette(server, "day2_flaws_off", "off")
    feed = run["product_feed"]
    assert feed["ready"], [f for f in feed["fields"] if f["required"] and f["status"] != "found"]
    assert feed["row"]["id"] == "FH-MUG-01" and feed["row"]["price"] == "24.00 USD"
    assert feed["row"]["availability"] == "in_stock" and feed["row"]["brand"]
    assert "Speckled Stoneware Mug" in feed["row"]["title"] and feed["row"]["image_link"].startswith("http")
    # The store publishes no barcode, part number or condition: reported as gaps, not invented.
    f = fields(feed)
    assert all(f[k]["status"] == "missing" and f[k]["fix"] for k in ("gtin", "mpn", "condition"))
    assert not any(f[k]["required"] for k in ("gtin", "mpn", "condition"))


@requires_browser
async def test_flawed_store_run_shows_the_gaps(server):
    run = await run_cassette(server, "day2_flaws_on", "on")
    feed = run["product_feed"]
    f = fields(feed)
    assert not feed["ready"]
    for gap in ("id", "description", "price", "availability", "brand"):
        assert f[gap]["status"] == "missing" and f[gap]["fix"], gap
    assert feed["required_found"] < feed["required_total"]
    assert f["title"]["status"] == "found"  # the page title is still readable
    rows = list(csv.reader(io.StringIO(feed_csv(feed))))
    assert rows[1][COLUMNS.index("price")] == "" and rows[1][COLUMNS.index("id")] == ""


def make_run(app, owner: str | None, snapshot=FULL) -> int:
    rec = RunRecorder.start(app.state.settings.database_path, store_url="https://shop.example/", goal="g",
                            target_product=None, checkout=False, paypal_mode="off", flaws=None, llm="scripted",
                            model="m", live=True, owner_hash=hash_token(owner) if owner else None)
    for key in CHECKS:
        rec.record_check(key, True, "seen")
    if snapshot:
        rec.set_product_snapshot(snapshot)
    rec.save_score(compute_score(rec.results()))
    rec.finish(status="completed", outcome="reached_checkout", step_count=1)
    return rec.run_id


def test_feed_download_follows_the_same_access_rules_as_runs(tmp_path):
    alice, bob = new_token(), new_token()
    app = create_app(settings(tmp_path))
    mine, example, bare = make_run(app, alice), make_run(app, None), make_run(app, alice, snapshot=None)
    with client_for(app, alice) as a, client_for(app, bob) as b, client_for(app, None) as anon:
        r = a.get(f"/api/runs/{mine}/feed.csv")
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
        assert "attachment" in r.headers["content-disposition"]
        assert r.text.splitlines()[0] == ",".join(COLUMNS)
        assert a.get(f"/api/runs/{mine}").json()["product_feed"]["ready"] is True
        # Someone else's check looks like a missing one; shared examples are readable by everyone.
        assert b.get(f"/api/runs/{mine}/feed.csv").status_code == 404
        assert anon.get(f"/api/runs/{mine}/feed.csv").status_code == 404
        assert b.get(f"/api/runs/{example}/feed.csv").status_code == 200
        # A check where no product page was read has no feed to download.
        r = a.get(f"/api/runs/{bare}/feed.csv")
        assert r.status_code == 409 and r.json()["detail"]["error"] == "NO_PRODUCT_READ"
        assert a.get(f"/api/runs/{bare}").json()["product_feed"] is None
        assert a.get("/api/runs/9999/feed.csv").status_code == 404
