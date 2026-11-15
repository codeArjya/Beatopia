"""Short job-table transactions; no connection is passed to inference."""

import math
from collections.abc import Iterator
from contextlib import contextmanager

from psycopg.types.json import Jsonb

from common import db


def claim(job_id: str | None = None) -> dict | None:
    with db.connect() as conn:
        row = conn.execute(
            """WITH candidate AS (
                 SELECT id FROM jobs WHERE status='queued' AND (%s::uuid IS NULL OR id=%s::uuid)
                 ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT 1
               ) UPDATE jobs j SET status='running',progress=0,output=NULL,error=NULL,updated_at=now()
                 FROM candidate c WHERE j.id=c.id RETURNING j.id,j.kind,j.input""",
            (job_id, job_id),
        ).fetchone()
    return None if row is None else {"id": str(row[0]), "kind": row[1], "input": row[2]}


def progress(job_id: str, value: float) -> None:
    if not math.isfinite(value) or not 0 <= value < 1:
        raise ValueError("Intermediate progress must be finite and in [0,1)")
    with db.connect() as conn:
        conn.execute(
            """UPDATE jobs SET progress=greatest(progress,%s),updated_at=now()
               WHERE id=%s AND status='running'""",
            (value, job_id),
        )


def terminate(job_id: str, *, output: dict | None = None, error: str | None = None) -> None:
    if (output is None) == (error is None):
        raise ValueError("Exactly one terminal result is required")
    with db.connect() as conn:
        conn.execute(
            """UPDATE jobs SET status=%s,progress=CASE WHEN %s THEN 1 ELSE progress END,
               output=%s,error=%s,updated_at=now() WHERE id=%s AND status='running'""",
            ("error" if error else "done", error is None, Jsonb(output) if output is not None else None, error, job_id),
        )


@contextmanager
def track_lock(track_id: str) -> Iterator[None]:
    # A session lock serializes duplicate jobs without an open transaction.
    # PostgreSQL releases it if the connection dies; claims remain explicitly recoverable.
    with db.connect() as conn:
        conn.autocommit = True
        conn.execute("SELECT pg_advisory_lock(hashtextextended(%s,0))", ("worker:" + track_id,))
        try:
            yield
        finally:
            conn.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", ("worker:" + track_id,))
