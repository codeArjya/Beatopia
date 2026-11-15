"""T9.1: POST /events and per-session Rocchio feedback.

The DB test runs only with BEATOPIA_DB_TESTS=1 and a DATABASE_URL, inside one transaction that is rolled back.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager

import numpy as np
import psycopg
import pytest
from fastapi.testclient import TestClient
from pgvector.psycopg import register_vector

from app import main
from app.core import personalize
from app.core.settings import Settings
from app.models.api import EventRequest


class FakePool:
    @contextmanager
    def connection(self) -> Iterator[object]:
        yield object()


@pytest.fixture
def client() -> TestClient:
    app = main.create_app(Settings.from_env({"SUPABASE_URL": "https://ref.supabase.co"}))
    app.state.pool = FakePool()
    return TestClient(app)


def test_event_recorded(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[EventRequest] = []
    monkeypatch.setattr(personalize, "record_event", lambda conn, ev: seen.append(ev))
    body = {"session_id": "s1", "query_id": "q_1", "window_id": "jam_1:mix:0", "action": "pick"}
    r = client.post("/events", json=body)
    assert r.status_code == 204 and r.content == b""
    assert seen == [EventRequest(**body)]


def test_event_validation(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(personalize, "record_event", lambda conn, ev: pytest.fail("must not be recorded"))
    bad_action = client.post("/events", json={"session_id": "s", "window_id": "w", "action": "like"})
    assert bad_action.status_code == 400 and bad_action.json()["error"]["code"] == "bad_request"
    blank = client.post("/events", json={"session_id": " ", "window_id": "w", "action": "play"})
    assert blank.status_code == 400


def _unit(seed: int) -> np.ndarray:
    v = np.random.default_rng(seed).standard_normal(512).astype(np.float32)
    return v / np.linalg.norm(v)


def test_rocchio_moves_toward_picks_and_away_from_skips() -> None:
    q, pick, skip = _unit(1), _unit(2), _unit(3)
    q_before = q.copy()
    assert personalize.rocchio(q, [], [skip]) is q  # no pick → unchanged
    out = personalize.rocchio(q, [pick], [skip])
    assert np.array_equal(q, q_before)  # input not mutated (it may be LRU-cached)
    assert abs(float(np.linalg.norm(out)) - 1) < 1e-5
    assert float(out @ pick) > float(q @ pick)
    assert float(out @ skip) < float(q @ skip)
    expected = q + 0.3 * pick - 0.1 * skip
    assert np.allclose(out, expected / np.linalg.norm(expected), atol=1e-6)


def _vec(v: np.ndarray) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


@pytest.mark.skipif(
    os.environ.get("BEATOPIA_DB_TESTS") != "1" or not os.environ.get("DATABASE_URL"),
    reason="set BEATOPIA_DB_TESTS=1 and DATABASE_URL to run against a real database",
)
def test_pick_pulls_the_picked_track_up_against_db() -> None:
    """After a pick, the picked window's similarity to the query rises (so its rank can only improve)."""
    conn = psycopg.connect(os.environ["DATABASE_URL"], prepare_threshold=None, connect_timeout=10)
    register_vector(conn)
    tid, sid = "test_ws2_t91", "test-session-t91"
    q, picked_vec, skipped_vec, other = _unit(10), _unit(11), _unit(12), _unit(13)
    try:
        conn.execute(
            "insert into tracks (id, source, title, license, attribution, duration_s, audio_path)"
            " values (%s, 'jamendo', 'T91', 'CC0', 'T91', 60, %s)",
            (tid, f"tracks/{tid}/mix.mp3"),
        )
        for wid, v in ((f"{tid}:mix:0", picked_vec), (f"{tid}:mix:10000", skipped_vec), (f"{tid}:mix:20000", other)):
            conn.execute(
                "insert into windows (id, track_id, start_s, end_s, embedding) values (%s, %s, 0, 10, %s::vector)",
                (wid, tid, _vec(v)),
            )

        same, fb = personalize.personalize(conn, sid, q)
        assert same is q and fb == personalize.Feedback(0, 0)

        for wid, action in ((f"{tid}:mix:0", "pick"), (f"{tid}:mix:10000", "skip"), ("fs_1:mix:0", "pick")):
            personalize.record_event(conn, EventRequest(session_id=sid, window_id=wid, action=action))
        personalize.record_event(
            conn, EventRequest(session_id="someone-else", window_id=f"{tid}:mix:20000", action="pick")
        )

        q2, fb = personalize.personalize(conn, sid, q)
        assert fb == personalize.Feedback(1, 1)  # fs_* pick has no embedding; other sessions don't count
        assert float(q2 @ picked_vec) > float(q @ picked_vec)
        assert float(q2 @ skipped_vec) < float(q @ skipped_vec)
        n = conn.execute("select count(*) from events where session_id = %s", (sid,)).fetchone()
        assert n is not None and n[0] == 3
    finally:
        conn.rollback()
        conn.close()
