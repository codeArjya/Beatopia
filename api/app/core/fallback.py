"""Freesound fallback (CONTRACT §7.7 as amended by proposal C10, `docs/proposals/WS2-fallback-trigger.md`).

- Trigger: fewer than 3 candidates with CLAP sim ≥ 0.30 ("weak"), or the planner reports requested sounds that
  aren't in the tag vocabulary ("gap").
- Freesound results come first (score = Freesound rank, not CLAP), library results fill the rest of `limit`.
- Fallback tracks aren't stored: `/tracks/fs_*` and `/why` build them live from Freesound, and their notes live in
  an in-process cache (`notes.window_id` is a foreign key to `windows`). The one exception is stems: the worker
  needs a `tracks` row and the audio in our bucket, so `store_track` copies the preview and inserts a minimal row.
"""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Sequence
from typing import Literal

from psycopg_pool import ConnectionPool

from app.core.errors import not_found, upstream_error
from app.core.freesound import Freesound, FreesoundError, Sound, TtlCache, sound_id
from app.core.planner import CAPTION_CATEGORIES
from app.core.scoring import similarity
from app.core.search_sql import Candidate
from app.core.snap import NOMINAL_BARS, ONE_SHOT_MAX_S, Bars
from app.models.api import Chip, Result, TrackDetail, TrackLite, Window
from common import audio, storage

log = logging.getLogger("app.fallback")

SIM_MIN = 0.30  # measured: eval queries' 3rd-best sim ≥ 0.318, sound effects ≤ 0.302 (proposal C10)
MIN_STRONG = 3
FS_SCORE_TOP = 0.5
FS_SCORE_STEP = 0.02
FS_SCORE_MIN = 0.1
NOTE_TTL_S = 24 * 3600.0
MIX_BITRATE = "192k"  # CONTRACT §2: tracks/{id}/mix.mp3 is 44.1 kHz stereo MP3 192k

Reason = Literal["weak", "gap"]

notes: TtlCache[str, str] = TtlCache(2048, NOTE_TTL_S)  # fallback window id → why note


def trigger(candidates: Sequence[Candidate], missing_sounds: Sequence[str]) -> Reason | None:
    if missing_sounds:
        return "gap"
    strong = sum(similarity(c.distance) >= SIM_MIN for c in candidates)
    return "weak" if strong < MIN_STRONG else None


def query_for(reason: Reason, text: str | None, chips: Sequence[Chip], missing_sounds: Sequence[str]) -> str:
    """What to ask Freesound. Freesound ANDs the words ("kazoo orchestra" → 0 hits, "kazoo" → 102), so a gap
    searches the first missing sound alone."""
    if reason == "gap" and missing_sounds:
        return missing_sounds[0]
    if text:
        return text
    return " ".join(c.label.lower() for c in chips if c.category in CAPTION_CATEGORIES)


def bars_for(duration_s: float) -> Bars:
    """Nominal bar count (no bpm on a fallback track): one-shots are 1 bar, everything else the nominal 4."""
    return 1 if duration_s < ONE_SHOT_MAX_S else NOMINAL_BARS


def fs_score(rank: int) -> float:
    return round(max(FS_SCORE_MIN, FS_SCORE_TOP - FS_SCORE_STEP * rank), 3)


def track_lite(sound: Sound) -> TrackLite:
    return TrackLite(
        id=sound.track_id,
        title=sound.name,
        artist=sound.username,
        source="freesound",
        source_url=sound.url,
        license=sound.license,
        attribution=sound.attribution,
        duration_s=sound.duration_s,
        bpm=None,
        key=None,
        is_hero=False,
    )


def to_result(sound: Sound, rank: int) -> Result:
    return Result(
        window_id=sound.window_id,
        track=track_lite(sound),
        stem="mix",
        audio_url=sound.preview_url,
        start_s=0.0,
        end_s=sound.window_end_s,
        bars=bars_for(sound.duration_s),
        tags=list(sound.tags),
        score=fs_score(rank),
        why=notes.get(sound.window_id),
    )


