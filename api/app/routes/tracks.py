from typing import Annotated

from fastapi import APIRouter, Depends, Request
from psycopg_pool import ConnectionPool

from app.core import fallback, tracks
from app.core.db import get_pool
from app.core.errors import not_found
from app.core.timing import note, stage
from app.models.api import TrackDetail

router = APIRouter()


@router.get("/tracks/{track_id}", response_model=TrackDetail)
def get_track(track_id: str, request: Request, pool: Annotated[ConnectionPool, Depends(get_pool)]) -> TrackDetail:
    # Sync handler: FastAPI runs it in the threadpool, so the blocking DB call is fine.
    with stage("sql"), pool.connection() as conn:
        detail = tracks.fetch_track_detail(conn, track_id)
    if detail is not None:
        return detail
    # An `fs_*` id that is not stored is a Freesound fallback track, built live (CONTRACT §6).
    with stage("freesound"):
        sound = fallback.live_sound(getattr(request.app.state, "freesound", None), track_id)
    if sound is None:
        raise not_found(f"track {track_id} not found")
    note(fallback_track=True)
    return fallback.track_detail(sound)
