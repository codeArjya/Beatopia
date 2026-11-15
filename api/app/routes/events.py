from typing import Annotated

from fastapi import APIRouter, Depends, Response
from psycopg_pool import ConnectionPool

from app.core import personalize
from app.core.db import get_pool
from app.core.errors import bad_request
from app.core.timing import stage
from app.models.api import EventRequest

router = APIRouter()


@router.post("/events", status_code=204)
def post_event(ev: EventRequest, pool: Annotated[ConnectionPool, Depends(get_pool)]) -> Response:
    if not ev.session_id.strip() or not ev.window_id.strip():
        raise bad_request("session_id and window_id are required")
    # Fallback (fs_*) picks are only recorded, never stored as tracks (CONTRACT §7.7).
    with stage("sql"), pool.connection() as conn:
        personalize.record_event(conn, ev)
    return Response(status_code=204)
