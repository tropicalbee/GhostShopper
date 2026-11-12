"""A sliding-window rate limiter kept in memory.

shortcut: one process only (the Dockerfile runs a single uvicorn worker, and runs are serialized by an
in-process lock anyway). Counters reset on restart. Move to a shared store before running more than one instance.
"""

import logging
import time
from collections import deque

from fastapi import HTTPException, Request

from store.app import has_admin_cookie

log = logging.getLogger(__name__)
_warned_short_forwarded = False


class RateLimiter:
    def __init__(self, limit: int, window_s: float, clock=time.monotonic):
        self.limit, self.window_s, self._clock = limit, window_s, clock
        self._hits: dict[str, deque[float]] = {}

    def hit(self, key: str) -> bool:
        """Record an attempt. False once `key` has used up `limit` attempts in the last `window_s` seconds."""
        now = self._clock()
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - self.window_s:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        if len(self._hits) > 10_000:  # bound memory: drop keys with no recent hits
            for k in [k for k, v in self._hits.items() if not v or v[-1] <= now - self.window_s]:
                del self._hits[k]
        return True


def client_ip(request: Request, hops: int) -> str:
    """The caller's address. Behind `hops` trusted proxies, each one appends the address it saw to X-Forwarded-For,
    so the entry `hops` from the right is the one our own proxy wrote. Entries further left are client-controlled
    and never used. No header (or fewer entries than hops): the socket peer."""
    forwarded = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    if hops > 0 and len(forwarded) >= hops:
        return forwarded[-hops]
    global _warned_short_forwarded
    if hops > 0 and forwarded and not _warned_short_forwarded:
        # Fewer entries than trusted proxies: TRUSTED_PROXY_HOPS is probably set too high for this host.
        _warned_short_forwarded = True
        log.warning("X-Forwarded-For has %d entries but TRUSTED_PROXY_HOPS is %d; check the setting.", len(forwarded), hops)
    return request.client.host if request.client else "unknown"


def _limits_apply(request: Request) -> bool:
    settings = request.app.state.settings
    return not (settings.dev_options or has_admin_cookie(request, settings.demo_admin_token))


def rate_limit(request: Request, limiter_name: str, daily_cap: str | None = None, charge_cap: bool = True) -> None:
    """Counts every attempt, failed ones included: a failed start still costs a preflight fetch.
    `daily_cap` names a process-wide per-day cap (runs, market, orders) for calls that cost real quota.
    `charge_cap=False` checks only the per-caller window; the route then calls charge_daily_cap once the request
    has passed local validation, so malformed requests can't burn the shared daily budget.
    Off in local development (dev_options), where tests and the benchmark start many runs. The presenter's
    admin cookie skips both limits, so a flood from anonymous callers can't lock them out."""
    state = request.app.state
    settings = state.settings
    if not _limits_apply(request):
        return
    limiter = getattr(state, limiter_name)
    ip = client_ip(request, settings.trusted_proxy_hops)
    if not (limiter.hit(f"ip:{ip}") & limiter.hit(f"owner:{request.state.owner}")):
        raise HTTPException(status_code=429, detail={"error": "RATE_LIMITED", "message": "That's a lot of requests in a short time. Please wait a few minutes and try again."})
    if daily_cap and charge_cap:
        charge_daily_cap(request, daily_cap)


def charge_daily_cap(request: Request, daily_cap: str) -> None:
    """Spend one call of the process-wide daily cap. Same exemptions as rate_limit."""
    if _limits_apply(request) and not request.app.state.daily_caps[daily_cap].hit("all"):
        raise HTTPException(status_code=429, detail={"error": "RATE_LIMITED", "message": "GhostShopper has reached its daily limit for this action on the shared demo. Please try again tomorrow."})
