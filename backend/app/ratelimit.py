"""A sliding-window rate limiter kept in memory.

shortcut: one process only (the Dockerfile runs a single uvicorn worker, and runs are serialized by an
in-process lock anyway). Counters reset on restart. Move to a shared store before running more than one instance.
"""

import time
from collections import deque

from fastapi import HTTPException, Request


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


def rate_limit(request: Request, limiter_name: str) -> None:
    """Counts every attempt, failed ones included: a failed start still costs a preflight fetch.
    Off in local development (dev_options), where tests and the benchmark start many runs."""
    if request.app.state.settings.dev_options:
        return
    limiter = getattr(request.app.state, limiter_name)
    ip = request.client.host if request.client else "unknown"
    if not (limiter.hit(f"ip:{ip}") & limiter.hit(f"owner:{request.state.owner}")):
        raise HTTPException(status_code=429, detail={"error": "RATE_LIMITED", "message": "That's a lot of requests in a short time. Please wait a few minutes and try again."})
