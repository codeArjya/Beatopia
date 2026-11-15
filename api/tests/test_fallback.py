"""T8.1: Freesound fallback (CONTRACT §7.7 + proposal C10): client, trigger, merge, and the four endpoints it touches.

Freesound is faked with httpx.MockTransport; CLAP, DB, Gemini and Storage with the same fakes as the other tests.
"""

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import main
from app.core import embed, excerpt, fallback, personalize, planner, rerank, search_sql, why
from app.core.freesound import Freesound, FreesoundError, TtlCache, cc_license, parse_sound, sound_id
from app.core.gemini import Gemini
from app.models.api import Result, SearchPlan, SearchResponse, TrackDetail, WhyResponse
from tests.test_planner import TRUMPET_RAW, FakeClient
from tests.test_search import CANDS, SETTINGS, SUPABASE, FakePool, cand, validate_schema

VOCAB = planner.vocab_tags(SETTINGS.vocab_path)
PREVIEW = "https://cdn.freesound.org/previews/754/754932_16341892-hq.mp3"


def fs_raw(sid: int, **over: Any) -> dict[str, Any]:
    base = {
        "id": sid,
        "url": f"https://freesound.org/people/someone/sounds/{sid}/",
        "name": f"kazoo take {sid}",
        "tags": ["kazoo", "Hi-Hats", "funny", "drum_loop"],
        "license": "http://creativecommons.org/publicdomain/zero/1.0/",
        "duration": 11.0,
        "username": "someone",
        "previews": {"preview-hq-mp3": PREVIEW, "preview-lq-mp3": "https://cdn.freesound.org/x-lq.mp3"},
    }
    return {**base, **over}


class FakeFreesound:
    """Records requests; answers /search/ and /sounds/{id}/ from `sounds`, previews with MP3-ish bytes."""

    def __init__(self, sounds: list[dict[str, Any]] | None = None) -> None:
        self.sounds = sounds if sounds is not None else [fs_raw(754932), fs_raw(754931), fs_raw(754929)]
        self.requests: list[httpx.Request] = []
        self.status = 200

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status, json={"detail": "nope"})
        path = request.url.path
        if path == "/apiv2/search/":
            return httpx.Response(200, json={"count": len(self.sounds), "results": self.sounds})
        if path.startswith("/apiv2/sounds/"):
            sid = int(path.rstrip("/").split("/")[-1])
            match = [s for s in self.sounds if s["id"] == sid]
            return httpx.Response(200, json=match[0]) if match else httpx.Response(404, json={"detail": "Not found"})
        if path.startswith("/previews/"):
            return httpx.Response(200, content=b"ID3" + b"\0" * 5000)
        return httpx.Response(500)

    def client(self) -> Freesound:
        return Freesound("secret-token", vocab=VOCAB, client=httpx.Client(transport=httpx.MockTransport(self.handler)))


# ---- client ----


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://creativecommons.org/publicdomain/zero/1.0/", "CC0"),
        ("https://creativecommons.org/licenses/by/4.0/", "CC-BY-4.0"),
        ("http://creativecommons.org/licenses/by/3.0/", "CC-BY-3.0"),
        ("https://creativecommons.org/licenses/by-nc/4.0/", None),
        ("http://creativecommons.org/licenses/sampling+/1.0/", None),
        ("https://creativecommons.org.evil/licenses/by/4.0/", None),
    ],
)
def test_cc_license(url: str, expected: str | None) -> None:
    assert cc_license(url) == expected


