"""T2.2: GET /tracks/{id}.

The DB integration test runs only with BEATOPIA_DB_TESTS=1 and a DATABASE_URL. It writes inside one transaction and
always rolls back, so nothing is left in the shared database.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import main
from app.core import tracks
from app.core.settings import Settings
from app.fixture_routes import fixture
from app.models.api import TrackDetail

SUPABASE = "https://ref.supabase.co"


class FakePool:
    @contextmanager
    def connection(self) -> Iterator[object]:
        yield object()


def _client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    app = main.create_app(Settings.from_env({"SUPABASE_URL": SUPABASE}))
    app.state.pool = FakePool()  # lifespan not run: no real DB
    return TestClient(app)


def test_track_found(monkeypatch: pytest.MonkeyPatch) -> None:
    detail = TrackDetail.model_validate(fixture("track_detail"))
    monkeypatch.setattr(tracks, "fetch_track_detail", lambda conn, tid: detail if tid == detail.track.id else None)
    r = _client(monkeypatch).get(f"/tracks/{detail.track.id}")
    assert r.status_code == 200
    assert TrackDetail.model_validate(r.json()) == detail
    assert "sql;dur=" in r.headers["server-timing"]


def test_track_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tracks, "fetch_track_detail", lambda conn, tid: None)
    r = _client(monkeypatch).get("/tracks/jam_nope")
    assert r.status_code == 404
    assert r.json() == {"error": {"code": "not_found", "message": "track jam_nope not found"}}


def _vec(x: float) -> str:
    return "[" + ",".join([str(x)] * 512) + "]"


@pytest.mark.skipif(
    os.environ.get("BEATOPIA_DB_TESTS") != "1" or not os.environ.get("DATABASE_URL"),
    reason="set BEATOPIA_DB_TESTS=1 and DATABASE_URL to run against a real database",
)
def test_fetch_track_detail_against_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", SUPABASE)
    tid = "test_ws2_t22"
    conn = psycopg.connect(os.environ["DATABASE_URL"], prepare_threshold=None, connect_timeout=10)
    try:
        conn.execute(
            "insert into tracks (id, source, title, license, attribution, duration_s, bpm, key, beat_times,"
            " audio_path, is_hero) values (%s, 'jamendo', 'T22', 'CC-BY-4.0', 'T22 by test', 30, 90, 'A minor',"
            " %s, %s, true)",
            (tid, [0.0, 0.667, 1.333], f"tracks/{tid}/mix.mp3"),
        )
        for wid, stem, start in (
            (f"{tid}:drums:0", "drums", 0.0),
            (f"{tid}:mix:5000", "mix", 5.0),
            (f"{tid}:mix:0", "mix", 0.0),
        ):
            conn.execute(
                "insert into windows (id, track_id, stem, start_s, end_s, embedding, tags, loopability, rms, density)"
                " values (%s, %s, %s, %s, %s, %s::vector, %s, 0.8, 0.2, 0.5)",
                (wid, tid, stem, start, start + 10, _vec(0.01), ["soul", "rhodes"]),
            )
        conn.execute(
            "insert into stems (track_id, stem, range_start_s, range_end_s, path, model)"
            " values (%s, 'drums', 0, 30, %s, 'htdemucs')",
            (tid, f"tracks/{tid}/stems/drums.mp3"),
        )

        detail = tracks.fetch_track_detail(conn, tid)
        assert detail is not None
        assert detail.track.key == "A minor" and detail.track.is_hero and detail.track.artist is None
        assert detail.audio_url == f"{SUPABASE}/storage/v1/object/public/audio/tracks/{tid}/mix.mp3"
        assert detail.beat_times == pytest.approx([0.0, 0.667, 1.333])
        assert [w.id for w in detail.windows] == [f"{tid}:mix:0", f"{tid}:mix:5000", f"{tid}:drums:0"]
        assert detail.windows[0].tags == ["soul", "rhodes"]
        assert detail.stems[0].url.endswith(f"/audio/tracks/{tid}/stems/drums.mp3")
        assert tracks.fetch_track_detail(conn, "test_ws2_missing") is None
    finally:
        conn.rollback()
        conn.close()
