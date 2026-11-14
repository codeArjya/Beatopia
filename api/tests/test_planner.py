"""T4.1: Gemini client (budgets, degraded switch) and the P1 planner + plan_cache, with a recorded-response fake."""

import json
import time
from collections.abc import Iterator
from typing import Any

import jsonschema
import pytest
from google.genai import errors

from app.core import gemini as gem
from app.core import planner
from app.core.settings import Settings
from app.models.api import SearchPlan

SETTINGS = Settings.from_env({})
VOCAB = SETTINGS.vocab_path

# What Gemini returned live for this request (T4.1 acceptance query), trimmed to the schema fields.
TRUMPET_RAW = {
    "clap_text": "a melancholy solo trumpet over soft, sparse jazz chords",
    "must_tags": ["trumpet"],
    "exclude_tags": ["drum loop", "breakbeat", "kick", "snare", "hi-hats", "cymbals"],
    "bpm_min": 85,
    "bpm_max": 95,
    "key": None,
    "stems_wanted": [],
    "prefer_sparse": False,
}


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeModels:
    def __init__(self, replies: list[Any]) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, *, model: str, contents: Any, config: Any) -> FakeResponse:
        self.calls.append({"model": model, "contents": contents, "config": config})
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return FakeResponse(reply if isinstance(reply, str) else json.dumps(reply))


class FakeClient:
    def __init__(self, *replies: Any) -> None:
        self.models = FakeModels(list(replies))


def api_error(code: int) -> errors.APIError:
    return errors.APIError(code, {"error": {"code": code, "message": "boom", "status": "X"}})


