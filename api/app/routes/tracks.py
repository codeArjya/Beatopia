from typing import Annotated

from fastapi import APIRouter, Depends
from psycopg_pool import ConnectionPool

from app.core import tracks
from app.core.db import get_pool
from app.core.errors import not_found
from app.core.timing import stage
from app.models.api import TrackDetail

router = APIRouter()


@router.get("/tracks/{track_id}", response_model=TrackDetail)
def get_track(track_id: str, pool: Annotated[ConnectionPool, Depends(get_pool)]) -> TrackDetail:
    # Sync handler: FastAPI runs it in the threadpool, so the blocking DB call is fine.
    # TODO(T8.1): an `fs_*` id that is not stored is a Freesound fallback track, built live (CONTRACT §6).
    with stage("sql"), pool.connection() as conn:
        detail = tracks.fetch_track_detail(conn, track_id)
    if detail is None:
        raise not_found(f"track {track_id} not found")
    return detail
