"""T4.3: POST /why with the audio excerpt (P3), the text-only fallback (P3b) and the notes cache."""

import json
import shutil
import threading
from collections.abc import Iterator
from concurrent.futures import Future
from typing import Any

import jsonschema
import pytest
from fastapi.testclient import TestClient

from app import main
from app.core import excerpt, rerank, why
from app.core.gemini import Gemini
from app.core.settings import REPO_ROOT, Settings
from tests.test_planner import FakeClient, api_error

SUPABASE = "https://ref.supabase.co"
SETTINGS = Settings.from_env({"SUPABASE_URL": SUPABASE})
SCHEMA = json.loads((REPO_ROOT / "shared" / "schema" / "api.schema.json").read_text("utf-8"))
FIXTURE_MIX = REPO_ROOT / "web" / "public" / "fixtures" / "audio" / "mix.wav"
WID = "jam_1:mix:30000"
BEATS = [i * 60 / 90 for i in range(200)]  # 90 bpm from 0 s


def row(**over: Any) -> dict[str, Any]:
    base = {
        "id": WID,
        "track_id": "jam_1",
        "stem": "mix",
        "start_s": 30.1,
        "end_s": 40.1,
        "tags": ["soul", "rhodes"],
        "title": "Late Night",
        "artist": None,
        "bpm": 90.0,
        "key": "A minor",
        "duration_s": 120.0,
        "beat_times": BEATS,
        "audio_path": "tracks/jam_1/mix.mp3",
        "note": None,
    }
    return {**base, **over}


class Env:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {WID: row()}
        self.stored: list[tuple[str, str, str]] = []
        self.excerpts: list[tuple[str, float, float]] = []
        self.excerpt_error: excerpt.ExcerptError | None = None


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Iterator[Env]:
    e = Env()
    monkeypatch.setenv("SUPABASE_URL", SUPABASE)

    def fake_cut(source: str, start_s: float, duration_s: float) -> bytes:
        e.excerpts.append((source, start_s, duration_s))
        if e.excerpt_error:
            raise e.excerpt_error
        return b"ID3" + b"\0" * 2000

    def fake_store(pool: object, wid: str, text: str, model: str) -> str:
        e.stored.append((wid, text, model))
        return text

    monkeypatch.setattr(why, "fetch_window", lambda pool, wid: e.rows.get(wid))
    monkeypatch.setattr(why, "store_note", fake_store)
    monkeypatch.setattr(excerpt, "cut_excerpt", fake_cut)
    yield e


def client_with(gemini: Gemini | None) -> TestClient:
    app = main.create_app(SETTINGS)
    app.state.pool = object()  # lifespan not run; fetch/store are faked
    app.state.gemini = gemini
    return TestClient(app)


def post(c: TestClient, wid: str = WID) -> Any:
    return c.post("/why", json={"window_id": wid})


def test_cached_note_is_returned_without_gemini(env: Env) -> None:
    env.rows[WID]["note"] = "cached from the rerank"
    fake = FakeClient({"note": "should not be used"})
    r = post(client_with(Gemini(fake, "gm")))
    assert r.status_code == 200
    assert r.json() == {"window_id": WID, "note": "cached from the rerank"}
    assert fake.models.calls == [] and env.excerpts == [] and env.stored == []


def test_audio_note_is_generated_and_cached(env: Env) -> None:
    fake = FakeClient({"note": "  Warm Rhodes chords with   space around them. Chop each chord. Pitch it down. "})
    r = post(client_with(Gemini(fake, "gm")))
    assert r.status_code == 200, r.text
    body = r.json()
    jsonschema.validate(body, {"$ref": "#/$defs/WhyResponse", "$defs": SCHEMA["$defs"]})
    assert body["note"] == "Warm Rhodes chords with space around them. Chop each chord. Pitch it down."
    assert env.stored == [(WID, body["note"], "gm:audio")]

    # the excerpt is the snapped window /search serves: start on the nearest beat, 4 bars at 90 bpm
    source, start, seconds = env.excerpts[0]
    assert source == f"{SUPABASE}/storage/v1/object/public/audio/tracks/jam_1/mix.mp3"
    assert start == pytest.approx(30.0, abs=1e-3) and seconds == pytest.approx(10.667, abs=1e-3)

    call = fake.models.calls[0]
    assert call["config"].system_instruction == why.SYSTEM_AUDIO
    assert call["config"].temperature == why.WHY_TEMPERATURE
    audio, text = call["contents"]
    assert audio.inline_data.mime_type == "audio/mp3" and audio.inline_data.data.startswith(b"ID3")
    assert 'Title: "Late Night" by unknown artist' in text.text
    assert "Tempo: 90 BPM   Key: A minor" in text.text and "Tags: soul, rhodes" in text.text
    assert "Excerpt length: 10.7 s (4 bars)" in text.text


