"""FastAPI app. Bootstrap version: every CONTRACT §6 endpoint returns its shared/fixtures file.

WS2 replaces the stub bodies with real implementations (keep fixture mode behind USE_FIXTURES=1).
"""

import json
import os
from functools import cache
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.models.api import (
    ApiError,
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

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = Path(os.environ.get("FIXTURES_DIR", REPO_ROOT / "shared" / "fixtures"))
MAX_STEM_RANGE_S = 60.0


@cache
def fixture(name: str) -> Any:
    return json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))


class ApiException(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status, self.code, self.message = status, code, message


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": ApiError(code=code, message=message).model_dump()})


app = FastAPI(title="Beatopia API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("WEB_ORIGIN", "http://localhost:3000").split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ApiException)
async def _api_exception(_: Request, exc: ApiException) -> JSONResponse:
    return error_response(exc.status, exc.code, exc.message)


@app.exception_handler(StarletteHTTPException)
async def _http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "not_found" if exc.status_code == 404 else "bad_request"
    return error_response(exc.status_code, code, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def _validation_exception(_: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response(400, "bad_request", "; ".join(str(e.get("msg")) for e in exc.errors()) or "invalid request")


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/chips", response_model=ChipsResponse)
def chips() -> Any:
    return fixture("chips")


@app.post("/search", response_model=SearchResponse)
def search(req: SearchRequest) -> Any:
    return fixture("search")


@app.get("/tracks/{track_id}", response_model=TrackDetail)
def get_track(track_id: str) -> Any:
    return fixture("track_detail")


@app.post("/tracks/{track_id}/stems", response_model=StemsResponse, response_model_exclude_none=False)
def request_stems(track_id: str, req: StemsRequest) -> Any:
    if req.end_s <= req.start_s:
        raise ApiException(400, "bad_request", "end_s must be greater than start_s")
    if req.end_s - req.start_s > MAX_STEM_RANGE_S:
        raise ApiException(400, "range_too_long", f"stem ranges are limited to {MAX_STEM_RANGE_S:.0f} s")
    return fixture("stems_ready")


@app.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: str) -> Any:
    for name in ("job_done_stems", "job_done_analyze"):
        if fixture(name)["id"] == job_id:
            return fixture(name)
    raise ApiException(404, "not_found", f"job {job_id} not found")


@app.post("/imports", response_model=ImportResponse)
async def create_import(file: Annotated[UploadFile, File()], session_id: Annotated[str, Form()]) -> Any:
    return fixture("import")


@app.post("/why", response_model=WhyResponse)
def why(req: WhyRequest) -> Any:
    return fixture("why")


@app.post("/events", status_code=204)
def events(req: EventRequest) -> Response:
    return Response(status_code=204)


@app.post("/assist", response_model=AssistResponse)
def assist(req: AssistRequest) -> Any:
    return fixture("assist")