def track_detail(sound: Sound) -> TrackDetail:
    """CONTRACT §6: one `mix` window, `beat_times: []`, `stems: []`."""
    window = Window(
        id=sound.window_id,
        track_id=sound.track_id,
        stem="mix",
        start_s=0.0,
        end_s=sound.window_end_s,
        tags=list(sound.tags),
        loopability=0.0,
        rms=0.0,
        density=0.5,
    )
    return TrackDetail(track=track_lite(sound), audio_url=sound.preview_url, beat_times=[], windows=[window], stems=[])


def merge(sounds: Sequence[Sound], library: Sequence[Result], limit: int) -> list[Result]:
    """Freesound results first, then library results; at least limit // 4 library slots when there are enough.

    A sound that is already in the library results (WS1 ingested some Freesound tracks) is skipped.
    """
    in_library = {r.track.id for r in library}
    fresh = [s for s in sounds if s.track_id not in in_library]
    keep_library = min(len(library), limit // 4)
    fs = [to_result(s, i) for i, s in enumerate(fresh[: limit - keep_library])]
    return fs + list(library[: limit - len(fs)])


def live_sound(fs: Freesound | None, track_or_window_id: str) -> Sound | None:
    """The Freesound sound behind an unstored fallback id, or None (not an fs id, no client, unknown sound).
    Raises upstream_error when Freesound is down."""
    sid = sound_id(track_or_window_id)
    if sid is None or fs is None:
        return None
    try:
        return fs.sound(sid)
    except FreesoundError as exc:
        raise upstream_error(f"Freesound is not answering right now ({exc})") from exc


def store_track(pool: ConnectionPool, fs: Freesound | None, track_id: str) -> bool:
    """Before a stems request on an unstored fallback track: copy its preview to `tracks/{id}/mix.mp3` and insert a
    minimal `tracks` row (bpm/key null, no windows; CONTRACT §7.7). Returns True when it stored one.

    No-op for ids that aren't `fs_*` or are already stored. 404 for an unknown sound, 502 when Freesound or Storage
    fails. Not transactional with the stems request on purpose: the upload takes seconds and must not hold a DB
    connection; a concurrent second request just upserts the same object and hits `on conflict do nothing`.
    """
    if sound_id(track_id) is None:
        return False
    with pool.connection() as conn:
        if conn.execute("select 1 from tracks where id = %s", (track_id,)).fetchone() is not None:
            return False
    sound = live_sound(fs, track_id)
    if sound is None:
        raise not_found(f"track {track_id} not found")

    path = f"tracks/{track_id}/mix.mp3"
    with tempfile.TemporaryDirectory(prefix="beatopia-fs-") as workdir:
        preview, mix = os.path.join(workdir, "preview.mp3"), os.path.join(workdir, "mix.mp3")
        assert fs is not None  # live_sound returned a sound
        try:
            size = fs.download_preview(sound, preview)
        except FreesoundError as exc:
            raise upstream_error(f"could not fetch the Freesound preview ({exc})") from exc
        # Library audio is 44.1 kHz stereo MP3 192k (CONTRACT §2), like WS1's ingest mixes: transcode the preview
        # with the same helper instead of storing Freesound's bytes as they are (issue #13 / WS1 full report).
        try:
            audio.to_mp3(preview, mix, MIX_BITRATE)
            y, sr = audio.load_mono(mix)
            duration_s = round(len(y) / sr, 3) if sr and len(y) else sound.duration_s
        except Exception as exc:
            log.warning("fallback %s: preview transcode failed", track_id, exc_info=True)
            raise upstream_error("could not convert the Freesound preview") from exc
        try:
            storage.upload(mix, path, "audio/mpeg")
        except Exception as exc:
            log.warning("fallback %s: preview upload failed", track_id, exc_info=True)
            raise upstream_error("could not copy the Freesound preview to storage") from exc

    with pool.connection() as conn:
        conn.execute(
            "insert into tracks (id, source, source_id, source_url, title, artist, license, attribution,"
            " duration_s, audio_path) values (%s, 'freesound', %s, %s, %s, %s, %s, %s, %s, %s)"
            " on conflict (id) do nothing",
            (
                track_id,
                str(sound.id),
                sound.url,
                sound.name,
                sound.username,
                sound.license,
                sound.attribution,
                duration_s,
                path,
            ),
        )
    log.info("fallback %s stored for stems (%d KB preview)", track_id, size // 1024)
    return True