def test_text_only_fallback_when_audio_fetch_fails(env: Env) -> None:
    env.excerpt_error = excerpt.ExcerptError("ffmpeg exited with 1")
    fake = FakeClient({"note": "Soul Rhodes chords at 90 BPM. Chop the first chord. Try it reversed."})
    r = post(client_with(Gemini(fake, "gm")))
    assert r.status_code == 200, r.text
    assert env.stored == [(WID, r.json()["note"], "gm:text")]
    call = fake.models.calls[0]
    assert call["config"].system_instruction == why.SYSTEM_TEXT
    assert isinstance(call["contents"], str) and "Stem: mix" in call["contents"]
    assert "cannot hear it" in why.SYSTEM_TEXT and "trust the audio" not in why.SYSTEM_TEXT


def test_note_is_trimmed_to_45_words(env: Env) -> None:
    long = "This is a sentence of words. " * 12  # 72 words
    r = post(client_with(Gemini(FakeClient({"note": long}), "gm")))
    note = r.json()["note"]
    assert len(note.split()) <= why.NOTE_MAX_WORDS and note.endswith(".")


def test_stem_window_uses_the_stem_file_and_caps_the_excerpt(env: Env) -> None:
    env.rows["jam_1:drums:0"] = row(id="jam_1:drums:0", stem="drums", start_s=0.0, end_s=30.0, bpm=None)
    r = post(client_with(Gemini(FakeClient({"note": "Tight drums."}), "gm")), "jam_1:drums:0")
    assert r.status_code == 200
    source, start, seconds = env.excerpts[0]
    assert source.endswith("/audio/tracks/jam_1/stems/drums.mp3")
    assert start == 0.0 and seconds == excerpt.MAX_EXCERPT_S


@pytest.mark.parametrize(
    ("gemini", "reply"),
    [
        (None, None),
        (Gemini(None, "gm", disabled_reason="GEMINI_DEGRADED=1"), None),
        ("client", api_error(503)),
        ("client", {"note": "   "}),
        ("client", "not json"),
    ],
)
def test_no_cached_note_and_no_gemini_is_upstream_error(env: Env, gemini: Any, reply: Any) -> None:
    g = Gemini(FakeClient(reply), "gm") if gemini == "client" else gemini
    r = post(client_with(g))
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "upstream_error"
    assert env.stored == []


def test_unknown_window_is_404(env: Env) -> None:
    r = post(client_with(Gemini(FakeClient({"note": "x"}), "gm")), "fs_999:mix:0")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_bad_request_body_is_400(env: Env) -> None:
    r = client_with(None).post("/why", json={})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_request"


# ---- the real ffmpeg excerpt ----

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@needs_ffmpeg
def test_cut_excerpt_on_local_audio() -> None:
    mp3 = excerpt.cut_excerpt(str(FIXTURE_MIX), 2.0, 30.0)  # capped at 15 s
    assert len(mp3) > excerpt.MIN_BYTES
    # 64 kbps mono: ≈ 8 KB per second; the fixture is 16 s, so 2..16 s → 14 s of audio
    assert 80_000 < len(mp3) < 150_000


@needs_ffmpeg
def test_cut_excerpt_errors() -> None:
    with pytest.raises(excerpt.ExcerptError):
        excerpt.cut_excerpt(str(FIXTURE_MIX.with_name("missing.wav")), 0.0, 5.0)
    with pytest.raises(excerpt.ExcerptError):
        excerpt.cut_excerpt(str(FIXTURE_MIX), 0.0, 0.0)


def test_pending_rerank_note_is_awaited_instead_of_generated(env: Env) -> None:
    """T11.1: a search's background notes call (P2b) is writing this window's note; /why waits for it."""
    rerank.pending.clear()
    batch: Future[dict[str, str]] = Future()
    rerank.pending.claim([WID], lambda ids: batch)
    threading.Timer(0.1, lambda: batch.set_result({WID: "Loop the first two bars."})).start()
    fake = FakeClient({"note": "should not be used"})
    r = post(client_with(Gemini(fake, "gm")))
    assert r.status_code == 200 and r.json() == {"window_id": WID, "note": "Loop the first two bars."}
    assert fake.models.calls == [] and env.excerpts == [] and env.stored == []

    # A failed batch falls through to the normal audio note.
    failed: Future[dict[str, str]] = Future()
    rerank.pending.claim([WID], lambda ids: failed)
    failed.set_exception(RuntimeError("gemini notes: HTTP 503"))
    r = post(client_with(Gemini(FakeClient({"note": "Own note."}), "gm")))
    assert r.status_code == 200 and r.json()["note"] == "Own note."
    rerank.pending.clear()
