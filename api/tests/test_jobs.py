"""T7.1: POST /tracks/{id}/stems and GET /jobs/{id}.

The DB test runs only with BEATOPIA_DB_TESTS=1 and a DATABASE_URL, inside one transaction that is rolled back.
"""

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import main
from app.core import jobs
from app.core.errors import ApiException
from app.core.settings import Settings
from app.fixture_routes import fixture
from app.models.api import Job, StemsRequest, StemsResponse

SUPABASE = "https://ref.supabase.co"


class FakePool:
    @contextmanager
    def connection(self) -> Iterator[object]:
        yield object()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("SUPABASE_URL", SUPABASE)
    app = main.create_app(Settings.from_env({"SUPABASE_URL": SUPABASE}))
    app.state.pool = FakePool()
    return TestClient(app)


# ---- range checks ----


@pytest.mark.parametrize(
    ("start", "end", "duration", "code"),
    [
        (5.0, 5.0, None, "bad_request"),
        (-1.0, 4.0, None, "bad_request"),
        (0.0, 61.0, None, "range_too_long"),
        (40.0, 50.0, 30.0, "bad_request"),
    ],
)
def test_check_range_rejects(start: float, end: float, duration: float | None, code: str) -> None:
    with pytest.raises(ApiException) as exc:
        jobs.check_range(StemsRequest(start_s=start, end_s=end), duration)
    assert exc.value.code == code


def test_check_range_clamps_end_to_duration() -> None:
    assert jobs.check_range(StemsRequest(start_s=20.0, end_s=30.05), 30.0) == (20.0, 30.0)
    assert jobs.check_range(StemsRequest(start_s=0.0, end_s=60.0), 180.0) == (0.0, 60.0)


def test_route_range_errors_skip_the_db(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jobs, "request_stems", lambda *a: pytest.fail("DB must not be touched"))
    r = client.post("/tracks/jam_1/stems", json={"start_s": 0, "end_s": 61})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "range_too_long"
    assert client.post("/tracks/jam_1/stems", json={"start_s": 3, "end_s": 2}).json()["error"]["code"] == "bad_request"


# ---- covering stems ----


def _row(stem: str, start: float, end: float, model: str = "htdemucs") -> dict[str, Any]:
    return {
        "track_id": "jam_1",
        "stem": stem,
        "path": f"tracks/jam_1/stems/{stem}_{start}.mp3",
        "range_start_s": start,
        "range_end_s": end,
        "model": model,
    }


def test_pick_covering_needs_a_complete_set_and_prefers_the_narrowest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", SUPABASE)
    four = ("other", "bass", "vocals", "drums")
    full = [_row(s, 0, 180) for s in four]
    partial = [_row(s, 10, 30) for s in ("drums", "bass")]
    narrow = [_row(s, 5, 35) for s in four]

    assert jobs.pick_covering(partial, "htdemucs") is None
    got = jobs.pick_covering(full + partial + narrow, "htdemucs")
    assert got is not None
    assert [s.stem for s in got] == ["vocals", "drums", "bass", "other"]
    assert {(s.range_start_s, s.range_end_s) for s in got} == {(5, 35)}
    assert got[0].url == f"{SUPABASE}/storage/v1/object/public/audio/tracks/jam_1/stems/vocals_5.mp3"
    # a 6-stem request needs guitar + piano too
    assert jobs.pick_covering(full, "htdemucs_6s") is None


