"""Stems requests and job polling (CONTRACT §3 `jobs`/`stems`, §6 `POST /tracks/{id}/stems`, `GET /jobs/{id}`).

The API never separates audio itself: it returns stems that already cover the requested range, or enqueues a
`stems` job for WS1's worker (which claims jobs with `for update skip locked`).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from app.core.errors import ApiException, bad_request, not_found
from app.models.api import AnalyzeJobOutput, Job, Stem, StemsJobOutput, StemsRequest, StemsResponse
from common.storage import public_url

log = logging.getLogger("app.jobs")

MAX_STEM_RANGE_S = 60.0
EPS_S = 0.01  # coverage slack: stored ranges are `real`, requests are float64 (never applied to the 60 s limit)
RANGE_DECIMALS = 6
STEM_ORDER = ("vocals", "drums", "bass", "other", "guitar", "piano")
MODEL_STEMS: dict[str, frozenset[str]] = {
    "htdemucs": frozenset(STEM_ORDER[:4]),
    "htdemucs_6s": frozenset(STEM_ORDER),
}


def check_range(req: StemsRequest, duration_s: float | None = None) -> tuple[float, float]:
    """Validated (start_s, end_s). The end is clamped to the track length (players overshoot by a few ms)."""
    start, end = req.start_s, req.end_s
    if start < 0:
        raise bad_request("start_s must be >= 0")
    if end <= start:
        raise bad_request("end_s must be greater than start_s")
    # Strict (CONTRACT §5: "> 60 s" is rejected), checked on the request before any clamping or coverage slack.
    # Rounding to the microsecond only absorbs float64 noise, so 10.1..70.1 passes and 0..60.005 doesn't.
    if round(end - start, RANGE_DECIMALS) > MAX_STEM_RANGE_S:
        raise ApiException("range_too_long", f"stem ranges are limited to {MAX_STEM_RANGE_S:.0f} s")
    if duration_s is not None and duration_s > 0:
        if start >= duration_s:
            raise bad_request(f"start_s is past the end of the track ({duration_s:.1f} s)")
        end = min(end, duration_s)
    return start, end


def _stem(row: dict[str, Any]) -> Stem:
    return Stem(
        track_id=row["track_id"],
        stem=row["stem"],
        url=public_url(row["path"]),
        range_start_s=row["range_start_s"],
        range_end_s=row["range_end_s"],
        model=row["model"],
    )


def pick_covering(rows: list[dict[str, Any]], model: str) -> list[Stem] | None:
    """The narrowest stored range that has every stem of `model`, as Stems in canonical order, else None.

    `rows` are stems rows of one track and model whose range already covers the request.
    """
    groups: dict[tuple[float, float], dict[str, dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((row["range_start_s"], row["range_end_s"]), {})[row["stem"]] = row
    complete = [(rng, g) for rng, g in groups.items() if MODEL_STEMS[model] <= g.keys()]
    if not complete:
        return None
    (_, group) = min(complete, key=lambda item: (item[0][1] - item[0][0], item[0][0]))
    return [_stem(group[name]) for name in STEM_ORDER if name in group]


def request_stems(conn: psycopg.Connection, track_id: str, req: StemsRequest) -> StemsResponse:
    """Existing covering stems, an identical/covering job already queued or running, or a new `stems` job."""
    check_range(req)  # cheap checks before any SQL
    with conn.cursor(row_factory=dict_row) as cur:
        track = cur.execute("select duration_s from tracks where id = %s", (track_id,)).fetchone()
        if track is None:
            # Unstored `fs_*` fallback tracks were stored by `fallback.store_track` in the route before this.
            raise not_found(f"track {track_id} not found")
        start, end = check_range(req, track["duration_s"])

        rows = cur.execute(
            "select track_id, stem, path, range_start_s, range_end_s, model from stems"
            " where track_id = %s and model = %s and range_start_s <= %s and range_end_s >= %s",
            (track_id, req.model, start + EPS_S, end - EPS_S),
        ).fetchall()
        stems = pick_covering(rows, req.model)
        if stems is not None:
            return StemsResponse(stems=stems)

        # Serialize enqueues per track so two clicks don't create two jobs (lock ends with the transaction).
        cur.execute("select pg_advisory_xact_lock(hashtext('stems:' || %s))", (track_id,))
        job = cur.execute(
            "select id from jobs where kind = 'stems' and status in ('queued', 'running')"
            " and input->>'track_id' = %s and input->>'model' = %s"
            " and (input->>'start_s')::float8 <= %s and (input->>'end_s')::float8 >= %s"
            " order by created_at limit 1",
            (track_id, req.model, start + EPS_S, end - EPS_S),
        ).fetchone()
        if job is None:
            payload = {"track_id": track_id, "start_s": start, "end_s": end, "model": req.model}
            job = cur.execute(
                "insert into jobs (kind, input) values ('stems', %s) returning id", (Jsonb(payload),)
            ).fetchone()
            log.info("stems job %s queued for %s %.2f-%.2f (%s)", job["id"], track_id, start, end, req.model)
    return StemsResponse(job_id=str(job["id"]))


def _output(kind: str, raw: Any) -> StemsJobOutput | AnalyzeJobOutput:
    model = StemsJobOutput if kind == "stems" else AnalyzeJobOutput
    return model.model_validate(raw)


def fetch_job(conn: psycopg.Connection, job_id: str) -> Job:
    try:
        key = uuid.UUID(job_id)
    except ValueError:
        raise not_found(f"job {job_id} not found") from None
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute("select id, kind, status, progress, output, error from jobs where id = %s", (key,)).fetchone()
    if row is None:
        raise not_found(f"job {job_id} not found")

    status, error, output = row["status"], row["error"], None
    if row["output"] is not None:
        try:
            output = _output(row["kind"], row["output"])
        except ValidationError as exc:
            # A worker bug must not break every poll with a 500; surface it as a failed job instead.
            log.warning("job %s has an invalid %s output: %s", job_id, row["kind"], exc.errors()[:3])
            status, error = "error", "the worker returned an invalid result"
    elif status == "done":
        status, error = "error", "the worker finished without a result"
    return Job(
        id=str(row["id"]),
        kind=row["kind"],
        status=status,
        progress=max(0.0, min(1.0, float(row["progress"] or 0.0))),
        output=output,
        error=error,
    )
