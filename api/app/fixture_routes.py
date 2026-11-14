"""Fixture handlers: every CONTRACT §6 endpoint answered from shared/fixtures (USE_FIXTURES=1).

In real mode, endpoints that have no real implementation yet fall back to these (see app.main).
"""

from __future__ import annotations

import json
from functools import cache
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Response, UploadFile

from app.core.errors import ApiException, bad_request, not_found
from app.core.settings import get_settings
from app.models.api import (
    ChipsResponse,
    EventRequest,
    ImportResponse,
    Job,
    SearchRequest,
    SearchResponse,
    StemsRequest,
    StemsResponse,
    TrackDetail,
    WhyRequest,
    WhyResponse,
)
from app.models.ops import AssistRequest, AssistResponse

MAX_STEM_RANGE_S = 60.0

router = APIRouter()


@cache
def fixture(name: str) -> Any:
    return json.loads((get_settings().fixtures_dir / f"{name}.json").read_text(encoding="utf-8"))


@router.get("/chips", response_model=ChipsResponse)
def chips() -> Any:
    return fixture("chips")


@router.post("/search", response_model=SearchResponse)
def search(req: SearchRequest) -> Any:
    return fixture("search")


@router.get("/tracks/{track_id}", response_model=TrackDetail)
def get_track(track_id: str) -> Any:
    return fixture("track_detail")


@router.post("/tracks/{track_id}/stems", response_model=StemsResponse, response_model_exclude_none=False)
def request_stems(track_id: str, req: StemsRequest) -> Any:
    if req.end_s <= req.start_s:
        raise bad_request("end_s must be greater than start_s")
    if req.end_s - req.start_s > MAX_STEM_RANGE_S:
        raise ApiException("range_too_long", f"stem ranges are limited to {MAX_STEM_RANGE_S:.0f} s")
    return fixture("stems_ready")


@router.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: str) -> Any:
    for name in ("job_done_stems", "job_done_analyze"):
        if fixture(name)["id"] == job_id:
            return fixture(name)
    raise not_found(f"job {job_id} not found")


@router.post("/imports", response_model=ImportResponse)
async def create_import(file: Annotated[UploadFile, File()], session_id: Annotated[str, Form()]) -> Any:
    return fixture("import")


@router.post("/why", response_model=WhyResponse)
def why(req: WhyRequest) -> Any:
    return {**fixture("why"), "window_id": req.window_id}


@router.post("/events", status_code=204)
def events(req: EventRequest) -> Response:
    return Response(status_code=204)


@router.post("/assist", response_model=AssistResponse)
def assist(req: AssistRequest) -> Any:
    return fixture("assist")