def test_stems_route_returns_exactly_one_of_job_or_stems(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    ready = StemsResponse.model_validate(fixture("stems_ready"))
    monkeypatch.setattr(jobs, "request_stems", lambda conn, tid, req: ready)
    body = client.post("/tracks/jam_1/stems", json={"start_s": 0, "end_s": 10}).json()
    assert body["job_id"] is None and len(body["stems"]) == len(ready.stems or [])

    monkeypatch.setattr(jobs, "request_stems", lambda conn, tid, req: StemsResponse(job_id="j-1"))
    assert client.post("/tracks/jam_1/stems", json={"start_s": 0, "end_s": 10}).json() == {
        "job_id": "j-1",
        "stems": None,
    }


# ---- jobs ----


class FakeConn:
    """Answers the single `select ... from jobs` of fetch_job with `row`."""

    def __init__(self, row: dict[str, Any] | None) -> None:
        self.row = row

    @contextmanager
    def cursor(self, row_factory: object = None) -> Iterator["FakeConn"]:
        yield self

    def execute(self, sql: str, params: object = None) -> "FakeConn":
        return self

    def fetchone(self) -> dict[str, Any] | None:
        return self.row


def _job_row(**over: Any) -> dict[str, Any]:
    done = fixture("job_done_stems")
    row = {
        "id": uuid.UUID(done["id"]),
        "kind": "stems",
        "status": "done",
        "progress": 1.0,
        "output": done["output"],
        "error": None,
    }
    return {**row, **over}


def test_fetch_job_done_validates_output() -> None:
    job = jobs.fetch_job(FakeConn(_job_row()), fixture("job_done_stems")["id"])  # type: ignore[arg-type]
    assert job == Job.model_validate(fixture("job_done_stems"))


def test_fetch_job_bad_output_becomes_error() -> None:
    job = jobs.fetch_job(FakeConn(_job_row(output={"stems": [{"stem": "kazoo"}]})), str(uuid.uuid4()))  # type: ignore[arg-type]
    assert job.status == "error" and job.output is None and job.error
    job = jobs.fetch_job(FakeConn(_job_row(output=None)), str(uuid.uuid4()))  # type: ignore[arg-type]
    assert job.status == "error"
    running = jobs.fetch_job(FakeConn(_job_row(status="running", progress=1.7, output=None)), str(uuid.uuid4()))  # type: ignore[arg-type]
    assert running.status == "running" and running.progress == 1.0 and running.error is None


def test_job_not_found_shapes(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    r = client.get("/jobs/not-a-uuid")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    monkeypatch.setattr(jobs, "fetch_job", lambda conn, jid: Job.model_validate(fixture("job_running")))
    assert client.get(f"/jobs/{uuid.uuid4()}").json() == Job.model_validate(fixture("job_running")).model_dump()


# ---- against the real DB (opt-in) ----


@pytest.mark.skipif(
    os.environ.get("BEATOPIA_DB_TESTS") != "1" or not os.environ.get("DATABASE_URL"),
    reason="set BEATOPIA_DB_TESTS=1 and DATABASE_URL to run against a real database",
)
def test_stems_and_jobs_against_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", SUPABASE)
    tid = "test_ws2_t71"
    conn = psycopg.connect(os.environ["DATABASE_URL"], prepare_threshold=None, connect_timeout=10)
    try:
        conn.execute(
            "insert into tracks (id, source, title, license, attribution, duration_s, audio_path)"
            " values (%s, 'jamendo', 'T71', 'CC-BY-4.0', 'T71 by test', 120, %s)",
            (tid, f"tracks/{tid}/mix.mp3"),
        )
        for stem in ("vocals", "drums", "bass", "other"):
            conn.execute(
                "insert into stems (track_id, stem, range_start_s, range_end_s, path, model)"
                " values (%s, %s, 10, 40, %s, 'htdemucs')",
                (tid, stem, f"tracks/{tid}/stems/{stem}_10000_40000.mp3"),
            )

        covered = jobs.request_stems(conn, tid, StemsRequest(start_s=12, end_s=38))
        assert covered.job_id is None and covered.stems is not None and len(covered.stems) == 4

        first = jobs.request_stems(conn, tid, StemsRequest(start_s=50, end_s=70))
        assert first.job_id is not None and first.stems is None
        again = jobs.request_stems(conn, tid, StemsRequest(start_s=55, end_s=65))  # covered by the queued job
        assert again.job_id == first.job_id
        other_model = jobs.request_stems(conn, tid, StemsRequest(start_s=50, end_s=70, model="htdemucs_6s"))
        assert other_model.job_id not in (None, first.job_id)
        clamped = jobs.request_stems(conn, tid, StemsRequest(start_s=100, end_s=130))
        stored = conn.execute("select input from jobs where id = %s", (clamped.job_id,)).fetchone()
        assert stored is not None and stored[0] == {"track_id": tid, "start_s": 100, "end_s": 120, "model": "htdemucs"}

        job = jobs.fetch_job(conn, first.job_id)
        assert job.status == "queued" and job.kind == "stems" and job.output is None
        with pytest.raises(ApiException) as exc:
            jobs.fetch_job(conn, str(uuid.uuid4()))
        assert exc.value.code == "not_found"
        with pytest.raises(ApiException) as exc:
            jobs.request_stems(conn, "test_ws2_missing", StemsRequest(start_s=0, end_s=5))
        assert exc.value.code == "not_found"
    finally:
        conn.rollback()
        conn.close()