def test_parse_sound_maps_and_rejects() -> None:
    s = parse_sound(fs_raw(7), frozenset(VOCAB))
    assert s is not None
    assert (s.track_id, s.window_id, s.license, s.preview_url) == ("fs_7", "fs_7:mix:0", "CC0", PREVIEW)
    assert s.tags == ("hi-hats", "drum loop")  # only vocab tags; "kazoo" isn't one
    assert s.attribution.startswith("kazoo take 7 by someone; https://freesound.org/") and "CC0" in s.attribution
    assert parse_sound(fs_raw(7, duration=30.0)).window_end_s == 16.0  # type: ignore[union-attr]

    bad = [
        fs_raw(7, license="https://creativecommons.org/licenses/by-nc/4.0/"),
        fs_raw(7, previews={"preview-hq-mp3": "https://evil.example/x.mp3"}),
        fs_raw(7, previews={"preview-hq-mp3": "http://cdn.freesound.org/x.mp3"}),  # not https
        fs_raw(7, previews={}),
        fs_raw(7, name="  "),
        fs_raw(7, duration=None),
        fs_raw(True),
        "not a dict",
    ]
    assert [parse_sound(b) for b in bad] == [None] * len(bad)


def test_sound_id() -> None:
    assert sound_id("fs_123") == 123 and sound_id("fs_123:mix:0") == 123
    assert [sound_id(x) for x in ("fs_123:drums:0", "fs_123:mix:5000", "jam_1", "fs_x", "fs_")] == [None] * 5


def test_search_sends_auth_filter_and_caches() -> None:
    fake = FakeFreesound([*([fs_raw(i) for i in range(1, 4)]), fs_raw(9, license="http://x.org/nc")])
    fs = fake.client()
    sounds = fs.search("  Kazoo ", 8)
    assert [s.id for s in sounds] == [1, 2, 3]  # the non-CC sound is dropped
    req = fake.requests[0]
    assert req.headers["authorization"] == "Token secret-token"
    assert req.url.params["query"] == "kazoo" and "duration:[1 TO 30]" in req.url.params["filter"]
    assert "Attribution" in req.url.params["filter"] and "previews" in req.url.params["fields"]
    assert fs.search("kazoo", 8) == sounds and len(fake.requests) == 1  # cached
    assert fs.sound(2) == sounds[1] and len(fake.requests) == 1  # search results fill the sound cache
    assert fs.search("", 8) == [] and len(fake.requests) == 1


def test_errors_raise_freesound_error_without_the_token() -> None:
    fake = FakeFreesound()
    fake.status = 401
    fs = fake.client()
    with pytest.raises(FreesoundError) as info:
        fs.search("kazoo", 8)
    assert "401" in str(info.value) and "secret" not in str(info.value)

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=request)

    fs = Freesound("secret-token", client=httpx.Client(transport=httpx.MockTransport(boom)))
    with pytest.raises(FreesoundError, match="ConnectTimeout"):
        fs.search("kazoo", 8)
    with pytest.raises(FreesoundError):
        fs.sound(5)


def test_sound_lookup_and_preview(tmp_path: Path) -> None:
    fake = FakeFreesound()
    fs = fake.client()
    s = fs.sound(754931)
    assert s is not None and s.id == 754931
    assert fs.sound(1) is None  # 404
    dest = tmp_path / "p.mp3"
    assert fs.download_preview(s, str(dest)) == 5003 and dest.read_bytes().startswith(b"ID3")


def test_ttl_cache_expires() -> None:
    now = [0.0]
    c: TtlCache[str, int] = TtlCache(2, 10.0, clock=lambda: now[0])
    c.put("a", 1)
    c.put("b", 2)
    c.put("c", 3)  # evicts "a"
    assert (c.get("a"), c.get("b")) == (None, 2)
    now[0] = 11.0
    assert c.get("b") is None


# ---- trigger, query, merge ----


def low(wid: str) -> Any:
    return cand(wid, 0.80)  # sim 0.20


def test_trigger_rules() -> None:
    strong = [cand(f"jam_{i}:mix:0", 0.60) for i in range(3)]  # sim 0.40
    assert fallback.trigger(strong, ()) is None
    assert fallback.trigger(strong, ("kazoo",)) == "gap"
    assert fallback.trigger([*strong[:2], *[low(f"jam_{i}:mix:0") for i in range(5, 15)]], ()) == "weak"
    assert fallback.trigger([], ()) == "weak"
    assert fallback.trigger([cand(f"jam_{i}:mix:0", 0.70) for i in range(3)], ()) is None  # sim 0.30 exactly


