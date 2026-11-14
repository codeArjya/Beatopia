"""Track lookups (CONTRACT §3 tables → §5 TrackLite / TrackDetail)."""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.models.api import Stem, TrackDetail, TrackLite, Window
from common.storage import public_url

TRACK_COLUMNS = (
    "id, title, artist, source, source_url, license, attribution, duration_s, bpm, key, is_hero, audio_path, beat_times"
)


def track_lite(row: dict[str, Any]) -> TrackLite:
    return TrackLite(
        id=row["id"],
        title=row["title"],
        artist=row["artist"],
        source=row["source"],
        source_url=row["source_url"],
        license=row["license"],
        attribution=row["attribution"],
        duration_s=row["duration_s"],
        bpm=row["bpm"],
        key=row["key"],
        is_hero=row["is_hero"],
    )


def fetch_track_detail(conn: psycopg.Connection, track_id: str) -> TrackDetail | None:
    """The track with all its windows and stems, or None. Imported tracks are returned too (only by id)."""
    with conn.cursor(row_factory=dict_row) as cur:
        track = cur.execute(f"select {TRACK_COLUMNS} from tracks where id = %s", (track_id,)).fetchone()
        if track is None:
            return None
        windows = cur.execute(
            "select id, track_id, stem, start_s, end_s, tags, loopability, rms, density"
            " from windows where track_id = %s order by stem = 'mix' desc, stem, start_s",
            (track_id,),
        ).fetchall()
        stems = cur.execute(
            "select track_id, stem, path, range_start_s, range_end_s, model"
            " from stems where track_id = %s order by stem, range_start_s, range_end_s",
            (track_id,),
        ).fetchall()

    return TrackDetail(
        track=track_lite(track),
        audio_url=public_url(track["audio_path"]),
        beat_times=list(track["beat_times"] or []),
        windows=[Window(**{**w, "tags": list(w["tags"] or [])}) for w in windows],
        stems=[
            Stem(
                track_id=s["track_id"],
                stem=s["stem"],
                url=public_url(s["path"]),
                range_start_s=s["range_start_s"],
                range_end_s=s["range_end_s"],
                model=s["model"],
            )
            for s in stems
        ],
    )
