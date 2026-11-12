"""Catalog readiness: how much of a store's catalog is machine-readable product data.

PayPal's Agentic Commerce Pulse Report (498 US merchants, Q1 2026) found only about 1 in 5 merchants have 80% or
more of their catalog as structured, machine-readable data, which AI agents need to find products (PayPal Store
Sync). The shopper checks one product; this opens up to 12 product pages and checks each one's Product JSON-LD by
code. Informational: it never changes the readiness score. Live stores are browse-only GETs through the same
politeness layer as a run (robots.txt, rate limit, public hosts only, DNS pinning).

    python -m backend.app.catalog_readiness [--url URL]
"""

import argparse
import asyncio
import html
import json
import re
import time
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request

from . import config  # noqa: F401  (loads .env)
from .agent.checks import _get, _products_in_jsonld
from .agent.site import (SiteError, Politeness, allow_private_hosts, check_host, fetch_capped, is_demo_store, normalize,
                         origin_of)
from .ratelimit import rate_limit

BENCHMARK_PERCENT = 80
MAX_PRODUCTS = 12
MIN_PAGES = 5  # pages that must be checked before a percent is shown
CATALOG_MIN_INTERVAL_S = 2.0  # between page loads on a live store
MAX_RETRY_WAIT_S = 10.0  # longest single wait for Retry-After
MAX_STATUS_RETRIES = 2  # per page, after a 429 or 503
MAX_CONN_RETRIES = 1  # per page, after a connection error
BUDGET_S = 60.0  # for the whole check; it stops early and reports what it checked
PAGE_MAX_BYTES = 1024 * 1024
CACHE_TTL_S = 600
CACHE_MAX = 100
# Fields recorded per product, and the ones a product needs to count as machine-readable.
FIELDS = ("product", "name", "price", "priceCurrency", "availability", "sku", "image")
REQUIRED = ("product", "name", "price", "priceCurrency", "availability")

LD_RE = re.compile(r"<script[^>]+type\s*=\s*[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.I | re.S)
LOC_RE = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.I | re.S)
HREF_RE = re.compile(r"""<a\s[^>]*?href\s*=\s*["']([^"'#]+)""", re.I)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
PRODUCT_PATH_RE = re.compile(r"/products?/[^/]+", re.I)
SITEMAP_FALLBACKS = ("/sitemap.xml", "/sitemap_products_1.xml")

_cache: dict[str, tuple[float, dict[str, Any]]] = {}


class CatalogError(ValueError):
    """The catalog can't be checked. The message is written for a shopkeeper."""


def _filled(value: Any) -> bool:
    if isinstance(value, (list, dict)):
        return bool(value)
    return value is not None and str(value).strip() != ""


def _offer(product: dict[str, Any]) -> dict[str, Any]:
    offer = product.get("offers")
    if isinstance(offer, list):
        offer = next((o for o in offer if isinstance(o, dict)), None)
    if isinstance(offer, dict) and isinstance(offer.get("offers"), (list, dict)):  # AggregateOffer
        inner = offer["offers"]
        inner = inner[0] if isinstance(inner, list) and inner else inner
        offer = {**offer, **inner} if isinstance(inner, dict) else offer
    return offer if isinstance(offer, dict) else {}


def fields_present(blocks: list[Any]) -> dict[str, bool]:
    """Which of FIELDS a page's JSON-LD blocks give. The first Product found is the one judged."""
    products = _products_in_jsonld(blocks)
    product = products[0] if products else {}
    offer = _offer(product)
    spec = _get(offer, "priceSpecification") or {}
    spec = spec if isinstance(spec, dict) else {}
    return {
        "product": bool(products),
        "name": _filled(product.get("name")),
        "price": _filled(offer.get("price")) or _filled(spec.get("price")) or _filled(offer.get("lowPrice")),
        "priceCurrency": _filled(offer.get("priceCurrency")) or _filled(spec.get("priceCurrency")),
        "availability": _filled(offer.get("availability")),
        "sku": any(_filled(product.get(k)) for k in ("sku", "gtin", "gtin8", "gtin12", "gtin13", "gtin14")),
        "image": _filled(product.get("image")),
    }


def machine_readable(present: dict[str, bool]) -> bool:
    return all(present.get(k) for k in REQUIRED)


def jsonld_blocks(page: str) -> list[Any]:
    blocks = []
    for raw in LD_RE.findall(page):
        try:
            blocks.append(json.loads(html.unescape(raw) if "&quot;" in raw else raw))
        except ValueError:
            continue  # a broken block is no data
    return blocks


def _same_site(url: str, origin: str) -> bool:
    return origin_of(url) == origin


def product_links(page: str, base: str, product_prefix: str | None = None) -> list[str]:
    """Product page links on a page, in order, same site only. `product_prefix` is the demo store's /store/products/."""
    origin, seen, out = origin_of(base), set(), []
    for href in HREF_RE.findall(page):
        url = urljoin(base, html.unescape(href.strip())).split("?")[0]
        path = urlparse(url).path
        ok = path.startswith(product_prefix) and path.rstrip("/") != product_prefix.rstrip("/") if product_prefix \
            else bool(PRODUCT_PATH_RE.search(path))
        if ok and _same_site(url, origin) and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def sitemap_locs(xml: str) -> list[str]:
    return [html.unescape(u) for u in LOC_RE.findall(xml)]


