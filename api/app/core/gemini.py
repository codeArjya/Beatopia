"""Gemini client singleton (google-genai `models.generate_content`), per-call budgets and the degraded switch.

Every caller treats Gemini as optional: any failure raises `GeminiUnavailable`, and the caller falls back (raw-text
plan, score order, cached notes). The client is degraded when
- `GEMINI_DEGRADED=1` or there is no `GEMINI_API_KEY` (fixed for the process), or
- `AUTO_DEGRADE_FAILURES` calls failed within `AUTO_DEGRADE_WINDOW_S` (then for `AUTO_DEGRADE_FOR_S`). This is what
  keeps a free-tier key that hits its quota (429) from adding seconds of retries to every search.

Budgets are wall-clock and enforced here, not by the HTTP deadline: the Gemini API rejects request deadlines under
10 s (`400 Manually set deadline 4s is too short`). The HTTP deadline is max(budget, 10 s); the call runs on a small
worker pool and we stop waiting after `timeout_ms`. A late reply finishes in the background and is dropped.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Literal

from google import genai
from google.genai import errors, types

from app.core.settings import Settings

log = logging.getLogger("app.gemini")

ThinkingLevel = Literal["MINIMAL", "LOW", "MEDIUM", "HIGH"]
# Models that reject MINIMAL (PLAN §0); for them MINIMAL is sent as LOW. Measured 2026-11-14 on the full planner
# prompt: gemini-3.6-flash MINIMAL ≈ 1.0–1.3 s, LOW ≈ 3–11 s, so the latency-critical calls ask for MINIMAL.
NO_MINIMAL_THINKING = ("gemini-3.8-flash",)


def thinking_for(model: str, level: ThinkingLevel) -> ThinkingLevel:
    if level == "MINIMAL" and model.removeprefix("models/").startswith(NO_MINIMAL_THINKING):
        return "LOW"
    return level


RETRY_STATUS_CODES = [429, 500, 502, 503, 504]
AUTO_DEGRADE_FAILURES = 3
AUTO_DEGRADE_WINDOW_S = 60.0
AUTO_DEGRADE_FOR_S = 300.0
MIN_HTTP_DEADLINE_MS = 10_000  # the API's minimum request deadline
WORKERS = 8

_executor = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="gemini")


@dataclass(frozen=True)
class CallBudget:
    """Wall-clock budget for the whole call incl. retries (ms), and total HTTP attempts (1 = no retry)."""

    timeout_ms: int
    attempts: int


DEFAULT_BUDGET = CallBudget(timeout_ms=10_000, attempts=3)  # 10 s, 2 retries with backoff (PLAN §1)


class GeminiUnavailable(Exception):
    """Gemini is degraded, timed out, failed or returned something unusable. Callers fall back."""


def http_options(budget: CallBudget) -> types.HttpOptions:
    return types.HttpOptions(
        timeout=max(budget.timeout_ms, MIN_HTTP_DEADLINE_MS),
        retry_options=types.HttpRetryOptions(
            attempts=budget.attempts, initial_delay=0.5, max_delay=2.0, http_status_codes=RETRY_STATUS_CODES
        ),
    )


class Gemini:
    def __init__(
        self,
        client: Any,  # genai.Client, or a fake with `.models.generate_content(model=, contents=, config=)`
        model: str,
        *,
        disabled_reason: str | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.model = model
        self._client = client
        self._disabled_reason = disabled_reason
        self._clock = clock
        self._lock = threading.Lock()
        self._failures: deque[float] = deque()
        self._degraded_until = 0.0

    def degraded_reason(self) -> str | None:
        """Why Gemini is skipped right now, or None when it is available."""
        if self._disabled_reason:
            return self._disabled_reason
        with self._lock:
            if self._clock() < self._degraded_until:
                return f"auto-degraded after {AUTO_DEGRADE_FAILURES} failures"
        return None

    def available(self) -> bool:
        return self.degraded_reason() is None

    def _record_failure(self) -> None:
        with self._lock:
            now = self._clock()
            self._failures.append(now)
            while self._failures and now - self._failures[0] > AUTO_DEGRADE_WINDOW_S:
                self._failures.popleft()
            if len(self._failures) >= AUTO_DEGRADE_FAILURES and now >= self._degraded_until:
                self._degraded_until = now + AUTO_DEGRADE_FOR_S
                self._failures.clear()
                log.warning("gemini auto-degraded for %.0f s (planner/rerank/notes skipped)", AUTO_DEGRADE_FOR_S)

    def generate_json(
        self,
        *,
        system: str,
        contents: Any,
        schema: dict[str, Any],
        temperature: float,
        thinking: ThinkingLevel = "MINIMAL",
        budget: CallBudget = DEFAULT_BUDGET,
        what: str = "call",
    ) -> dict[str, Any]:
        """Structured output: one JSON object matching `schema`. Raises GeminiUnavailable on any problem."""
        reason = self.degraded_reason()
        if reason:
            raise GeminiUnavailable(reason)
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=schema,
            temperature=temperature,
            thinking_config=types.ThinkingConfig(thinking_level=thinking_for(self.model, thinking)),  # type: ignore[arg-type]
            http_options=http_options(budget),
        )
        future = _executor.submit(
            self._client.models.generate_content, model=self.model, contents=contents, config=config
        )
        try:
            response = future.result(timeout=budget.timeout_ms / 1000)
            data = json.loads(response.text or "")
        except errors.APIError as exc:
            self._record_failure()
            log.warning("gemini %s failed: %s %s", what, exc.code, (exc.message or "")[:200])
            raise GeminiUnavailable(f"gemini {what}: HTTP {exc.code}") from exc
        except json.JSONDecodeError as exc:
            self._record_failure()
            log.warning("gemini %s returned non-JSON text", what)
            raise GeminiUnavailable(f"gemini {what}: invalid JSON") from exc
        except Exception as exc:  # budget TimeoutError, httpx timeouts, connection errors
            future.cancel()
            self._record_failure()
            log.warning("gemini %s failed: %s", what, type(exc).__name__)
            raise GeminiUnavailable(f"gemini {what}: {type(exc).__name__}") from exc
        if not isinstance(data, dict):
            self._record_failure()
            raise GeminiUnavailable(f"gemini {what}: expected a JSON object")
        return data


def from_settings(settings: Settings) -> Gemini:
    """The process-wide client (created once in the lifespan)."""
    if settings.gemini_degraded:
        return Gemini(None, settings.gemini_model, disabled_reason="GEMINI_DEGRADED=1")
    if not settings.gemini_api_key:
        log.warning("GEMINI_API_KEY is not set: planner, rerank and notes are skipped")
        return Gemini(None, settings.gemini_model, disabled_reason="no GEMINI_API_KEY")
    client = genai.Client(api_key=settings.gemini_api_key, http_options=http_options(DEFAULT_BUDGET))
    log.info("gemini client ready (%s)", settings.gemini_model)
    return Gemini(client, settings.gemini_model)
