from typing import Annotated

from fastapi import APIRouter, Depends
from psycopg_pool import ConnectionPool

from app.core import jobs
from app.core.db import get_pool
from app.core.timing import stage
from app.models.api import Job, StemsRequest, StemsResponse

router = APIRouter()


@router.post("/tracks/{track_id}/stems", response_model=StemsResponse, response_model_exclude_none=False)
def request_stems(
    track_id: str, req: StemsRequest, pool: Annotated[ConnectionPool, Depends(get_pool)]
) -> StemsResponse:
    jobs.check_range(req)  # 400/range_too_long without touching the DB
    with stage("sql"), pool.connection() as conn:
        return jobs.request_stems(conn, track_id, req)


@router.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: str, pool: Annotated[ConnectionPool, Depends(get_pool)]) -> Job:
    with stage("sql"), pool.connection() as conn:
        return jobs.fetch_job(conn, job_id)