def test_query_for() -> None:
    chips = planner.resolve_chips(["inst.rhodes", "genre.soul", "tempo.90"], SETTINGS.vocab_path)
    assert fallback.query_for("gap", "kazoo orchestra", [], ("kazoo", "bagpipes")) == "kazoo"
    assert fallback.query_for("weak", "dog barking", chips, ()) == "dog barking"
    assert fallback.query_for("weak", None, chips, ()) == "rhodes soul"
    assert fallback.query_for("weak", None, [], ()) == ""


def lib_result(tid: str) -> Result:
    return Result.model_validate(
        {
            "window_id": f"{tid}:mix:0",
            "track": {
                "id": tid,
                "title": tid,
                "source": "jamendo",
                "license": "CC0",
                "attribution": "a",
                "duration_s": 9,
            },
            "stem": "mix",
            "audio_url": "u",
            "start_s": 0,
            "end_s": 9,
            "bars": 4,
            "tags": [],
            "score": 0.4,
        }
    )


def test_merge_puts_freesound_first_and_keeps_some_library() -> None:
    sounds = [parse_sound(fs_raw(i)) for i in range(1, 11)]
    library = [lib_result(f"jam_{i}") for i in range(8)]
    out = fallback.merge(sounds, library, 8)  # type: ignore[arg-type]
    assert [r.track.source for r in out] == ["freesound"] * 6 + ["jamendo"] * 2
    assert [r.score for r in out[:3]] == [0.5, 0.48, 0.46]
    few = fallback.merge(sounds[:2], library, 8)  # type: ignore[arg-type]
    assert [r.track.id for r in few] == ["fs_1", "fs_2", *[f"jam_{i}" for i in range(6)]]
    # A sound that is already a library track (WS1 ingested some Freesound sounds) isn't listed twice.
    dup = fallback.merge(sounds[:2], [lib_result("fs_1")], 8)  # type: ignore[arg-type]
    assert [r.track.id for r in dup] == ["fs_2", "fs_1"]
    assert fallback.merge([], library, 5) == library[:5]


def test_bars_and_detail() -> None:
    assert fallback.bars_for(2.0) == 1 and fallback.bars_for(11.0) == 4
    s = parse_sound(fs_raw(7, duration=25.0), frozenset(VOCAB))
    assert s is not None
    d = fallback.track_detail(s)
    validate_schema(d.model_dump(mode="json"), "TrackDetail")
    assert d.beat_times == [] and d.stems == [] and d.audio_url == PREVIEW
    assert [(w.id, w.stem, w.start_s, w.end_s) for w in d.windows] == [("fs_7:mix:0", "mix", 0.0, 16.0)]


# ---- /search ----


@pytest.fixture
def search_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    env: dict[str, Any] = {"cands": CANDS, "plans": []}
    monkeypatch.setenv("SUPABASE_URL", SUPABASE)

    def fake_fetch(conn: object, plan: SearchPlan, q: np.ndarray, limit: int = 60) -> tuple[list[Any], bool]:
        env["plans"].append(plan)
        return env["cands"], False

    planner.memory_cache.clear()
    rerank.order_memo.clear()
    fallback.notes.clear()
    monkeypatch.setattr(planner, "db_get", lambda pool, key: None)
    monkeypatch.setattr(planner, "db_put", lambda pool, key, planned: None)
    monkeypatch.setattr(embed, "embed_query", lambda text: np.ones(512, dtype=np.float32) / np.sqrt(512))
    monkeypatch.setattr(search_sql, "fetch_candidates", fake_fetch)
    monkeypatch.setattr(personalize, "personalize", lambda conn, sid, q: (q, personalize.Feedback(0, 0)))
    env["fake"] = FakeFreesound()
    app = main.create_app(SETTINGS)
    app.state.pool = FakePool()
    app.state.clap_ready = True
    app.state.freesound = env["fake"].client()
    env["client"] = TestClient(app)
    yield env
    fallback.notes.clear()


def search(env: dict[str, Any], **body: Any) -> SearchResponse:
    r = env["client"].post("/search", json={"session_id": "s1", **body})
    assert r.status_code == 200, r.text
    validate_schema(r.json(), "SearchResponse")
    return SearchResponse.model_validate(r.json())