class FakePool:
    """plan_cache stand-in: the planner's db_get/db_put are monkeypatched onto this dict."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}


@pytest.fixture
def pool(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakePool]:
    planner.memory_cache.clear()
    p = FakePool()

    def get(pool: FakePool, key: str) -> SearchPlan | None:
        row = pool.rows.get(key)
        return SearchPlan.model_validate(row) if row else None

    def put(pool: FakePool, key: str, plan: SearchPlan) -> None:
        pool.rows[key] = plan.model_dump(mode="json")

    monkeypatch.setattr(planner, "db_get", get)
    monkeypatch.setattr(planner, "db_put", put)
    yield p
    planner.memory_cache.clear()


def plan(text: str | None, chip_ids: list[str], pool: FakePool, g: gem.Gemini | None) -> planner.PlanOutcome:
    chips = planner.resolve_chips(chip_ids, VOCAB)
    return planner.make_plan(text, chips, chip_ids, pool=pool, gemini=g, vocab_path=VOCAB)  # type: ignore[arg-type]


# ---- schema and conversion ----


def test_plan_schema_is_valid_and_accepts_the_recorded_reply() -> None:
    schema = planner.plan_schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(TRUMPET_RAW, schema)
    # No tag enums (they make the API return 400); the prompt carries the full vocab instead.
    assert "enum" not in schema["properties"]["must_tags"]["items"]
    assert len(schema["properties"]["key"]["anyOf"][0]["enum"]) == 24
    prompt = planner.system_prompt(VOCAB)
    assert all(t in prompt for t in planner.vocab_tags(VOCAB)) and "{" not in prompt


def test_from_gemini_conversion_is_defensive() -> None:
    p = planner.from_gemini(TRUMPET_RAW, fallback_text="x", vocab_path=VOCAB)
    assert p.must_tags == ["trumpet"] and "kick" in p.exclude_tags and p.bpm_range == (85, 95)

    messy = {
        "clap_text": "  ",
        "must_tags": ["trumpet", "trumpet", "kazoo", 3],
        "exclude_tags": ["trumpet", "kick"],
        "bpm_min": 110,
        "bpm_max": 90,
        "key": "Bb minor",
        "stems_wanted": ["drums", "drums", "horns"],
        "prefer_sparse": "yes",
    }
    p = planner.from_gemini(messy, fallback_text="raw text", vocab_path=VOCAB)
    assert p == SearchPlan(
        clap_text="raw text", must_tags=["trumpet"], exclude_tags=["kick"], bpm_range=(90, 110), stems_wanted=["drums"]
    )
    assert planner.from_gemini({"bpm_min": 90}, fallback_text="t", vocab_path=VOCAB).bpm_range == (85, 95)
    assert planner.from_gemini({"bpm_max": 999}, fallback_text="t", vocab_path=VOCAB).bpm_range is None
    assert planner.from_gemini({"key": "F# major"}, fallback_text="t", vocab_path=VOCAB).key == "F# major"


def test_cache_key_normalizes_text_and_chip_order() -> None:
    a = planner.cache_key("Sad  Trumpet ", ["tempo.90", "genre.soul"])
    assert a == planner.cache_key("sad trumpet", ["genre.soul", "tempo.90"])
    assert a != planner.cache_key("sad trumpet", ["genre.soul"])


# ---- make_plan ----


def test_planner_calls_gemini_once_then_hits_the_cache(pool: FakePool) -> None:
    client = FakeClient(TRUMPET_RAW)
    g = gem.Gemini(client, "gemini-test")
    text = "sad trumpet around 90 bpm, no drums"

    first = plan(text, [], pool, g)
    assert first.source == "gemini" and not first.cached
    assert first.plan.must_tags == ["trumpet"] and first.plan.bpm_range == (85, 95)
    assert {"drum loop", "kick", "snare"} <= set(first.plan.exclude_tags)

    call = client.models.calls[0]
    assert call["model"] == "gemini-test" and json.dumps(text) in call["contents"]
    cfg = call["config"]
    assert cfg.response_mime_type == "application/json" and cfg.temperature == planner.PLAN_TEMPERATURE
    assert cfg.http_options.timeout == gem.MIN_HTTP_DEADLINE_MS  # the API rejects deadlines < 10 s
    assert cfg.http_options.retry_options.attempts == planner.PLAN_BUDGET.attempts

    again = plan("  Sad trumpet around 90 BPM, no drums", [], pool, g)
    assert again.source == "memory" and again.plan == first.plan
    planner.memory_cache.clear()
    from_db = plan(text, [], pool, g)
    assert from_db.source == "db" and from_db.plan == first.plan
    assert len(client.models.calls) == 1


def test_chips_merge_after_gemini_and_win(pool: FakePool) -> None:
    client = FakeClient({**TRUMPET_RAW, "exclude_tags": ["soul", "kick"]})
    out = plan("sad trumpet around 90 bpm", ["genre.soul", "tempo.120", "key.a_minor"], pool, gem.Gemini(client, "m"))
    assert out.plan.must_tags == ["trumpet", "soul"]
    assert out.plan.exclude_tags == ["kick"]  # a chip tag can't be excluded
    assert out.plan.bpm_range == (115, 125)  # the tempo chip overrides Gemini's range
    assert out.plan.key == "A minor"
    assert "Soul, 120 BPM, A minor" in client.models.calls[0]["contents"]
    # The cache stores the pre-merge plan: chips are re-applied on every hit.
    assert next(iter(pool.rows.values()))["bpm_range"] == [85.0, 95.0]


def test_chips_only_never_calls_gemini(pool: FakePool) -> None:
    client = FakeClient(TRUMPET_RAW)
    out = plan(None, ["inst.trumpet", "tempo.90"], pool, gem.Gemini(client, "m"))
    assert out.source == "chips" and out.plan.clap_text == "trumpet music" and out.plan.bpm_range == (85, 95)
    assert client.models.calls == [] and pool.rows == {}


@pytest.mark.parametrize("reply", [api_error(503), api_error(429), "not json", "[1, 2]", TimeoutError()])
def test_gemini_failure_falls_back_and_is_not_cached(pool: FakePool, reply: Any) -> None:
    client = FakeClient(reply)
    out = plan("dusty soul keys", ["genre.soul"], pool, gem.Gemini(client, "m"))
    assert out.source == "fallback"
    assert out.plan == SearchPlan(clap_text="dusty soul keys", must_tags=["soul"])
    assert pool.rows == {} and planner.memory_cache.get(planner.cache_key("dusty soul keys", ["genre.soul"])) is None


def test_no_client_falls_back(pool: FakePool) -> None:
    assert plan("dusty soul keys", [], pool, None).source == "fallback"


def test_cache_read_error_still_plans(pool: FakePool, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_: Any) -> None:
        raise RuntimeError("db down")

    monkeypatch.setattr(planner, "db_get", broken)
    monkeypatch.setattr(planner, "db_put", broken)
    assert plan("dusty soul keys", [], pool, gem.Gemini(FakeClient(TRUMPET_RAW), "m")).source == "gemini"


def test_budget_is_wall_clock() -> None:
    class Slow(FakeModels):
        def generate_content(self, **kw: Any) -> FakeResponse:
            time.sleep(0.5)
            return super().generate_content(**kw)

    client = FakeClient(TRUMPET_RAW)
    client.models = Slow([TRUMPET_RAW])
    g = gem.Gemini(client, "m")
    t0 = time.perf_counter()
    with pytest.raises(gem.GeminiUnavailable, match="TimeoutError"):
        g.generate_json(system="s", contents="c", schema={}, temperature=0, budget=gem.CallBudget(100, 1))
    assert time.perf_counter() - t0 < 0.4


# ---- degraded switch ----


def test_degraded_by_setting_or_missing_key() -> None:
    off = gem.from_settings(Settings.from_env({"GEMINI_DEGRADED": "1", "GEMINI_API_KEY": "k"}))
    assert off.degraded_reason() == "GEMINI_DEGRADED=1"
    assert gem.from_settings(Settings.from_env({})).degraded_reason() == "no GEMINI_API_KEY"
    with pytest.raises(gem.GeminiUnavailable):
        off.generate_json(system="s", contents="c", schema={}, temperature=0)


def test_auto_degrade_after_repeated_failures_and_recovery() -> None:
    now = [1000.0]
    client = FakeClient(api_error(503))
    g = gem.Gemini(client, "m", clock=lambda: now[0])
    for _ in range(gem.AUTO_DEGRADE_FAILURES):
        assert g.available()
        with pytest.raises(gem.GeminiUnavailable):
            g.generate_json(system="s", contents="c", schema={}, temperature=0)
        now[0] += 1
    assert not g.available()
    with pytest.raises(gem.GeminiUnavailable, match="auto-degraded"):
        g.generate_json(system="s", contents="c", schema={}, temperature=0)
    assert len(client.models.calls) == gem.AUTO_DEGRADE_FAILURES  # no network call while degraded
    now[0] += gem.AUTO_DEGRADE_FOR_S
    assert g.available()


def test_spread_out_failures_do_not_degrade() -> None:
    now = [0.0]
    g = gem.Gemini(FakeClient(api_error(500)), "m", clock=lambda: now[0])
    for _ in range(5):
        with pytest.raises(gem.GeminiUnavailable):
            g.generate_json(system="s", contents="c", schema={}, temperature=0)
        now[0] += gem.AUTO_DEGRADE_WINDOW_S
    assert g.available()


def test_minimal_thinking_falls_back_to_low_where_rejected() -> None:
    assert gem.thinking_for("gemini-3.6-flash", "MINIMAL") == "MINIMAL"
    assert gem.thinking_for("gemini-3.8-flash", "MINIMAL") == "LOW"
    assert gem.thinking_for("models/gemini-3.8-flash", "MEDIUM") == "MEDIUM"
    client = FakeClient({"note": "x"})
    gem.Gemini(client, "gemini-3.8-flash").generate_json(system="s", contents="c", schema={}, temperature=0)
    assert client.models.calls[0]["config"].thinking_config.thinking_level == "LOW"
