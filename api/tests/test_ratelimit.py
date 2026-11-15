"""T11.2: token-bucket rate limits (429 rate_limited + Retry-After) and Gemini-down behaviour of /search."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core import ratelimit
from app.core.gemini import Gemini
from app.core.ratelimit import Limit, RateLimited, RateLimiter
from app.models.api import SearchPlan, SearchResponse
from tests.test_planner import FakeClient, api_error
from tests.test_search import client, validate_schema  # noqa: F401  (pytest fixture)


class Clock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


def test_bucket_burst_refill_and_retry_after() -> None:
    clock = Clock()
    rl = RateLimiter({"search": Limit(per_minute=30, burst=3)}, clock=clock)
    for _ in range(3):
        rl.check("search", "s1")
    with pytest.raises(RateLimited) as exc:
        rl.check("search", "s1")
    assert exc.value.code == "rate_limited" and exc.value.status == 429
    assert exc.value.retry_after_s == 2 and exc.value.headers == {"Retry-After": "2"}  # 30/min = one per 2 s
    rl.check("search", "s2")  # other keys have their own bucket
    clock.t += 2.0
    rl.check("search", "s1")  # refilled one token
    with pytest.raises(RateLimited):
        rl.check("search", "s1")
    clock.t += 3600
    for _ in range(3):  # refill is capped at the burst
        rl.check("search", "s1")
    with pytest.raises(RateLimited):
        rl.check("search", "s1")
    rl.check("unlisted", "s1")  # endpoints without a limit are never refused


def test_idle_buckets_are_evicted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ratelimit, "MAX_KEYS", 2)
    rl = RateLimiter({"why": Limit(per_minute=1, burst=1)}, clock=Clock())
    rl.check("why", "a")
    rl.check("why", "b")
    rl.check("why", "c")  # evicts "a", the least recently used
    rl.check("why", "a")  # a fresh bucket again
    with pytest.raises(RateLimited):
        rl.check("why", "c")


def test_default_limits_cover_the_gemini_endpoints() -> None:
    assert set(ratelimit.LIMITS) == {"search", "why", "assist"}
    assert all(lim.burst >= 10 and lim.per_minute >= 20 for lim in ratelimit.LIMITS.values())


def test_search_is_limited_per_session(client: tuple[TestClient, list[SearchPlan]]) -> None:  # noqa: F811
    c, _ = client
    c.app.state.limiter = RateLimiter({"search": Limit(per_minute=6, burst=2)})  # type: ignore[attr-defined]
    for _ in range(2):
        assert c.post("/search", json={"text": "soul", "session_id": "s1"}).status_code == 200
    r = c.post("/search", json={"text": "soul", "session_id": "s1"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
    validate_schema(r.json()["error"], "ApiError")
    assert r.headers["retry-after"] == "10"
    assert c.post("/search", json={"text": "soul", "session_id": "s2"}).status_code == 200


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/why", {"window_id": "jam_1:mix:0"}),
        ("/assist", {"messages": [{"role": "user", "content": "reverse it"}], "editor": {"clips": [], "ops": []}}),
    ],
)
def test_why_and_assist_are_limited_per_client_ip(
    client: tuple[TestClient, list[SearchPlan]],  # noqa: F811
    path: str,
    body: dict[str, Any],
) -> None:
    c, _ = client
    what = path.strip("/")
    c.app.state.limiter = RateLimiter({what: Limit(per_minute=60, burst=0)})  # type: ignore[attr-defined]
    r = c.post(path, json=body, headers={"X-Forwarded-For": "6.6.6.6, 203.0.113.7"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited", r.text
    assert r.headers["retry-after"] == "1"
    assert c.app.state.limiter._buckets.keys() == {(what, "203.0.113.7")}  # type: ignore[attr-defined]  # last hop


def test_client_ip_without_proxy(client: tuple[TestClient, list[SearchPlan]]) -> None:  # noqa: F811
    c, _ = client
    c.app.state.limiter = RateLimiter({"why": Limit(per_minute=60, burst=0)})  # type: ignore[attr-defined]
    assert c.post("/why", json={"window_id": "x"}).status_code == 429
    assert c.app.state.limiter._buckets.keys() == {("why", "testclient")}  # type: ignore[attr-defined]


def test_search_survives_gemini_503s_with_cached_notes(client: tuple[TestClient, list[SearchPlan]]) -> None:  # noqa: F811
    """Gemini down: raw-text plan, score order, cached notes; after 3 failures Gemini is skipped entirely."""
    c, plans = client
    fake = FakeClient(api_error(503))
    gemini = Gemini(fake, "m")
    c.app.state.gemini = gemini  # type: ignore[attr-defined]

    r = c.post("/search", json={"text": "dusty soul keys", "session_id": "s1"})
    assert r.status_code == 200, r.text
    validate_schema(r.json(), "SearchResponse")
    resp = SearchResponse.model_validate(r.json())
    assert resp.plan == SearchPlan(clap_text="dusty soul keys") == plans[0]  # planner fallback
    assert resp.results[0].window_id == "jam_1:mix:0" and resp.results[0].why == "cached note"
    assert [x.score for x in resp.results] == sorted((x.score for x in resp.results), reverse=True)
    assert len(fake.models.calls) == 2  # planner + rerank, each failed once

    assert c.post("/search", json={"text": "warm rhodes", "session_id": "s1"}).status_code == 200
    assert not gemini.available()  # 3rd failure (planner) auto-degraded; rerank was skipped
    calls = len(fake.models.calls)
    r = c.post("/search", json={"text": "eerie flute", "session_id": "s1"})
    assert r.status_code == 200 and r.json()["results"][0]["why"] == "cached note"
    assert len(fake.models.calls) == calls  # degraded: no Gemini call at all