def test_good_library_match_does_not_call_freesound(search_env: dict[str, Any]) -> None:
    resp = search(search_env, text="dusty soul keys")
    assert not resp.fallback_used and search_env["fake"].requests == []


def test_weak_match_falls_back(search_env: dict[str, Any]) -> None:
    search_env["cands"] = [low(f"jam_{i}:mix:0") for i in range(1, 10)]
    resp = search(search_env, text="dog barking")
    assert resp.fallback_used
    fs_ids = ["fs_754932", "fs_754931", "fs_754929"]
    assert [r.track.id for r in resp.results] == fs_ids + [f"jam_{i}" for i in range(1, 6)]
    first = resp.results[0]
    assert first.window_id == "fs_754932:mix:0" and first.audio_url == PREVIEW and first.stem == "mix"
    assert first.track.license == "CC0" and first.track.attribution and first.track.bpm is None
    assert (first.start_s, first.end_s, first.bars, first.why) == (0.0, 11.0, 4, None)
    assert search_env["fake"].requests[0].url.params["query"] == "dog barking"


def test_vocab_gap_falls_back_with_the_missing_sound(search_env: dict[str, Any]) -> None:
    raw = {**TRUMPET_RAW, "clap_text": "buzzy kazoo ensemble", "must_tags": [], "missing_sounds": ["Kazoo", "trumpet"]}
    search_env["client"].app.state.gemini = Gemini(FakeClient(raw), "m")
    resp = search(search_env, text="kazoo orchestra", limit=5)
    assert resp.fallback_used and len(resp.results) == 5
    assert [r.track.source for r in resp.results] == ["freesound"] * 3 + ["jamendo"] * 2
    assert search_env["fake"].requests[0].url.params["query"] == "kazoo"  # trumpet is a vocab tag: not missing


def test_freesound_down_keeps_library_results(search_env: dict[str, Any]) -> None:
    search_env["cands"] = [low(f"jam_{i}:mix:0") for i in range(3, 12)]
    search_env["fake"].status = 503
    resp = search(search_env, text="dog barking")
    assert not resp.fallback_used and len(resp.results) == 8
    assert all(r.track.source == "jamendo" for r in resp.results)


def test_no_key_keeps_library_results(search_env: dict[str, Any]) -> None:
    search_env["cands"] = []
    search_env["client"].app.state.freesound = None
    resp = search(search_env, text="dog barking")
    assert not resp.fallback_used and resp.results == []


def test_empty_freesound_still_reports_the_fallback(search_env: dict[str, Any]) -> None:
    search_env["cands"] = []
    search_env["fake"].sounds = []
    resp = search(search_env, text="zzzz qqqq")
    assert resp.fallback_used and resp.results == []  # like shared/fixtures/search_empty.json


# ---- /tracks/fs_*, /why, stems ----


class DbPool:
    """Pool fake for /tracks and store_track: `select ... from tracks` finds nothing unless `stored`."""

    def __init__(self) -> None:
        self.stored: dict[str, tuple[Any, ...]] = {}
        self.sql: list[str] = []

    @contextmanager
    def connection(self) -> Iterator["DbPool"]:
        yield self

    def execute(self, sql: str, params: tuple[Any, ...]) -> Any:
        self.sql.append(sql)
        pool = self

        class Cur:
            def fetchone(self) -> Any:
                return (1,) if "select 1 from tracks" in sql and params[0] in pool.stored else None

        if sql.startswith("insert into tracks"):
            self.stored.setdefault(params[0], params)
        return Cur()


@pytest.fixture
def live_app(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, FakeFreesound]]:
    from app.core import tracks

    monkeypatch.setenv("SUPABASE_URL", SUPABASE)
    monkeypatch.setattr(tracks, "fetch_track_detail", lambda conn, tid: None)
    monkeypatch.setattr(why, "fetch_window", lambda pool, wid: None)
    fallback.notes.clear()
    fake = FakeFreesound()
    app = main.create_app(SETTINGS)
    app.state.pool = DbPool()
    app.state.freesound = fake.client()
    yield TestClient(app), fake
    fallback.notes.clear()


