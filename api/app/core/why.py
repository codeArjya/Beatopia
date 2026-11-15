"""POST /why (CONTRACT §6, prompts P3 / P3b): one beginner-friendly note per window, cached in `notes`.

1. A cached note (from an earlier /why, or a ":meta" note from the search rerank) is returned as is, so a window
   costs at most one Gemini call.
2. A note a search is still writing in the background (rerank P2b) is waited for (≤ 8 s) and returned.
3. Otherwise the window is snapped exactly like in /search (so the excerpt is what the user hears), a ≤ 15 s MP3
   excerpt is cut (`core/excerpt.py`) and sent inline with P3. The note is stored with model "<model>:audio".
4. If the excerpt can't be cut, the text-only P3b runs on the metadata ("<model>:text").
5. Gemini degraded or failing with no cached note → 502 upstream_error (the client keeps showing no note).

Freesound fallback windows (`fs_*:mix:0`, not in `windows`) are built live from Freesound, the excerpt comes from
the Freesound preview, and the note is cached in process only (`notes.window_id` is a foreign key; T8.1).
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Any

from google.genai import types
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core import excerpt, fallback, rerank
from app.core.errors import not_found, upstream_error
from app.core.freesound import Freesound, FreesoundError, Sound
from app.core.gemini import CallBudget, Gemini, GeminiUnavailable
from app.core.rerank import trim_note
from app.core.search import audio_path
from app.core.snap import snap_window
from app.core.timing import note, stage
from app.models.api import WhyResponse
from common.storage import public_url

log = logging.getLogger("app.why")

NOTE_MAX_WORDS = 45
WHY_TEMPERATURE = 0.4
# Not on the search path, so it gets more room than planner/rerank: 12 s wall clock, one retry.
WHY_BUDGET = CallBudget(timeout_ms=12_000, attempts=2)
# Longest wait for a note a search is still writing in the background (rerank P2b, typically ≈ 1–2 s left).
PENDING_WAIT_S = 8.0

_SYSTEM_TAIL = """\
Write one note of at most 45 words that covers three things, in this order:
1) why this excerpt works as a sample ({why_basis});
2) what to chop (where the clean hits or phrases are, for example "the first chord", "each piano hit",
   "the 2-bar horn phrase");
3) one flip idea (reverse, pitch down, slice and re-order, filter, loop).
Use plain words, no jargon without explanation, no hype, and no emojis. {trust} Do not mention the license or
the score.
"""

SYSTEM_AUDIO = (
    "You are a friendly sampling mentor for producers who are just learning to sample. You will hear a short\n"
    "excerpt (up to 15 seconds) from a Creative Commons track, plus its title and auto-detected metadata.\n"
    + _SYSTEM_TAIL.format(
        why_basis="what you actually hear: the instrument, the space, the groove,\n   the texture",
        trust="Describe what you hear; if the\nmetadata disagrees with the audio, trust the audio.",
    )
)

SYSTEM_TEXT = (
    "You are a friendly sampling mentor for producers who are just learning to sample. You will get the\n"
    "title and auto-detected metadata of a short excerpt (you cannot hear it) from a Creative Commons track.\n"
    + _SYSTEM_TAIL.format(
        why_basis="the instrument, the groove, the texture the metadata suggests",
        trust="Base the note only on the metadata and keep claims modest.",
    )
)

WHY_SCHEMA: dict[str, Any] = {"type": "object", "properties": {"note": {"type": "string"}}, "required": ["note"]}

WINDOW_SQL = """
select w.id, w.track_id, w.stem, w.start_s, w.end_s, w.tags,
       t.title, t.artist, t.bpm, t.key, t.duration_s, t.beat_times, t.audio_path,
       n.text as note
