"""Being a polite visitor on real stores: which URLs we may open, robots.txt, a rate limit, and
friendly messages when a site can't be read.

Live stores (anything but our own demo store) are browse-only: the agent never pays or logs in there.
"""

import asyncio
import ipaddress
import os
import socket
import time
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import httpx

from .. import config  # noqa: F401  (loads .env)

USER_AGENT = ("Mozilla/5.0 (compatible; GhostShopperBot/0.1; AI shopping-agent readiness check) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36")
ROBOTS_AGENT = "GhostShopperBot"
MIN_INTERVAL_S = 2.0   # between page loads on a live store
MAX_CRAWL_DELAY_S = 10.0


class SiteError(ValueError):
    """A store we can't check. The message is written for a shopkeeper."""


@dataclass(frozen=True)
class Target:
    url: str
    origin: str
    demo: bool  # our own demo store: the only place sandbox purchases run


def normalize(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        raise SiteError("Paste the address of your store, for example https://yourshop.com")
    if "://" not in raw:
        raw = "https://" + raw
    u = urlparse(raw)
    if u.scheme not in ("http", "https") or not u.hostname or " " in raw:
        raise SiteError("That doesn't look like a web address. Try something like https://yourshop.com")
    return urlunparse((u.scheme, u.netloc.lower(), u.path or "/", "", u.query, ""))


def origin_of(url: str) -> str:
    u = urlparse(url)
    return f"{u.scheme}://{u.netloc}"


def is_demo_store(url: str, app_base_url: str) -> bool:
    return origin_of(url) == origin_of(app_base_url) and urlparse(url).path.startswith("/store")


def allow_private_hosts(app_base_url: str) -> bool:
    """Private and local addresses are allowed in development (the app itself runs on localhost),
    and refused when deployed, so a hosted GhostShopper can't be pointed at internal machines."""
    env = os.getenv("ALLOW_PRIVATE_URLS", "").strip().lower()
    if env in ("1", "true", "yes"):
        return True
    if env in ("0", "false", "no"):
        return False
    return (urlparse(app_base_url).hostname or "") in ("localhost", "127.0.0.1", "::1")


def _is_public(ip: str) -> bool:
    a = ipaddress.ip_address(ip)
    return not (a.is_private or a.is_loopback or a.is_link_local or a.is_multicast or a.is_reserved
                or a.is_unspecified)


async def check_host(url: str, allow_private: bool) -> None:
    host = urlparse(url).hostname or ""
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SiteError("We couldn't find that website. Check the address for typos.") from exc
    if not allow_private and not all(_is_public(i[4][0]) for i in infos):
        raise SiteError("For safety we can only check public websites.")


class Politeness:
    """robots.txt (RFC 9309 rules) and a minimum gap between page loads, per origin."""

    def __init__(self, http: httpx.AsyncClient | None = None, min_interval_s: float = MIN_INTERVAL_S,
                 allow_private: bool = False, transport: httpx.AsyncBaseTransport | None = None):
        self._http = http
        self.allow_private = allow_private
        self._transport = transport  # tests: a mock transport behind the same host checks
        self._robots: dict[str, RobotFileParser | bool] = {}
        self._last: dict[str, float] = {}
        self.min_interval_s = min_interval_s
        self._lock = asyncio.Lock()

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers={"User-Agent": USER_AGENT},
                                           event_hooks={"request": [self._check_request]}, transport=self._transport)
        return self._http

    async def _check_request(self, request: httpx.Request) -> None:
        """Runs before every request, redirect hops included, so no hop can reach a private address."""
        await check_host(str(request.url), self.allow_private)

    async def robots(self, origin: str) -> RobotFileParser | bool:
        """A parser, True (allow all) or False (disallow all)."""
        if origin in self._robots:
            return self._robots[origin]
        try:
            resp = await (await self._client()).get(f"{origin}/robots.txt")
            if resp.status_code >= 500:
                result: RobotFileParser | bool = False  # unreachable rules: assume everything is disallowed
            elif resp.status_code >= 400:
                result = True  # no robots.txt: everything is allowed
            else:
                parser = RobotFileParser()
                parser.parse(resp.text.splitlines())
                result = parser
        except (httpx.HTTPError, SiteError):  # unreachable, or redirected somewhere we won't go
            result = False
        self._robots[origin] = result
        return result

    async def allowed(self, url: str) -> bool:
        rules = await self.robots(origin_of(url))
        if isinstance(rules, bool):
            return rules
        return rules.can_fetch(ROBOTS_AGENT, url)

    async def wait_turn(self, url: str) -> None:
        origin = origin_of(url)
        rules = await self.robots(origin)
        delay = self.min_interval_s
        if isinstance(rules, RobotFileParser):
            crawl = rules.crawl_delay(ROBOTS_AGENT)
            if crawl:
                delay = max(delay, min(float(crawl), MAX_CRAWL_DELAY_S))
        async with self._lock:
            now = time.monotonic()
            wait = self._last.get(origin, 0) + delay - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last[origin] = time.monotonic()

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()


async def preflight(url: str, app_base_url: str, politeness: Politeness | None = None) -> Target:
    """Check a store link before a run starts. Raises SiteError with a shopkeeper-friendly message."""
    url = normalize(url)
    demo = is_demo_store(url, app_base_url)
    if demo:
        return Target(url, origin_of(url), True)
    allow_private = allow_private_hosts(app_base_url)
    await check_host(url, allow_private)
    polite = politeness or Politeness(allow_private=allow_private)
    try:
        if not await polite.allowed(url):
            raise SiteError("Your store's robots.txt asks automated visitors not to open this page, so we didn't. "
                            "You can allow GhostShopperBot in robots.txt, or check a different page.")
        try:
            resp = await (await polite._client()).get(url)
        except httpx.TimeoutException as exc:
            raise SiteError("Your store took too long to answer. Try again in a minute.") from exc
        except httpx.HTTPError as exc:
            raise SiteError("We couldn't open your store. Check the address and that the site is online.") from exc
        # 403/429/503 often mean a bot check; the run itself detects and reports that as not the store's fault.
        if resp.status_code >= 400 and resp.status_code not in (403, 429, 503):
            raise SiteError(f"Your store answered with an error ({resp.status_code}). Check the link opens in your browser.")
        ctype = resp.headers.get("content-type", "")
        if resp.status_code < 400 and "html" not in ctype:
            raise SiteError("That link doesn't open a web page. Paste the address of your shop's home or product page.")
        await check_host(str(resp.url), allow_private_hosts(app_base_url))  # redirects can't sneak inward
        final = normalize(str(resp.url))
        return Target(final, origin_of(final), False)
    finally:
        if politeness is None:
            await polite.aclose()