def test_get_fallback_track_is_built_live(live_app: tuple[TestClient, FakeFreesound]) -> None:
    c, fake = live_app
    r = c.get("/tracks/fs_754931")
    assert r.status_code == 200, r.text
    validate_schema(r.json(), "TrackDetail")
    d = TrackDetail.model_validate(r.json())
    assert d.track.source == "freesound" and d.track.attribution and len(d.windows) == 1

    assert c.get("/tracks/fs_1").json()["error"]["code"] == "not_found"
    assert c.get("/tracks/jam_404").status_code == 404
    fake.status = 500
    fake_fs = c.app.state.freesound  # type: ignore[attr-defined]
    fake_fs.sounds.clear()
    r = c.get("/tracks/fs_754929")
    assert r.status_code == 502 and r.json()["error"]["code"] == "upstream_error"


def test_why_for_a_fallback_window_uses_the_preview_and_memory_cache(
    live_app: tuple[TestClient, FakeFreesound], monkeypatch: pytest.MonkeyPatch
) -> None:
    c, _ = live_app
    cuts: list[str] = []
    monkeypatch.setattr(excerpt, "cut_excerpt", lambda src, s, d: cuts.append(src) or b"ID3" + b"\0" * 2000)
    fake_gemini = FakeClient({"note": "A buzzy kazoo hum. Chop the first note and pitch it down an octave."})
    c.app.state.gemini = Gemini(fake_gemini, "gm")  # type: ignore[attr-defined]

    r = c.post("/why", json={"window_id": "fs_754932:mix:0"})
    assert r.status_code == 200, r.text
    validate_schema(r.json(), "WhyResponse")
    assert WhyResponse.model_validate(r.json()).note.startswith("A buzzy kazoo")
    assert len(cuts) == 1 and cuts[0].endswith(".mp3") and cuts[0] != PREVIEW  # local copy of the preview
    assert not Path(cuts[0]).exists()  # temp file removed
    assert c.post("/why", json={"window_id": "fs_754932:mix:0"}).json() == r.json()
    assert len(fake_gemini.models.calls) == 1  # 2nd call from the in-memory cache
    assert fallback.notes.get("fs_754932:mix:0") == r.json()["note"]

    assert c.post("/why", json={"window_id": "fs_1:mix:0"}).status_code == 404
    assert c.post("/why", json={"window_id": "jam_1:mix:0"}).status_code == 404
    c.app.state.gemini = None  # type: ignore[attr-defined]
    r = c.post("/why", json={"window_id": "fs_754931:mix:0"})
    assert r.status_code == 502 and r.json()["error"]["code"] == "upstream_error"


def test_why_falls_back_to_the_preview_url_when_the_download_fails(
    live_app: tuple[TestClient, FakeFreesound], monkeypatch: pytest.MonkeyPatch
) -> None:
    c, _ = live_app
    fs = c.app.state.freesound  # type: ignore[attr-defined]
    assert fs.sound(754932) is not None  # cache the sound, then break previews

    def broken(sound: Any, dest: str) -> int:
        raise FreesoundError("freesound preview: HTTP 503")

    monkeypatch.setattr(fs, "download_preview", broken)
    cuts: list[str] = []
    monkeypatch.setattr(excerpt, "cut_excerpt", lambda src, s, d: cuts.append(src) or b"ID3" + b"\0" * 2000)
    c.app.state.gemini = Gemini(FakeClient({"note": "Loop the hum."}), "gm")  # type: ignore[attr-defined]
    r = c.post("/why", json={"window_id": "fs_754932:mix:0"})
    assert r.status_code == 200 and r.json()["note"] == "Loop the hum." and cuts == [PREVIEW]


def test_search_results_pick_up_cached_fallback_notes(search_env: dict[str, Any]) -> None:
    fallback.notes.put("fs_754931:mix:0", "cached kazoo note")
    search_env["cands"] = []
    resp = search(search_env, text="dog barking")
    assert {r.window_id: r.why for r in resp.results}["fs_754931:mix:0"] == "cached kazoo note"


