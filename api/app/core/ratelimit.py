"""Rate-limit guard (PLAN T11.2): in-memory token buckets → 429 `rate_limited` (CONTRACT §6).

One bucket per (endpoint, key). `/search` is keyed by `session_id`. `/why` and `/assist` carry no session id
(CONTRACT §5), so they are keyed by client IP: the last `X-Forwarded-For` entry, which Caddy sets (the API port is
only exposed inside the compose network), else the socket peer. The limits are generous on purpose: they stop a
client loop or a script from burning the Gemini quota, not a demo room of people on one Wi-Fi NAT.

Process-local (one uvicorn worker). Idle buckets are evicted, so memory stays bounded.
"""

from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Request

from app.core.errors import ApiException


@dataclass(frozen=True)
class Limit:
    per_minute: float  # sustained refill rate
    burst: int  # bucket size: requests allowed back to back


LIMITS: dict[str, Limit] = {
    "search": Limit(per_minute=30, burst=20),  # per session: chip clicks can fire several searches quickly
    "why": Limit(per_minute=120, burst=40),  # per IP: a results page asks for up to ~8 notes at once
    "assist": Limit(per_minute=20, burst=10),  # per IP: each call is up to 3 Gemini turns
}
MAX_KEYS = 10_000


class RateLimited(ApiException):
    def __init__(self, what: str, retry_after_s: int) -> None:
        super().__init__("rate_limited", f"too many {what} requests, try again in {retry_after_s} s")
        self.retry_after_s = retry_after_s
        self.headers["Retry-After"] = str(retry_after_s)


class RateLimiter:
    def __init__(self, limits: dict[str, Limit] | None = None, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.limits = dict(LIMITS if limits is None else limits)
        self._clock = clock
        self._lock = threading.Lock()
        self._buckets: OrderedDict[tuple[str, str], tuple[float, float]] = OrderedDict()  # → (tokens, last)

    def check(self, what: str, key: str) -> None:
        """Take one token for `what`/`key`, or raise `RateLimited` (with the seconds until the next token)."""
        limit = self.limits.get(what)
        if limit is None:
            return
        rate = limit.per_minute / 60.0
        now = self._clock()
        with self._lock:
            tokens, last = self._buckets.pop((what, key), (float(limit.burst), now))
            tokens = min(float(limit.burst), tokens + (now - last) * rate)
            allowed = tokens >= 1.0
            if allowed:
                tokens -= 1.0
            self._buckets[(what, key)] = (tokens, now)  # re-inserted at the end: most recently used
            while len(self._buckets) > MAX_KEYS:
                self._buckets.popitem(last=False)
        if not allowed:
            raise RateLimited(what, max(1, math.ceil((1.0 - tokens) / rate)))


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    hops = [h.strip() for h in forwarded.split(",") if h.strip()]
    if hops:
        return hops[-1]
    return request.client.host if request.client else "unknown"


def guard(request: Request, what: str, key: str | None = None) -> None:
    """Route helper: no-op when the app has no limiter (fixture mode builds one too, tests may remove it)."""
    limiter: RateLimiter | None = getattr(request.app.state, "limiter", None)
    if limiter is not None:
        limiter.check(what, key if key is not None else client_ip(request))
