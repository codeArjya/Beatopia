"""POST /search pipeline (CONTRACT §7): plan → CLAP → SQL → score → rerank + notes → snap → Result.

Gemini planner + plan_cache (T4.1), Gemini rerank + notes (T4.2). No Freesound fallback yet (T8.1).
"""

from __future__ import annotations

import secrets

from psycopg_pool import ConnectionPool

from app.core import embed, planner, rerank, search_sql
from app.core.errors import bad_request
from app.core.gemini import Gemini
from app.core.scoring import Scored, rank
from app.core.settings import Settings
from app.core.snap import snap_window
from app.core.timing import note, stage
from app.core.tracks import track_lite
from app.models.api import Result, SearchRequest, SearchResponse
from common.storage import public_url

SCORE_DECIMALS = 3


def new_query_id() -> str:
    return f"q_{secrets.token_hex(4)}"


def audio_path(track_id: str, stem: str, mix_path: str) -> str:
    """mix → the track's mix.mp3; a stem window → the full-length pre-separated stem (CONTRACT §2)."""
    return mix_path if stem == "mix" else f"tracks/{track_id}/stems/{stem}.mp3"


def to_result(s: Scored, why: str | None = None) -> Result:
    c = s.candidate
    t = c.track
    snapped = snap_window(c.start_s, c.end_s, bpm=c.bpm, beat_times=t["beat_times"], duration_s=float(t["duration_s"]))
    return Result(
        window_id=c.window_id,
        track=track_lite(t),
        stem=c.stem,  # type: ignore[arg-type]  # DB check: stem is a StemName
        audio_url=public_url(audio_path(c.track_id, c.stem, t["audio_path"])),
        start_s=snapped.start_s,
        end_s=snapped.end_s,
        bars=snapped.bars,
        tags=list(c.tags),
        score=round(s.score, SCORE_DECIMALS),
        why=why if why is not None else c.why,
    )


def run_search(
    req: SearchRequest, pool: ConnectionPool, settings: Settings, gemini: Gemini | None = None
) -> SearchResponse:
    text = planner.normalize_text(req.text)
    chips = planner.resolve_chips(req.chips, settings.vocab_path)
    if text is None and not chips:
        raise bad_request("send search text or at least one chip")

    with stage("plan"):
        outcome = planner.make_plan(text, chips, req.chips, pool=pool, gemini=gemini, vocab_path=settings.vocab_path)
    plan = outcome.plan
    with stage("embed"):
        q = embed.embed_query(plan.clap_text)
    with stage("sql"), pool.connection() as conn:
        candidates, relaxed = search_sql.fetch_candidates(conn, plan, q)
    with stage("score"):
        ranked = rank(candidates, plan)
    with stage("rerank"):
        rr = rerank.rerank(text or planner.chip_caption(chips), chips, ranked, req.limit, gemini=gemini, pool=pool)
    results = [to_result(s, rr.notes.get(s.candidate.window_id)) for s in rr.ordered]
    note(
        plan_source=outcome.source,
        plan_cached=outcome.cached,
        relaxed=relaxed,
        candidates=len(candidates),
        n=len(results),
        rerank=rr.status,
        new_notes=len(rr.new_notes),
        fallback=False,
    )
    return SearchResponse(query_id=new_query_id(), plan=plan, results=results, fallback_used=False)
