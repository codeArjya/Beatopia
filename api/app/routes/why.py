from typing import Annotated

from fastapi import APIRouter, Depends, Request
from psycopg_pool import ConnectionPool

from app.core.db import get_pool
from app.core.why import run_why
from app.models.api import WhyRequest, WhyResponse

router = APIRouter()


@router.post("/why", response_model=WhyResponse)
def why(req: WhyRequest, request: Request, pool: Annotated[ConnectionPool, Depends(get_pool)]) -> WhyResponse:
    # Sync handler: ffmpeg, Gemini and the DB all block, so FastAPI runs this in the threadpool.
    state = request.app.state
    return run_why(req.window_id, pool, getattr(state, "gemini", None), getattr(state, "freesound", None))
