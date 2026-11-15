"""Opt-in real DB acceptance. Deliberately invalid jobs remain as terminal audit rows."""

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from psycopg.types.json import Jsonb

from common import db
from worker import handlers, jobs, main

pytestmark = pytest.mark.skipif(os.environ.get("WORKER_LIVE_TESTS") != "1", reason="requires explicit live DB run")


def enqueue(data: dict, kind: str = "stems") -> str:
    with db.connect() as conn:
        return str(
            conn.execute("INSERT INTO jobs(kind,input) VALUES(%s,%s) RETURNING id", (kind, Jsonb(data))).fetchone()[0]
        )


def test_competing_claims_progress_and_no_held_transaction(tmp_path, monkeypatch) -> None:
    jid = enqueue({"acceptance": "session4-competing-claims"})
    barrier = threading.Barrier(2)

    def compete() -> dict | None:
        barrier.wait()
        return jobs.claim(jid)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(compete) for _ in range(2)]
        claimed = [future.result(timeout=30) for future in futures]
    assert sum(item is not None for item in claimed) == 1
    job = next(item for item in claimed if item is not None)
    jobs.progress(jid, 0.4)
    jobs.progress(jid, 0.2)
    with db.connect() as conn:
        row = conn.execute("SELECT status,progress,updated_at>=created_at FROM jobs WHERE id=%s", (jid,)).fetchone()
        assert row[0] == "running" and row[1] == pytest.approx(0.4) and row[2]

    def processing(data: dict, root: object, update: object, timings: dict) -> dict:
        # An independent NOWAIT row lock during processing proves claim's transaction ended.
        with db.connect() as conn:
            conn.execute("SELECT id FROM jobs WHERE id=%s FOR UPDATE NOWAIT", (jid,)).fetchone()
        raise ValueError("deliberate acceptance failure after released claim")

    monkeypatch.setattr(handlers, "stems_job", processing)
    main.run_job(job, tmp_path)
    with db.connect() as conn:
        row = conn.execute("SELECT status,progress,output,error FROM jobs WHERE id=%s", (jid,)).fetchone()
    assert row[0] == "error" and row[1] == pytest.approx(0.4) and row[2] is None
    assert "deliberate acceptance failure" in row[3]
    print(
        json.dumps(
            {
                "competing_job": jid,
                "claims": 1,
                "progress_visible": True,
                "claim_lock_released_during_processing": True,
                "terminal": row[0],
            }
        )
    )


def test_skip_locked_and_session_lock_has_no_transaction() -> None:
    jid = enqueue({"acceptance": "session4-skip-locked"})
    with db.connect() as conn:
        conn.execute("SELECT id FROM jobs WHERE id=%s FOR UPDATE", (jid,)).fetchone()
        assert jobs.claim(jid) is None
    assert jobs.claim(jid) is not None
    jobs.terminate(jid, error="deliberate acceptance job: skip-locked verified")
    with jobs.track_lock("imp_session4lock"):
        with db.connect() as conn:
            rows = conn.execute(
                """SELECT a.xact_start FROM pg_locks l JOIN pg_stat_activity a ON a.pid=l.pid
                   WHERE l.locktype='advisory' AND l.granted
                     AND a.query LIKE 'SELECT pg_advisory_lock%'"""
            ).fetchall()
        assert rows and all(row[0] is None for row in rows)
    print(json.dumps({"skip_locked_job": jid, "skip_locked": True, "session_lock_without_transaction": True}))


@pytest.mark.parametrize(
    "kind,data",
    [
        ("stems", {"track_id": "fs_166649", "start_s": 0, "end_s": 61, "model": "htdemucs"}),
        ("stems", {"track_id": "fs_166649", "start_s": 10, "end_s": 9, "model": "htdemucs"}),
        ("analyze", {"track_id": "imp_invalid", "path": "imports/other/original.wav"}),
    ],
)
def test_invalid_jobs_reach_error(kind: str, data: dict, tmp_path: object) -> None:
    jid = enqueue(data, kind)
    job = jobs.claim(jid)
    assert job is not None
    main.run_job(job, tmp_path)
    with db.connect() as conn:
        row = conn.execute("SELECT status,output,error FROM jobs WHERE id=%s", (jid,)).fetchone()
    assert row[0] == "error" and row[1] is None and row[2].startswith("ValueError:")
    print(json.dumps({"invalid_job": jid, "kind": kind, "terminal": row[0], "error": row[2]}))
