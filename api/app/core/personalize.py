"""Per-session Rocchio feedback (PLAN §1 "Personalization"): q' = normalize(q + α·mean(picked) − β·mean(skipped)).

Uses `events` from the last WINDOW of this session joined to `windows.embedding` (Freesound fallback windows have
no embedding and drop out of the join). Only applies once the session has at least one pick.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import psycopg

from app.models.api import EventRequest

ALPHA = 0.3
BETA = 0.1
MAX_PER_ACTION = 20
WINDOW = "2 hours"


@dataclass(frozen=True)
class Feedback:
    picked: int
    skipped: int


def record_event(conn: psycopg.Connection, ev: EventRequest) -> None:
    conn.execute(
        "insert into events (session_id, query_id, window_id, action) values (%s, %s, %s, %s)",
        (ev.session_id, ev.query_id, ev.window_id, ev.action),
    )


def _vectors(conn: psycopg.Connection, session_id: str) -> tuple[list[np.ndarray], list[np.ndarray]]:
    rows = conn.execute(
        "select action, embedding from ("
        "  select e.action, w.embedding,"
        "         row_number() over (partition by e.action order by e.created_at desc) as n"
        "  from events e join windows w on w.id = e.window_id"
        "  where e.session_id = %s and e.action in ('pick', 'skip')"
        f"   and e.created_at > now() - interval '{WINDOW}'"
        ") recent where n <= %s",
        (session_id, MAX_PER_ACTION),
    ).fetchall()
    picked = [_array(v) for a, v in rows if a == "pick"]
    skipped = [_array(v) for a, v in rows if a == "skip"]
    return picked, skipped


def _array(v: object) -> np.ndarray:
    """pgvector's psycopg loader returns `Vector` objects (or numpy arrays, depending on the version)."""
    to_numpy = getattr(v, "to_numpy", None)
    return np.asarray(to_numpy() if callable(to_numpy) else v, dtype=np.float32)


def rocchio(q: np.ndarray, picked: list[np.ndarray], skipped: list[np.ndarray]) -> np.ndarray:
    """New L2-normalized vector; `q` itself is never modified (it may be an LRU-cached array)."""
    if not picked:
        return q
    out = q.astype(np.float32, copy=True) + ALPHA * np.mean(picked, axis=0)
    if skipped:
        out -= BETA * np.mean(skipped, axis=0)
    norm = float(np.linalg.norm(out))
    return out / norm if norm > 0 else q


def personalize(conn: psycopg.Connection, session_id: str, q: np.ndarray) -> tuple[np.ndarray, Feedback]:
    picked, skipped = _vectors(conn, session_id)
    return rocchio(q, picked, skipped), Feedback(picked=len(picked), skipped=len(skipped))
