import json

import httpx
import pytest

from backend.app.market import MULTI_PACK_RE, Channel3Search, RecordedSearch, analyze, make_search, market_check
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


def offers(*items: tuple[str, str, float]) -> dict:
    return {"products": [{"id": str(i), "title": t, "offers": [
        {"domain": d, "url": "u", "price": {"price": price, "currency": "USD"}}]} for i, (t, d, price) in enumerate(items)]}


def titles(report) -> list[str]:
    return [c.title for c in report.comparables]


def test_duplicate_title_on_the_same_domain_counts_once():
    r = analyze(catalog.get_by_sku("FH-MUG-01"), offers(
        ("Vince Stoneware Mug", "stonelain.com", 38.99), ("  vince  STONEWARE mug", "stonelain.com", 38.99),
        ("Vince Stoneware Mug", "other.example", 40)), "channel3", "q")
    assert titles(r) == ["Vince Stoneware Mug", "Vince Stoneware Mug"]
    assert [c.domain for c in r.comparables] == ["stonelain.com", "other.example"]
    assert r.similar_found == 2 and r.removed == 1
    assert "(1 removed: duplicates or multi-packs)" in r.verdict


@pytest.mark.parametrize("title", [
    "Tessa, Gray Speckle, Mug, Stoneware, Pack/4", "Mug 4-Pack", "Mug pack of 4", "Mugs, Set of 4", "Mug 4 pack",
    "Mug 4pc", "Mug 6-piece", "Mug (Set of 2)", "Mug Pair", "Mug x4", "12-pack mugs"])
def test_multi_pack_titles_are_recognised(title):
    assert MULTI_PACK_RE.search(title)


def test_multi_packs_are_left_out_of_the_comparison_and_the_median():
    r = analyze(catalog.get_by_sku("FH-MUG-01"), offers(
        ("Tessa Mug, Stoneware, Pack/4", "a.example", 88), ("Plain Mug", "b.example", 20), ("Blue Mug", "c.example", 30),
        ("Green Mug", "d.example", 40)), "channel3", "q")
    assert titles(r) == ["Plain Mug", "Blue Mug", "Green Mug"]
    assert r.removed == 1 and r.market_median == "30.00" and r.market_max == "40.00"  # 88 would have made it 35.00


def test_single_item_with_a_number_in_the_title_is_kept():
    r = analyze(catalog.get_by_sku("FH-MUG-01"), offers(
        ("Stoneware Mug 12 oz", "a.example", 20), ("Mug, 1 Pack", "b.example", 22), ("Mug 350ml", "c.example", 24)),
        "channel3", "q")
    assert len(r.comparables) == 3 and r.removed == 0 and "removed" not in r.verdict


def test_a_product_that_is_itself_a_set_is_compared_with_other_sets():
    sets = offers(("Plates Set of 4", "a.example", 80), ("plates  set of 4", "a.example", 80), ("Plates 4 Pack", "b.example", 90))
    r = analyze(catalog.get_by_sku("FH-PLT-10"), sets, "channel3", "q")
    assert titles(r) == ["Plates Set of 4", "Plates 4 Pack"] and r.removed == 1


async def test_recorded_fixtures_are_filtered_like_live_results(tmp_path):
    (tmp_path / "FH-MUG-01.json").write_text(json.dumps(offers(
        ("Mug", "a.example", 20), ("Mug", "a.example", 20), ("Mug Pack/4", "b.example", 80), ("Cup", "c.example", 30))))
    r = await market_check(catalog.get_by_sku("FH-MUG-01"), RecordedSearch(tmp_path))
    assert r["source"] == "recorded" and r["similar_found"] == 2 and r["removed"] == 2
    assert [c["title"] for c in r["comparables"]] == ["Mug", "Cup"] and r["market_median"] == "25.00"


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
