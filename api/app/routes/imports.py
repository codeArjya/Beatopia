import os
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from psycopg_pool import ConnectionPool

from app.core import imports
from app.core.db import get_pool
from app.core.errors import bad_request
from app.core.timing import stage
from app.models.api import ImportResponse
from common import storage

router = APIRouter()


def _store(pool: ConnectionPool, local_path: str, ext: str, track_id: str, title: str) -> str:
    original = f"imports/{track_id}/original.{ext}"
    with stage("upload"):
        storage.upload(local_path, original, imports.CONTENT_TYPES[ext])
    with stage("sql"), pool.connection() as conn:
        return imports.create_import(conn, track_id, title, original)


@router.post("/imports", response_model=ImportResponse)
async def create_import(
    request: Request,
    file: Annotated[UploadFile, File()],
    session_id: Annotated[str, Form()],
    pool: Annotated[ConnectionPool, Depends(get_pool)],
) -> ImportResponse:
    if not session_id.strip():
        raise bad_request("session_id is required")
    # Multipart overhead is small; a body far above the limit is rejected before reading it.
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > imports.MAX_UPLOAD_BYTES + 64 * 1024:
        raise imports.too_large()
    ext = imports.extension(file.filename)
    spooled = await imports.spool(file.read)
    try:
        imports.check_format(ext, spooled.head)
        track_id = imports.new_track_id()
        job_id = await run_in_threadpool(_store, pool, spooled.path, ext, track_id, imports.title_from(file.filename))
    finally:
        os.unlink(spooled.path)
    return ImportResponse(track_id=track_id, job_id=job_id)
