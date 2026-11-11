"""A sliding-window rate limiter kept in memory.

shortcut: one process only (the Dockerfile runs a single uvicorn worker, and runs are serialized by an
in-process lock anyway). Counters reset on restart. Move to a shared store before running more than one instance.
"""

import time
from collections import deque

from fastapi import HTTPException, Request

from store.app import has_admin_cookie


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
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request, limiter_name: str, daily_cap: str | None = None) -> None:
    """Counts every attempt, failed ones included: a failed start still costs a preflight fetch.
    `daily_cap` names a process-wide per-day cap (runs, market, orders) for calls that cost real quota.
    Off in local development (dev_options), where tests and the benchmark start many runs. The presenter's
    admin cookie skips both limits, so a flood from anonymous callers can't lock them out."""
    state = request.app.state
    settings = state.settings
    if settings.dev_options or has_admin_cookie(request, settings.demo_admin_token):
        return
    limiter = getattr(state, limiter_name)
    ip = client_ip(request, settings.trusted_proxy_hops)
    if not (limiter.hit(f"ip:{ip}") & limiter.hit(f"owner:{request.state.owner}")):
        raise HTTPException(status_code=429, detail={"error": "RATE_LIMITED", "message": "That's a lot of requests in a short time. Please wait a few minutes and try again."})
    if daily_cap and not state.daily_caps[daily_cap].hit("all"):
        raise HTTPException(status_code=429, detail={"error": "RATE_LIMITED", "message": "GhostShopper has reached its daily limit for this action on the shared demo. Please try again tomorrow."})