@pytest.fixture
def transcodes(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """The fake previews aren't real audio: stand in for common.audio (bitrate recorded, 11.0 s decoded)."""
    calls: list[tuple[str, str]] = []

    def fake_to_mp3(src: str, dst: str, bitrate: str = "192k") -> None:
        calls.append((Path(src).name, bitrate))
        Path(dst).write_bytes(Path(src).read_bytes())

    monkeypatch.setattr(fallback.audio, "to_mp3", fake_to_mp3)
    monkeypatch.setattr(fallback.audio, "load_mono", lambda path, sr=44100: (np.zeros(11 * 44100), 44100))
    return calls


def test_store_track_transcodes_the_preview_once(
    monkeypatch: pytest.MonkeyPatch, transcodes: list[tuple[str, str]]
) -> None:
    from common import storage

    uploads: list[tuple[str, str, bytes]] = []

    def fake_upload(local: str, path: str, content_type: str) -> str:
        uploads.append((path, content_type, Path(local).read_bytes()[:3]))
        return f"{SUPABASE}/storage/v1/object/public/audio/{path}"

    monkeypatch.setattr(storage, "upload", fake_upload)
    pool, fs = DbPool(), FakeFreesound().client()

    assert fallback.store_track(pool, fs, "fs_754931") is True  # type: ignore[arg-type]
    assert uploads == [("tracks/fs_754931/mix.mp3", "audio/mpeg", b"ID3")]
    row = pool.stored["fs_754931"]
    assert row[1:3] == ("754931", "https://freesound.org/people/someone/sounds/754931/")
    assert row[5] == "CC0" and row[6].startswith("kazoo take 754931 by someone") and row[-1] == uploads[0][0]
    assert "bpm" not in pool.sql[-1]  # bpm/key stay null, no windows
    assert transcodes == [("preview.mp3", "192k")]  # CONTRACT §2 mix format, not Freesound's bytes as they are
    assert row[-2] == 11.0  # duration measured from the stored mix

    assert fallback.store_track(pool, fs, "fs_754931") is False and len(uploads) == 1  # already stored
    assert fallback.store_track(pool, fs, "jam_1") is False  # not a fallback id
    with pytest.raises(Exception, match="not found"):
        fallback.store_track(pool, fs, "fs_1")  # type: ignore[arg-type]

    def broken(*a: Any) -> str:
        raise RuntimeError("storage down")

    monkeypatch.setattr(storage, "upload", broken)
    with pytest.raises(Exception, match="storage") as info:
        fallback.store_track(pool, fs, "fs_754929")  # type: ignore[arg-type]
    assert getattr(info.value, "code", None) == "upstream_error" and "fs_754929" not in pool.stored


@pytest.mark.skipif(__import__("shutil").which("ffprobe") is None, reason="ffmpeg/ffprobe not installed")
def test_store_track_writes_a_contract_mix(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Real ffmpeg: the stored mix is 44.1 kHz stereo MP3 at 192 kbit/s (WS1's full report probes exactly this)."""
    import subprocess

    from app.core.settings import REPO_ROOT
    from common import storage

    fixture = REPO_ROOT / "web" / "public" / "fixtures" / "audio" / "mix.wav"
    kept = tmp_path / "stored.mp3"
    monkeypatch.setattr(storage, "upload", lambda local, path, ct: kept.write_bytes(Path(local).read_bytes()) and "u")
    pool, fs = DbPool(), FakeFreesound().client()
    monkeypatch.setattr(fs, "download_preview", lambda sound, dest: Path(dest).write_bytes(fixture.read_bytes()))

    assert fallback.store_track(pool, fs, "fs_754931") is True  # type: ignore[arg-type]
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
         "stream=codec_name,sample_rate,channels,bit_rate", "-of", "json", str(kept)],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    stream = json.loads(probe.stdout)["streams"][0]
    assert stream["codec_name"] == "mp3" and stream["sample_rate"] == "44100" and stream["channels"] == 2
    assert stream["bit_rate"] == "192000"
    assert pool.stored["fs_754931"][-2] == pytest.approx(16.0, abs=0.1)  # the 16 s fixture, measured


def test_stems_route_stores_the_fallback_track_first(
    live_app: tuple[TestClient, FakeFreesound], monkeypatch: pytest.MonkeyPatch, transcodes: list[tuple[str, str]]
) -> None:
    from app.core import jobs
    from app.models.api import StemsResponse
    from common import storage

    c, _ = live_app
    calls: list[str] = []
    monkeypatch.setattr(storage, "upload", lambda local, path, ct: calls.append(f"upload {path}") or "u")

    def fake_request(conn: object, track_id: str, req: object) -> StemsResponse:
        calls.append(f"stems {track_id}")
        return StemsResponse(job_id="00000000-0000-0000-0000-000000000001")

    monkeypatch.setattr(jobs, "request_stems", fake_request)
    r = c.post("/tracks/fs_754931/stems", json={"start_s": 0, "end_s": 11})
    assert r.status_code == 200, r.text
    assert calls == ["upload tracks/fs_754931/mix.mp3", "stems fs_754931"]
    assert json.loads(r.text)["job_id"]


# ---- planner: missing_sounds ----


def test_missing_sounds_are_cleaned_and_never_vocab_tags() -> None:
    raw = {"missing_sounds": [" Kazoo ", "kazoo", "trumpet", "hi-hats", "", 7, "x" * 41, "dog  barking", "rain", "a"]}
    assert planner.missing_from_gemini(raw, vocab_path=SETTINGS.vocab_path) == ("kazoo", "dog barking", "rain")
    assert planner.missing_from_gemini({}, vocab_path=SETTINGS.vocab_path) == ()
    assert "missing_sounds" in planner.plan_schema()["required"]
    assert "missing_sounds:" in planner.system_prompt(SETTINGS.vocab_path)


def test_plan_cache_row_round_trip_and_old_rows() -> None:
    planned = planner.Planned(SearchPlan(clap_text="kazoo ensemble"), ("kazoo",))
    row = planner.to_row(planned)
    assert row["missing_sounds"] == ["kazoo"] and row["clap_text"] == "kazoo ensemble"
    assert planner.from_row(row) == planned
    old = SearchPlan(clap_text="x").model_dump(mode="json")  # a row cached before C10
    assert planner.from_row(old) == planner.Planned(SearchPlan(clap_text="x"))
    assert planner.cache_key("kazoo", []) != hashlib.sha256(b"kazoo|").hexdigest()  # versioned key


def test_make_plan_carries_missing_sounds_through_the_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    rows: dict[str, Any] = {}
    monkeypatch.setattr(planner, "db_get", lambda pool, key: planner.from_row(rows[key]) if key in rows else None)
    monkeypatch.setattr(planner, "db_put", lambda pool, key, planned: rows.__setitem__(key, planner.to_row(planned)))
    planner.memory_cache.clear()
    g = Gemini(FakeClient({**TRUMPET_RAW, "missing_sounds": ["kazoo"]}), "m")
    vocab = SETTINGS.vocab_path
    first = planner.make_plan("kazoo trumpet", [], [], pool=object(), gemini=g, vocab_path=vocab)  # type: ignore[arg-type]
    assert (first.source, first.missing_sounds) == ("gemini", ("kazoo",))
    planner.memory_cache.clear()
    again = planner.make_plan("kazoo trumpet", [], [], pool=object(), gemini=None, vocab_path=vocab)  # type: ignore[arg-type]
    assert (again.source, again.missing_sounds) == ("db", ("kazoo",))
    rhodes = planner.resolve_chips(["inst.rhodes"], vocab)
    chips_only = planner.make_plan(None, rhodes, ["inst.rhodes"], pool=object(), gemini=g, vocab_path=vocab)  # type: ignore[arg-type]
    assert chips_only.missing_sounds == ()
    planner.memory_cache.clear()
