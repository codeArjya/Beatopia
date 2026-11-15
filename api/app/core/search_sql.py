"""Candidate windows for a SearchPlan (CONTRACT §7.3): hard filters in SQL, ordered by CLAP cosine distance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import psycopg
from psycopg.rows import dict_row

from app.models.api import SearchPlan

CANDIDATE_LIMIT = 60
RELAX_BELOW = 10  # if must_tags ⊆ tags returns fewer rows than this, require ≥ 1 overlap instead

_TRACK_FIELDS = (
    "title",
    "artist",
    "source",
    "source_url",
    "license",
    "attribution",
    "duration_s",
    "bpm",
    "key",
    "is_hero",
    "audio_path",
)

_SELECT = """
select w.id as window_id, w.track_id, w.stem, w.start_s, w.end_s, w.tags, w.loopability, w.density,
       (w.embedding <=> %(q)s) as distance, n.text as why,
       t.title, t.artist, t.source, t.source_url, t.license, t.attribution, t.duration_s, t.bpm, t.key,
       t.is_hero, t.audio_path, t.beat_times
from windows w
join tracks t on t.id = w.track_id
left join notes n on n.window_id = w.id
where {where}
order by distance, w.id
limit %(limit)s
"""


@dataclass(frozen=True)
class Candidate:
    window_id: str
    track_id: str
    stem: str
    start_s: float
    end_s: float
    tags: tuple[str, ...]
    loopability: float
    density: float
    distance: float
    why: str | None
    track: dict[str, Any]  # tracks row: id, _TRACK_FIELDS, beat_times

    @property
    def bpm(self) -> float | None:
        bpm = self.track["bpm"]
        return float(bpm) if bpm is not None else None


def where_clause(plan: SearchPlan, *, relax: bool) -> tuple[str, dict[str, Any]]:
    """The §7.3 filters. Only static SQL fragments; every value goes through a parameter."""
    clauses = ["t.source <> 'import'"]  # imported tracks are private (CONTRACT §6)
    params: dict[str, Any] = {}
    if plan.must_tags:
        clauses.append("w.tags && %(must)s" if relax else "w.tags @> %(must)s")
        params["must"] = list(plan.must_tags)
    if plan.exclude_tags:
        clauses.append("not (w.tags && %(exclude)s)")
        params["exclude"] = list(plan.exclude_tags)
    if plan.bpm_range is not None:
        lo, hi = sorted(plan.bpm_range)
        # Null bpm passes (scored with bpm_fit = 0.5, §7.4); half and double time also match.
        clauses.append(
            "(t.bpm is null or t.bpm between %(bpm_lo)s and %(bpm_hi)s"
            " or t.bpm * 2 between %(bpm_lo)s and %(bpm_hi)s or t.bpm / 2 between %(bpm_lo)s and %(bpm_hi)s)"
        )
        params |= {"bpm_lo": lo, "bpm_hi": hi}
    if plan.key:
        clauses.append("t.key = %(key)s")
        params["key"] = plan.key
    if plan.stems_wanted:
        clauses.append("w.stem = any(%(stems)s)")
        params["stems"] = list(plan.stems_wanted)
    return " and ".join(clauses), params


def _candidate(r: dict[str, Any]) -> Candidate:
    track = {k: r[k] for k in _TRACK_FIELDS}
    track["id"] = r["track_id"]
    track["beat_times"] = [float(b) for b in r["beat_times"] or []]
    return Candidate(
        window_id=r["window_id"],
        track_id=r["track_id"],
        stem=r["stem"],
        start_s=float(r["start_s"]),
        end_s=float(r["end_s"]),
        tags=tuple(r["tags"] or ()),
        loopability=float(r["loopability"]),
        density=float(r["density"]),
        distance=float(r["distance"]),
        why=r["why"],
        track=track,
    )


def _query(conn: psycopg.Connection, plan: SearchPlan, q: np.ndarray, limit: int, relax: bool) -> list[Candidate]:
    where, params = where_clause(plan, relax=relax)
    sql = _SELECT.format(where=where)
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, {**params, "q": q, "limit": limit}).fetchall()  # type: ignore[call-overload]
    return [_candidate(r) for r in rows]


def fetch_candidates(
    conn: psycopg.Connection, plan: SearchPlan, q: np.ndarray, limit: int = CANDIDATE_LIMIT
) -> tuple[list[Candidate], bool]:
    """Up to `limit` nearest windows passing the filters, and whether must_tags had to be relaxed to an overlap."""
    q = np.asarray(q, dtype=np.float32)
    rows = _query(conn, plan, q, limit, relax=False)
    if plan.must_tags and len(rows) < RELAX_BELOW:
        return _query(conn, plan, q, limit, relax=True), True
    return rows, False