def summary_line(machine: int, checked: int, found: int | None = None) -> str:
    pct = round(100 * machine / checked)
    line = (f"{machine} of {checked} {'product is' if checked == 1 else 'products are'} machine-readable ({pct}%). "
            f"PayPal's benchmark is {BENCHMARK_PERCENT}% of the catalog.")
    return line + (f" Checked {checked} of {found} product pages." if found and checked < found else "")


def enough_checked(checked: int, found: int) -> bool:
    """A figure needs at least 5 pages, or half of those found when that is fewer."""
    return checked > 0 and checked >= min(MIN_PAGES, found / 2)


class _Refused(CatalogError):
    """A page the store would not give us right now (429 or 503)."""


class _OutOfTime(CatalogError):
    pass


def retry_after_s(value: str | None) -> float | None:
    """Retry-After as seconds: a number of seconds or an HTTP date."""
    value = (value or "").strip()
    if not value:
        return None
    if value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds()) if when.tzinfo else None


class _Fetcher:
    """Browse-only GETs, one at a time. The demo store is our own server; a live store goes through Politeness, with a
    gap between loads, Retry-After honoured on 429/503 (a few retries, short waits) and one overall time budget."""

    def __init__(self, demo: bool, allow_private: bool, min_interval_s: float | None, budget_s: float):
        self.demo = demo
        interval = CATALOG_MIN_INTERVAL_S if min_interval_s is None else min_interval_s
        self._polite = None if demo else Politeness(allow_private=allow_private, min_interval_s=interval)
        self._http = httpx.AsyncClient(timeout=10.0) if demo else None
        self._interval = interval
        self._deadline = time.monotonic() + budget_s

    def out_of_time(self) -> bool:
        return time.monotonic() >= self._deadline

    async def _once(self, url: str) -> tuple[httpx.Response, bytes]:
        if self.demo:
            return await fetch_capped(self._http, url, PAGE_MAX_BYTES)
        if not await self._polite.allowed(url):
            raise CatalogError("robots.txt asks automated visitors not to open this page")
        await self._polite.wait_turn(url)
        return await fetch_capped(await self._polite._client(), url, PAGE_MAX_BYTES)

    async def get(self, url: str) -> str:
        """The page text. Raises CatalogError with a short reason."""
        status_retries, conn_retries = MAX_STATUS_RETRIES, MAX_CONN_RETRIES
        while True:
            if self.out_of_time():
                raise _OutOfTime("not opened: the time budget ran out")
            try:
                resp, body = await self._once(url)
            except httpx.TimeoutException as exc:
                raise CatalogError("took too long to answer") from exc
            except (httpx.HTTPError, SiteError) as exc:
                if conn_retries <= 0:
                    raise CatalogError("could not be opened") from exc
                conn_retries -= 1
                await asyncio.sleep(min(self._interval, MAX_RETRY_WAIT_S))
                continue
            code = resp.status_code
            if code < 400:
                return body.decode(resp.encoding or "utf-8", errors="replace")
            if code not in (429, 503):
                raise CatalogError(f"answered with status {code}")
            err = _Refused("the store rate-limited us (HTTP 429)" if code == 429
                           else "the store was temporarily unavailable (HTTP 503)")
            if status_retries <= 0:
                raise err
            status_retries -= 1
            wait = retry_after_s(resp.headers.get("retry-after"))
            wait = min(MAX_RETRY_WAIT_S, max(self._interval, 2 * self._interval if wait is None else wait))
            if time.monotonic() + wait >= self._deadline:
                raise err
            await asyncio.sleep(wait)

    async def aclose(self) -> None:
        if self._polite:
            await self._polite.aclose()
        if self._http:
            await self._http.aclose()


async def _discover(fetch: _Fetcher, root: str) -> list[str]:
    """Product page URLs, at most MAX_PRODUCTS. Demo store: the links on its home page. Live store: the sitemap,
    then product links on the home page."""
    origin = origin_of(root)
    if fetch.demo:
        return product_links(await fetch.get(root), root, urlparse(root).path.rstrip("/") + "/products/")[:MAX_PRODUCTS]
    urls: list[str] = []
    for path in SITEMAP_FALLBACKS:
        try:
            locs = sitemap_locs(await fetch.get(origin + path))
        except CatalogError:
            continue
        children = [u for u in locs if u.lower().endswith(".xml") and _same_site(u, origin)]
        if children:  # a sitemap index: open the first product sitemap
            child = next((u for u in children if "product" in u.lower()), None)
            try:
                locs = sitemap_locs(await fetch.get(child)) if child else []
            except CatalogError:
                locs = []
        urls = [u for u in locs if _same_site(u, origin) and PRODUCT_PATH_RE.search(urlparse(u).path)]
        if urls:
            break
    if not urls:
        try:
            urls = product_links(await fetch.get(root), root)
        except CatalogError as exc:
            raise CatalogError(f"Your store's home page {exc}, so we couldn't look for products.") from exc
    return list(dict.fromkeys(urls))[:MAX_PRODUCTS]


