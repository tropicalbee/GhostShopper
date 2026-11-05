import json

import httpx
import pytest

from backend.app.market import Channel3Search, RecordedSearch, analyze, make_search, market_check
from store import catalog

pytestmark = pytest.mark.anyio


async def recorded_report(sku: str) -> dict:
    return await market_check(catalog.get_by_sku(sku), RecordedSearch())


async def test_mug_is_findable_and_competitive_in_the_recorded_market():
    r = await recorded_report("FH-MUG-01")
    assert r["source"] == "recorded" and "not live market data" in r["source_note"]
    assert r["similar_found"] == 6  # the EUR offer is not comparable and is skipped
    assert (r["market_min"], r["market_median"], r["market_max"]) == ("18.00", "27.00", "36.00")
    assert r["price_vs_median_pct"] == -11.1  # (24 - 27) / 27
    assert r["findable"] is True and r["competitive"] is True
    assert "11.1% below the market median $27.00" in r["verdict"]


async def test_dripper_is_priced_above_the_market():
    r = await recorded_report("FH-DRP-02")
    assert r["market_median"] == "32.00"
    assert r["price_vs_median_pct"] == 18.8  # (38 - 32) / 32 = 18.75 -> 18.8
    assert r["competitive"] is False


async def test_too_few_comparables_is_not_findable():
    r = await recorded_report("FH-ESP-04")
    assert r["similar_found"] == 2 and r["findable"] is False
    assert "weak signal" in r["verdict"]


async def test_every_store_product_has_a_recording():
    for p in catalog.load_products():
        assert (await recorded_report(p.sku))["similar_found"] > 0


def test_no_comparables_is_reported_not_invented():
    r = analyze(catalog.get_by_sku("FH-MUG-01"), {"products": []}, "channel3", "q")
    assert (r.similar_found, r.findable, r.competitive, r.market_median) == (0, False, None, None)


async def test_live_client_calls_channel3_search_with_the_api_key():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"], seen["key"], seen["body"] = request.url.path, request.headers["x-api-key"], json.loads(request.content)
        return httpx.Response(200, json={"products": [
            {"id": "1", "title": "Mug", "offers": [{"domain": "a.example", "url": "u", "price": {"price": 20, "currency": "USD"}}]}],
            "next_page_token": None})

    http = httpx.AsyncClient(base_url="https://api.trychannel3.com", headers={"x-api-key": "k-123"},
                             transport=httpx.MockTransport(handler))
    r = await market_check(catalog.get_by_sku("FH-MUG-01"), Channel3Search("k-123", http=http))
    assert seen == {"path": "/v1/search", "key": "k-123",
                    "body": {"query": "Speckled Stoneware Mug", "limit": 20, "config": {"country": "US", "currency": "USD"}}}
    assert r["source"] == "channel3" and r["similar_found"] == 1


def test_switch_to_live_only_when_the_key_exists(monkeypatch):
    monkeypatch.delenv("CHANNEL3_API_KEY", raising=False)
    assert make_search().source == "recorded"
    monkeypatch.setenv("CHANNEL3_API_KEY", "k")
    assert make_search().source == "channel3"


def test_market_endpoint(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from backend.app.config import Settings
    from backend.app.main import create_app

    monkeypatch.delenv("CHANNEL3_API_KEY", raising=False)
    app = create_app(Settings("", "", tmp_path / "m.db", "http://x"))
    with TestClient(app) as c:
        assert c.get("/api/market/FH-BWL-03").json()["competitive"] is True
        assert c.get("/api/market/NOPE").status_code == 404
