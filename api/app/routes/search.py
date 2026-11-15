from typing import Annotated

from fastapi import APIRouter, Depends, Request
from psycopg_pool import ConnectionPool

from app.core.db import get_pool
from app.core.errors import upstream_error
from app.core.search import run_search
from app.models.api import SearchRequest, SearchResponse

router = APIRouter()


@router.post("/search", response_model=SearchResponse)
def search(req: SearchRequest, request: Request, pool: Annotated[ConnectionPool, Depends(get_pool)]) -> SearchResponse:
    # Sync handler: FastAPI runs it in the threadpool, so CLAP and the DB call don't block the event loop.
    if not request.app.state.clap_ready:
        raise upstream_error("the search model is not loaded (CLAP warm-up failed at startup)")
    state = request.app.state
    return run_search(req, pool, state.settings, getattr(state, "gemini", None), getattr(state, "freesound", None))
