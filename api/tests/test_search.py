"""T3.2: POST /search v1 (no Gemini) and the deterministic chip merge.

CLAP and the DB are replaced by fakes; responses are validated against the Pydantic model AND the generated JSON
schema in shared/schema (what the web client is typed against).
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import jsonschema
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import main
from app.core import embed, personalize, planner, rerank, search_sql
from app.core.chips import chip_index
from app.core.search_sql import Candidate
from app.core.settings import REPO_ROOT, Settings
from app.models.api import SearchPlan, SearchResponse

SUPABASE = "https://ref.supabase.co"
SETTINGS = Settings.from_env({"SUPABASE_URL": SUPABASE})
SCHEMA = json.loads((REPO_ROOT / "shared" / "schema" / "api.schema.json").read_text("utf-8"))


def validate_schema(body: Any, name: str) -> None:
    jsonschema.validate(body, {"$ref": f"#/$defs/{name}", "$defs": SCHEMA["$defs"]})


def chips(*ids: str) -> list[Any]:
    return planner.resolve_chips(list(ids), SETTINGS.vocab_path)


# ---- planner (chip merge) ----


def test_chip_caption_and_base_plan() -> None:
    cs = chips("inst.trumpet", "genre.soul", "mood.melancholy", "tempo.90", "key.a_minor")
    assert planner.chip_caption(cs) == "trumpet, soul, melancholy music"
    assert planner.base_plan(None, chips("tempo.90")).clap_text == "music"
    assert planner.base_plan("dusty keys", cs).clap_text == "dusty keys"
    assert planner.normalize_text("  Dusty   soul\tkeys ") == "Dusty soul keys"
    assert planner.normalize_text("   ") is None


def test_merge_chips_rules() -> None:
    p = SearchPlan(
        clap_text="x", must_tags=["rhodes"], exclude_tags=["soul", "kick"], bpm_range=(60, 70), key="C major"
    )
    merged = planner.merge_chips(
        p, chips("genre.soul", "inst.rhodes", "tempo.90", "tempo.110", "key.a_minor", "key.d_minor")
    )
    assert merged.must_tags == ["rhodes", "soul"]  # chip tags added once
    assert merged.exclude_tags == ["kick"]  # a chip tag can't be excluded
    assert merged.bpm_range == (85, 115)  # several tempo chips → min(lo)..max(hi)
    assert merged.key == "D minor"  # last key chip wins
    assert planner.merge_chips(p, []) == p


def test_unknown_chip_is_bad_request() -> None:
    with pytest.raises(Exception, match="unknown chip id"):
        chips("inst.kazoo")


# ---- route ----


class FakePool:
    @contextmanager
    def connection(self) -> Iterator[object]:
        yield object()


def cand(wid: str, distance: float, *, stem: str = "mix", start: float = 0.0, why: str | None = None) -> Candidate:
    tid = wid.split(":")[0]
    track = {
        "id": tid,
        "title": tid.upper(),
        "artist": None,
        "source": "jamendo",
        "source_url": None,
        "license": "CC-BY-4.0",
        "attribution": f"{tid} by someone",
        "duration_s": 120.0,
        "bpm": 90.0,
        "key": "A minor",
        "is_hero": stem != "mix",
        "audio_path": f"tracks/{tid}/mix.mp3",
        "beat_times": [i * 60 / 90 for i in range(180)],
    }
    return Candidate(wid, tid, stem, start, start + 10, ("soul", "rhodes"), 0.7, 0.3, distance, why, track)


CANDS = [
    cand("jam_1:mix:0", 0.50, why="cached note"),
    cand("jam_1:mix:20000", 0.52, start=20),
    cand("jam_1:mix:40000", 0.53, start=40),
    cand("jam_1:mix:60000", 0.54, start=60),  # 4th of jam_1 → capped
    cand("jam_2:drums:15200", 0.55, stem="drums", start=15.2),
    *[cand(f"jam_{i}:mix:0", 0.56 + i / 100) for i in range(3, 12)],
]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, list[SearchPlan]]]:
    plans: list[SearchPlan] = []
    monkeypatch.setenv("SUPABASE_URL", SUPABASE)  # common.storage.public_url reads the env

    def fake_fetch(conn: object, plan: SearchPlan, q: np.ndarray, limit: int = 60) -> tuple[list[Candidate], bool]:
        assert q.shape == (512,)
        plans.append(plan)
        return CANDS, False

    planner.memory_cache.clear()
    rerank.order_memo.clear()
    monkeypatch.setattr(planner, "db_get", lambda pool, key: None)
    monkeypatch.setattr(planner, "db_put", lambda pool, key, plan: None)
    monkeypatch.setattr(embed, "embed_query", lambda text: np.ones(512, dtype=np.float32) / np.sqrt(512))
    monkeypatch.setattr(search_sql, "fetch_candidates", fake_fetch)
    monkeypatch.setattr(personalize, "personalize", lambda conn, sid, q: (q, personalize.Feedback(0, 0)))
    app = main.create_app(SETTINGS)
    app.state.pool = FakePool()  # lifespan not run: no real DB or CLAP
    app.state.clap_ready = True
    yield TestClient(app), plans


def test_search_v1_response(client: tuple[TestClient, list[SearchPlan]]) -> None:
    c, plans = client
    r = c.post("/search", json={"text": " dusty soul keys ", "session_id": "s1"})
    assert r.status_code == 200, r.text
    body = r.json()
    validate_schema(body, "SearchResponse")
    resp = SearchResponse.model_validate(body)
    assert resp.query_id.startswith("q_") and not resp.fallback_used
    assert resp.plan == SearchPlan(clap_text="dusty soul keys") == plans[0]
    assert len(resp.results) == 8
    assert max(sum(x.track.id == t for x in resp.results) for t in {x.track.id for x in resp.results}) <= 3
    assert all(0 <= x.score <= 1 for x in resp.results)
    assert [x.score for x in resp.results] == sorted((x.score for x in resp.results), reverse=True)

    first = resp.results[0]
    assert first.window_id == "jam_1:mix:0" and first.why == "cached note"
    assert first.audio_url == f"{SUPABASE}/storage/v1/object/public/audio/tracks/jam_1/mix.mp3"
    assert first.bars == 4 and first.end_s - first.start_s == pytest.approx(10.667, abs=1e-3)
    assert first.track.attribution and first.track.license

    drums = next(x for x in resp.results if x.stem == "drums")
    assert drums.audio_url.endswith("/audio/tracks/jam_2/stems/drums.mp3")
    assert drums.start_s == pytest.approx(15.333, abs=1e-3)  # snapped to the nearest beat
    assert "embed;dur=" in r.headers["server-timing"] and "sql;dur=" in r.headers["server-timing"]


def test_search_limit_and_chips(client: tuple[TestClient, list[SearchPlan]]) -> None:
    c, plans = client
    r = c.post("/search", json={"chips": ["inst.rhodes", "tempo.90"], "limit": 3, "session_id": "s1"})
    assert r.status_code == 200, r.text
    validate_schema(r.json(), "SearchResponse")
    assert len(r.json()["results"]) == 3
    assert plans[0] == SearchPlan(clap_text="rhodes music", must_tags=["rhodes"], bpm_range=(85, 95))


@pytest.mark.parametrize(
    ("body", "code", "status"),
    [
        ({"session_id": "s1"}, "bad_request", 400),
        ({"text": "   ", "chips": [], "session_id": "s1"}, "bad_request", 400),
        ({"text": "x", "chips": ["inst.kazoo"], "session_id": "s1"}, "bad_request", 400),
        ({"text": "x", "limit": 99, "session_id": "s1"}, "bad_request", 400),
    ],
)
def test_search_errors(
    client: tuple[TestClient, list[SearchPlan]], body: dict[str, Any], code: str, status: int
) -> None:
    r = client[0].post("/search", json=body)
    assert r.status_code == status and r.json()["error"]["code"] == code
    validate_schema(r.json()["error"], "ApiError")


def test_search_without_clap_is_upstream_error(client: tuple[TestClient, list[SearchPlan]]) -> None:
    c, _ = client
    c.app.state.clap_ready = False  # type: ignore[attr-defined]
    r = c.post("/search", json={"text": "x", "session_id": "s1"})
    assert r.status_code == 502 and r.json()["error"]["code"] == "upstream_error"


def test_search_uses_the_gemini_plan(client: tuple[TestClient, list[SearchPlan]]) -> None:
    from app.core.gemini import Gemini
    from tests.test_planner import TRUMPET_RAW, FakeClient

    c, plans = client
    c.app.state.gemini = Gemini(FakeClient(TRUMPET_RAW), "m")  # type: ignore[attr-defined]
    r = c.post("/search", json={"text": "sad trumpet around 90 bpm, no drums", "session_id": "s1"})
    assert r.status_code == 200, r.text
    validate_schema(r.json(), "SearchResponse")
    assert plans[0].must_tags == ["trumpet"] and plans[0].bpm_range == (85, 95)
    assert SearchResponse.model_validate(r.json()).plan == plans[0]
    assert "plan;dur=" in r.headers["server-timing"]


def test_search_reranks_and_fills_why(
    client: tuple[TestClient, list[SearchPlan]], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.gemini import Gemini
    from tests.test_planner import TRUMPET_RAW, FakeResponse

    written: list[dict[str, str]] = []
    monkeypatch.setattr(rerank, "write_notes", lambda pool, notes, model: written.append(notes))
    order = ["jam_5:mix:0", "jam_2:drums:15200", "made_up:mix:0"]

    class Models:
        def generate_content(self, *, model: str, contents: Any, config: Any) -> FakeResponse:
            if "order" in config.response_json_schema["properties"]:
                notes = [{"id": "jam_5:mix:0", "note": "Loop it."}]
                return FakeResponse(json.dumps({"order": order, "notes": notes}))
            return FakeResponse(json.dumps(TRUMPET_RAW))

    class Client:
        models = Models()

    c, _ = client
    c.app.state.gemini = Gemini(Client(), "m")  # type: ignore[attr-defined]
    r = c.post("/search", json={"text": "sad trumpet", "session_id": "s1"})
    assert r.status_code == 200, r.text
    validate_schema(r.json(), "SearchResponse")
    res = SearchResponse.model_validate(r.json()).results
    assert [x.window_id for x in res[:3]] == ["jam_5:mix:0", "jam_2:drums:15200", "jam_1:mix:0"]
    assert len(res) == 8 and res[0].why == "Loop it." and res[2].why == "cached note"
    assert written == [{"jam_5:mix:0": "Loop it."}]
    assert "rerank;dur=" in r.headers["server-timing"]


def test_every_chip_resolves() -> None:
    ids = list(chip_index(SETTINGS.vocab_path))
    assert len(planner.resolve_chips(ids, SETTINGS.vocab_path)) == len(ids) == 154
