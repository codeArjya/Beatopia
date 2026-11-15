"""POST /search pipeline (CONTRACT §7): plan → CLAP → SQL → score → rerank + notes → snap → Result.

Gemini planner + plan_cache (T4.1), Gemini rerank + notes (T4.2), Freesound fallback (T8.1, proposal C10).
"""

from __future__ import annotations

import logging
import secrets
import time

from psycopg_pool import ConnectionPool

from app.core import embed, fallback, personalize, planner, rerank, search_sql
from app.core.errors import bad_request
from app.core.freesound import Freesound, FreesoundError, Sound
from app.core.gemini import Gemini
from app.core.scoring import Scored, rank
from app.core.settings import Settings
from app.core.snap import piece_bounds, snap_window
from app.core.timing import note, stage
from app.core.tracks import track_lite
from app.models.api import Chip, Result, SearchRequest, SearchResponse
from common.storage import public_url

log = logging.getLogger("app.search")

SCORE_DECIMALS = 3
# How long after the request started a search waits for background rerank notes (P2b) before answering without
# them (T11.1: keeps the cold path under the 3 s p50 target; late notes land in the cache for /why).
NOTES_DEADLINE_S = 2.6


def new_query_id() -> str:
    return f"q_{secrets.token_hex(4)}"


def audio_path(track_id: str, stem: str, mix_path: str) -> str:
    """mix → the track's mix.mp3; a stem window → the full-length pre-separated stem (CONTRACT §2)."""
    return mix_path if stem == "mix" else f"tracks/{track_id}/stems/{stem}.mp3"


def to_result(s: Scored, why: str | None = None) -> Result:
    c = s.candidate
    t = c.track
    duration = float(t["duration_s"])
    piece = piece_bounds(c.start_s, c.end_s, duration_s=duration, source=t["source"])
    snapped = snap_window(c.start_s, c.end_s, bpm=c.bpm, beat_times=t["beat_times"], duration_s=duration, piece=piece)
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
    req: SearchRequest,
    pool: ConnectionPool,
    settings: Settings,
    gemini: Gemini | None = None,
    freesound: Freesound | None = None,
) -> SearchResponse:
    started = time.monotonic()
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
        q, feedback = personalize.personalize(conn, req.session_id, q)
        candidates, relaxed = search_sql.fetch_candidates(conn, plan, q)
    with stage("score"):
        ranked = rank(candidates, plan)

    reason = fallback.trigger(candidates, outcome.missing_sounds)
    sounds = fallback_sounds(reason, text, chips, outcome.missing_sounds, req.limit, freesound)
    if sounds is not None:
        # The library has no good match: Freesound results lead, library results (score order, cached notes)
        # fill the rest. No rerank: it would cost ~3 s to order filler.
        library = [to_result(s) for s in ranked[: req.limit]]
        results = fallback.merge(sounds, library, req.limit)
        status, new_notes = "skipped:fallback", 0
    else:
        with stage("rerank"):
            rr = rerank.rerank(
                text or planner.chip_caption(chips),
                chips,
                ranked,
                req.limit,
                gemini=gemini,
                pool=pool,
                notes_until=started + NOTES_DEADLINE_S,
            )
        results = [to_result(s, rr.notes.get(s.candidate.window_id)) for s in rr.ordered]
        status, new_notes = rr.status, len(rr.new_notes)
        note(notes_pending=rr.notes_pending)
    note(
        plan_source=outcome.source,
        plan_cached=outcome.cached,
        relaxed=relaxed,
        picks=feedback.picked,
        skips=feedback.skipped,
        candidates=len(candidates),
        n=len(results),
        rerank=status,
        new_notes=new_notes,
        fallback=reason if sounds is not None else False,
    )
    return SearchResponse(query_id=new_query_id(), plan=plan, results=results, fallback_used=sounds is not None)


def fallback_sounds(
    reason: fallback.Reason | None,
    text: str | None,
    chips: list[Chip],
    missing_sounds: tuple[str, ...],
    limit: int,
    freesound: Freesound | None,
) -> list[Sound] | None:
    """Freesound sounds when the fallback triggers and Freesound answers (possibly []), else None."""
    if reason is None:
        return None
    if freesound is None:
        note(fallback_skipped=f"{reason}:no_key")
        return None
    query = fallback.query_for(reason, text, chips, missing_sounds)
    if not query:
        note(fallback_skipped=f"{reason}:no_query")
        return None
    try:
        with stage("freesound"):
            sounds = freesound.search(query, limit)
    except FreesoundError as exc:
        log.warning("fallback (%s) failed: %s", reason, exc)
        note(fallback_skipped=f"{reason}:error")
        return None
    note(fs_n=len(sounds), missing_sounds=list(missing_sounds))
    return sounds
