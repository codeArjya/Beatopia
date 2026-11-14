"""Per-request stage timings: one JSON log line per request plus a `Server-Timing` header.

Usage inside a handler (works across `asyncio.to_thread`, which copies the context):

    with stage("embed"):
        q = embed(...)
    note(plan_cached=True, n=len(results))
"""

from __future__ import annotations

import json
import logging
import sys
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from fastapi import FastAPI, Request, Response

log = logging.getLogger("app.request")


class Timer:
    def __init__(self) -> None:
        self.t0 = time.perf_counter()
        self.stages: dict[str, float] = {}
        self.fields: dict[str, Any] = {}

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        t = time.perf_counter()
        try:
            yield
        finally:
            self.stages[name] = self.stages.get(name, 0.0) + (time.perf_counter() - t) * 1000

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self.t0) * 1000


_current: ContextVar[Timer | None] = ContextVar("request_timer", default=None)


def current() -> Timer:
    """The request's timer, or a throwaway one outside a request (scripts, tests)."""
    return _current.get() or Timer()


def stage(name: str) -> Any:
    return current().stage(name)


def note(**fields: Any) -> None:
    current().fields.update(fields)


def server_timing(timer: Timer, total_ms: float) -> str:
    parts = [f"{name};dur={ms:.1f}" for name, ms in timer.stages.items()]
    return ", ".join([*parts, f"total;dur={total_ms:.1f}"])


def configure_logging() -> None:
    """`app.*` loggers print INFO to stderr (uvicorn only configures its own loggers)."""
    root = logging.getLogger("app")
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        root.propagate = False


def install_timing(app: FastAPI) -> None:
    @app.middleware("http")
    async def _timing(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        timer = Timer()
        token = _current.set(timer)
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["Server-Timing"] = server_timing(timer, timer.elapsed_ms())
            return response
        finally:
            _current.reset(token)
            line = {
                "method": request.method,
                "path": request.url.path,
                "status": status,
                "ms": round(timer.elapsed_ms(), 1),
                **{f"{k}_ms": round(v, 1) for k, v in timer.stages.items()},
                **timer.fields,
            }
            log.info(json.dumps(line, default=str))