from windows w
join tracks t on t.id = w.track_id
left join notes n on n.window_id = w.id
where w.id = %s
"""


def fetch_window(pool: ConnectionPool, window_id: str) -> dict[str, Any] | None:
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(WINDOW_SQL, (window_id,)).fetchone()


def store_note(pool: ConnectionPool, window_id: str, text: str, model: str) -> str:
    """Insert the note unless one exists already; return the stored note (the first writer wins)."""
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "insert into notes (window_id, text, model) values (%s, %s, %s) on conflict (window_id) do nothing",
            (window_id, text, model),
        )
        row = cur.execute("select text from notes where window_id = %s", (window_id,)).fetchone()
    return row[0] if row else text


def user_content(row: dict[str, Any], seconds: float, bars: int) -> str:
    bpm = f"{round(row['bpm'])}" if row["bpm"] else "unknown"
    tags = ", ".join(row["tags"] or []) or "none"
    return (
        f'Title: "{row["title"]}" by {row["artist"] or "unknown artist"}\n'
        f"Stem: {row['stem']}   Tempo: {bpm} BPM   Key: {row['key'] or 'unknown'}\n"
        f"Tags: {tags}\n"
        f"Excerpt length: {seconds:.1f} s ({bars} bars)"
    )


def excerpt_range(row: dict[str, Any]) -> tuple[float, float, int]:
    """(start_s, seconds, bars) of the window as /search serves it, capped at 15 s."""
    bpm = float(row["bpm"]) if row["bpm"] else None
    snapped = snap_window(
        float(row["start_s"]),
        float(row["end_s"]),
        bpm=bpm,
        beat_times=row["beat_times"] or [],
        duration_s=float(row["duration_s"]),
    )
    return snapped.start_s, min(snapped.end_s - snapped.start_s, excerpt.MAX_EXCERPT_S), snapped.bars


def generate(row: dict[str, Any], gemini: Gemini, audio_url: str | None = None) -> tuple[str, str]:
    """(note, source) with source "audio" or "text". Raises GeminiUnavailable.

    `audio_url` overrides the bucket URL (fallback windows: a local copy of the Freesound preview, or its URL,
    host-checked in `freesound`).
    """
    start_s, seconds, bars = excerpt_range(row)
    text = user_content(row, seconds, bars)
    url = audio_url or public_url(audio_path(row["track_id"], row["stem"], row["audio_path"]))
    try:
        with stage("excerpt"):
            mp3 = excerpt.cut_excerpt(url, start_s, seconds)
    except excerpt.ExcerptError as exc:
        log.warning("why %s: no excerpt (%s), using the text-only prompt", row["id"], exc)
        mp3 = None

    if mp3 is not None:
        system, source = SYSTEM_AUDIO, "audio"
        contents: Any = [types.Part.from_bytes(data=mp3, mime_type="audio/mp3"), types.Part.from_text(text=text)]
        note(excerpt_kb=round(len(mp3) / 1024))
    else:
        system, source, contents = SYSTEM_TEXT, "text", text

    with stage("why"):
        raw = gemini.generate_json(
            system=system,
            contents=contents,
            schema=WHY_SCHEMA,
            temperature=WHY_TEMPERATURE,
            budget=WHY_BUDGET,
            what=f"why:{source}",
        )
    value = raw.get("note")
    if not isinstance(value, str) or not value.strip():
        raise GeminiUnavailable("gemini why: empty note")
    return trim_note(value, NOTE_MAX_WORDS), source


def fallback_row(sound: Sound) -> dict[str, Any]:
    """A fallback window in the shape of `WINDOW_SQL`'s row (no bpm, key or beats: Freesound doesn't have them)."""
    return {
        "id": sound.window_id,
        "track_id": sound.track_id,
        "stem": "mix",
        "start_s": 0.0,
        "end_s": sound.window_end_s,
        "tags": list(sound.tags),
        "title": sound.name,
        "artist": sound.username,
        "bpm": None,
        "key": None,
        "duration_s": sound.duration_s,
        "beat_times": [],
        "audio_path": None,
        "note": None,
    }


def _require_gemini(gemini: Gemini | None) -> Gemini:
    if gemini is None or not gemini.available():
        reason = gemini.degraded_reason() if gemini is not None else "no Gemini client"
        note(why_source="unavailable")
        raise upstream_error(f"notes are unavailable right now ({reason})")
    return gemini


def _generate(row: dict[str, Any], gemini: Gemini, audio_url: str | None = None) -> tuple[str, str]:
    try:
        return generate(row, gemini, audio_url)
    except GeminiUnavailable as exc:
        note(why_source="failed")
        raise upstream_error(f"could not write a note right now ({exc})") from exc


def run_fallback_why(window_id: str, gemini: Gemini | None, freesound: Freesound | None) -> WhyResponse:
    """A Freesound fallback window (not in `windows`): note cached in process only (CONTRACT §6)."""
    with stage("freesound"):
        sound = fallback.live_sound(freesound, window_id)
    if sound is None:
        raise not_found(f"window {window_id} not found")
    cached = fallback.notes.get(window_id)
    if cached:
        note(why_source="cache:memory")
        return WhyResponse(window_id=window_id, note=cached)
    g = _require_gemini(gemini)
    assert freesound is not None  # live_sound found the sound
    # ffmpeg seeking over HTTP on Freesound's CDN took 7+ s (vs ~1 s on our bucket); previews are ≤ 30 s
    # (≈ 0.5 MB), so fetch the whole file over the keep-alive client and cut locally. A failed fetch → P3b.
    fd, local = tempfile.mkstemp(prefix="beatopia-why-", suffix=".mp3")
    os.close(fd)
    try:
        try:
            with stage("preview"):
                freesound.download_preview(sound, local)
            source_url = local
        except FreesoundError as exc:
            log.warning("why %s: preview download failed (%s), ffmpeg will try the URL", window_id, exc)
            source_url = sound.preview_url
        text, source = _generate(fallback_row(sound), g, source_url)
    finally:
        os.unlink(local)
    fallback.notes.put(window_id, text)
    note(why_source=f"{source}:fallback")
    return WhyResponse(window_id=window_id, note=text)


def run_why(
    window_id: str, pool: ConnectionPool, gemini: Gemini | None, freesound: Freesound | None = None
) -> WhyResponse:
    with stage("sql"):
        row = fetch_window(pool, window_id)
    if row is None:
        return run_fallback_why(window_id, gemini, freesound)
    if row["note"]:
        note(why_source="cache")
        return WhyResponse(window_id=window_id, note=row["note"])
    with stage("pending"):  # a search's background notes call (P2b) may be writing this one right now
        waited = rerank.pending.wait(window_id, PENDING_WAIT_S)
    if waited:
        note(why_source="rerank")
        return WhyResponse(window_id=window_id, note=waited)

    text, source = _generate(row, _require_gemini(gemini))

    with stage("sql"):
        stored = store_note(pool, window_id, text, f"{gemini.model}:{source}")
    note(why_source=source)
    return WhyResponse(window_id=window_id, note=stored)
