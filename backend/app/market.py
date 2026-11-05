"""Market check: are similar products findable, and is the merchant's price competitive?

Channel3 (https://channel3.ai/docs, POST /v1/search) behind a small interface. With CHANNEL3_API_KEY set the
live API is used; without it, recorded fixtures in Channel3's response shape are used and every report says
so (source = "recorded"). The market check is informational: it never changes the readiness score.
"""

import json
import os
from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from statistics import median
from typing import Any, Protocol

import httpx

from . import config  # noqa: F401  (loads .env)
from store.catalog import Product

CHANNEL3_BASE_URL = "https://api.trychannel3.com"
RECORDINGS_DIR = Path(__file__).with_name("market_recordings")
FINDABLE_MIN = 3  # similar products with a comparable price needed to call the market "findable"
COMPETITIVE_MARGIN = Decimal("0.10")  # up to 10% above the market median still counts as competitive


class MarketError(RuntimeError):
    pass


class ProductSearch(Protocol):
    source: str  # "channel3" (live) | "recorded"

    async def search(self, query: str, sku: str, limit: int = 20) -> dict[str, Any]: ...


class Channel3Search:
    source = "channel3"

    def __init__(self, api_key: str, http: httpx.AsyncClient | None = None):
        self._http = http or httpx.AsyncClient(base_url=CHANNEL3_BASE_URL, timeout=30.0,
                                               headers={"x-api-key": api_key})

    async def search(self, query: str, sku: str, limit: int = 20) -> dict[str, Any]:
        body = {"query": query, "limit": min(limit, 30), "config": {"country": "US", "currency": "USD"}}
        resp = await self._http.post("/v1/search", json=body)
        if resp.status_code != 200:
            raise MarketError(f"Channel3 search failed: {resp.status_code} {resp.text[:200]}")
        return resp.json()

    async def aclose(self) -> None:
        await self._http.aclose()


class RecordedSearch:
    """Hand-made fixtures in Channel3's /v1/search response shape, one per store product. Not real market data."""

    source = "recorded"

    def __init__(self, directory: Path = RECORDINGS_DIR):
        self._dir = directory

    async def search(self, query: str, sku: str, limit: int = 20) -> dict[str, Any]:
        path = self._dir / f"{sku}.json"
        if not path.is_file():
            raise MarketError(f"No recorded market response for {sku}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return {**data, "products": data["products"][:limit]}


def make_search() -> ProductSearch:
    key = os.getenv("CHANNEL3_API_KEY", "").strip()
    return Channel3Search(key) if key else RecordedSearch()


@dataclass(frozen=True)
class Comparable:
    title: str
    price: str
    currency: str
    domain: str | None
    url: str | None


@dataclass(frozen=True)
class MarketReport:
    sku: str
    product: str
    source: str
    source_note: str
    query: str
    our_price: str
    currency: str
    similar_found: int
    findable: bool
    market_min: str | None
    market_median: str | None
    market_max: str | None
    price_vs_median_pct: float | None
    competitive: bool | None
    verdict: str
    comparables: list[Comparable]


def _money(d: Decimal) -> str:
    return str(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def comparables_from(response: dict[str, Any], currency: str) -> list[Comparable]:
    """First in-currency offer of each product. Products without a comparable price are skipped."""
    out = []
    for p in response.get("products") or []:
        for offer in p.get("offers") or []:
            price = (offer.get("price") or {})
            if price.get("currency") == currency and price.get("price") is not None:
                out.append(Comparable(p.get("title", ""), _money(Decimal(str(price["price"]))), currency,
                                      offer.get("domain"), offer.get("url")))
                break
    return out


def analyze(product: Product, response: dict[str, Any], source: str, query: str) -> MarketReport:
    comps = comparables_from(response, product.currency)
    prices = sorted(Decimal(c.price) for c in comps)
    note = ("Live Channel3 search results." if source == "channel3" else
            "Recorded fixture in Channel3's response shape, not live market data. Set CHANNEL3_API_KEY for live results.")
    if not prices:
        return MarketReport(product.sku, product.name, source, note, query, product.price_str, product.currency,
                            0, False, None, None, None, None, None,
                            "No similar products with a comparable price were found.", comps)
    med = Decimal(str(median(prices)))
    pct = float(((product.price - med) / med * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
    competitive = product.price <= med * (1 + COMPETITIVE_MARGIN)
    findable = len(prices) >= FINDABLE_MIN
    where = "below" if pct < 0 else "above" if pct > 0 else "at"
    verdict = (f"{len(prices)} similar products found; your price ${product.price_str} is "
               f"{abs(pct):.1f}% {where} the market median ${_money(med)} "
               f"({'competitive' if competitive else 'not competitive'}).")
    if not findable:
        verdict += f" Fewer than {FINDABLE_MIN} comparables, so treat this as a weak signal."
    return MarketReport(product.sku, product.name, source, note, query, product.price_str, product.currency,
                        len(prices), findable, _money(prices[0]), _money(med), _money(prices[-1]), pct,
                        competitive, verdict, comps)


async def market_check(product: Product, search: ProductSearch | None = None) -> dict[str, Any]:
    search = search or make_search()
    query = product.name
    try:
        response = await search.search(query, product.sku)
    finally:
        close = getattr(search, "aclose", None)
        if close:
            await close()
    return asdict(analyze(product, response, search.source, query))


def main() -> int:
    import argparse
    import asyncio

    from store import catalog

    p = argparse.ArgumentParser(prog="python -m backend.app.market", description="Market check for a store product")
    p.add_argument("sku", nargs="?", default="FH-MUG-01")
    sku = p.parse_args().sku
    product = catalog.get_by_sku(sku)
    if product is None:
        print(f"Unknown SKU {sku}")
        return 2
    report = asyncio.run(market_check(product))
    print(f"{report['product']} ({report['sku']}), source: {report['source']}")
    print(f"  {report['source_note']}")
    print(f"  {report['verdict']}")
    for c in report["comparables"]:
        print(f"    ${c['price']:>7}  {c['title']}  [{c['domain']}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