def _not_enough(checked: int, found: int, errors: list[str]) -> str:
    why = ("the store refused the rest (rate limited)" if any("rate-limited" in e for e in errors)
           else "the check ran out of time for the rest" if any("time budget" in e for e in errors)
           else "the rest could not be opened")
    return f"Checked {checked} of {found} product pages; {why}. Not enough to judge the catalog."


async def check_catalog(store_url: str | None, app_base_url: str, *, min_interval_s: float | None = None,
                        budget_s: float = BUDGET_S) -> dict[str, Any]:
    """The catalog report for a store (the demo store when `store_url` is empty). Raises SiteError or CatalogError.
    With too few pages checked there is no percent: `percent` and `meets_benchmark` are None."""
    demo_root = f"{app_base_url.rstrip('/')}/store/"
    url = normalize(store_url) if store_url else demo_root
    demo = is_demo_store(url, app_base_url)
    allow_private = allow_private_hosts(app_base_url)
    if not demo:
        await check_host(url, allow_private)
    key = url
    hit = _cache.get(key)
    if not demo and hit and time.monotonic() - hit[0] < CACHE_TTL_S:  # the demo store's flaws change, so it is never cached
        return hit[1]
    fetch = _Fetcher(demo, allow_private, min_interval_s, budget_s)
    errors: list[str] = []
    try:
        pages = await _discover(fetch, url)
        if not pages:
            raise CatalogError("We couldn't find any product pages on this store. Link to your product pages from "
                               "the home page or list them in /sitemap.xml.")
        per_product = []
        for page_url in pages:
            try:
                page = await fetch.get(page_url)
            except CatalogError as exc:
                errors.append(f"{page_url} {exc}")
                continue
            blocks = jsonld_blocks(page)
            present = fields_present(blocks)
            title = TITLE_RE.search(page)
            name = next((p.get("name") for p in _products_in_jsonld(blocks) if _filled(p.get("name"))), None)
            per_product.append({
                "url": page_url,
                "name": str(name or (html.unescape(title.group(1)).strip() if title else "") or urlparse(page_url).path),
                "present": present,
                "missing": [f for f in FIELDS if not present[f]],
                "machine_readable": machine_readable(present),
            })
    finally:
        await fetch.aclose()
    machine = sum(p["machine_readable"] for p in per_product)
    checked, found = len(per_product), len(pages)
    enough = enough_checked(checked, found)
    report = {
        "store_url": url,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "products_found": found,
        "products_checked": checked,
        "machine_readable": machine,
        "percent": round(100 * machine / checked) if enough else None,
        "benchmark_percent": BENCHMARK_PERCENT,
        "meets_benchmark": machine * 100 >= BENCHMARK_PERCENT * checked if enough else None,
        "summary": summary_line(machine, checked, found) if enough else _not_enough(checked, found, errors),
        "per_product": per_product,
        "source": "demo store" if demo else "live store",
        "errors": errors,
    }
    if not demo and enough:
        if len(_cache) >= CACHE_MAX:
            _cache.pop(next(iter(_cache)))
        _cache[key] = (time.monotonic(), report)
    return report


router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/catalog")
async def catalog(request: Request, store_url: str | None = None):
    """Catalog readiness for the demo store, or a pasted live store. Informational: never part of the score."""
    rate_limit(request, "api_limiter", daily_cap="catalog")
    try:
        async with asyncio.timeout(BUDGET_S + 10):  # backstop: the check's own budget stops it early, this stops a hang
            return await check_catalog(store_url, request.app.state.settings.app_base_url)
    except TimeoutError as exc:
        raise HTTPException(status_code=400, detail={"error": "CATALOG_UNAVAILABLE", "message": "The catalog check took too long and was stopped. Try again, or check a store that responds faster."}) from exc
    except (SiteError, CatalogError) as exc:
        raise HTTPException(status_code=400, detail={"error": "CATALOG_UNAVAILABLE", "message": str(exc)}) from exc


def _print(report: dict[str, Any]) -> None:
    print(f"{report['store_url']} ({report['source']})")
    print(report["summary"])
    width = max((len(p["name"]) for p in report["per_product"]), default=0)
    for p in report["per_product"]:
        state = "ok     " if p["machine_readable"] else "NOT ok "
        print(f"  {p['name']:<{width}}  {state}  missing: {', '.join(p['missing']) or 'nothing'}")
    for e in report["errors"]:
        print(f"  error: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Catalog readiness: how much of a catalog is machine-readable.")
    parser.add_argument("--url", help="store address; the demo store when omitted")
    args = parser.parse_args()
    try:
        _print(asyncio.run(check_catalog(args.url, config.get_settings().app_base_url)))
    except (SiteError, CatalogError) as exc:
        raise SystemExit(f"Error: {exc}")


if __name__ == "__main__":
    main()
