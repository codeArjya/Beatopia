"""Error responses. Every non-2xx body is {"error": ApiError} (CONTRACT §5)."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.models.api import ApiError

log = logging.getLogger("app.errors")

ErrorCode = Literal[
    "not_found",
    "bad_request",
    "range_too_long",
    "clip_is_sliced",
    "upload_too_large",
    "unsupported_format",
    "upstream_error",
    "rate_limited",
    "internal_error",  # unhandled server bug; see docs/proposals/WS2-internal-error-code.md
]

STATUS: dict[ErrorCode, int] = {
    "not_found": 404,
    "bad_request": 400,
    "range_too_long": 400,
    "clip_is_sliced": 400,
    "upload_too_large": 413,
    "unsupported_format": 415,
    "upstream_error": 502,
    "rate_limited": 429,
    "internal_error": 500,
}

_HTTP_CODES: dict[int, ErrorCode] = {
    404: "not_found",
    413: "upload_too_large",
    415: "unsupported_format",
    429: "rate_limited",
}


class ApiException(Exception):
    def __init__(self, code: ErrorCode, message: str, status: int | None = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code: ErrorCode = code
        self.message = message
        self.status = status if status is not None else STATUS[code]


def not_found(message: str) -> ApiException:
    return ApiException("not_found", message)


def bad_request(message: str) -> ApiException:
    return ApiException("bad_request", message)


def upstream_error(message: str) -> ApiException:
    return ApiException("upstream_error", message)


def rate_limited(message: str = "too many requests, slow down") -> ApiException:
    return ApiException("rate_limited", message)


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": ApiError(code=code, message=message).model_dump()})


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiException)
    async def _api(_: Request, exc: ApiException) -> JSONResponse:
        return error_response(exc.status, exc.code, exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "bad_request")
        return error_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        message = "; ".join(_describe(e) for e in exc.errors()) or "invalid request"
        return error_response(400, "bad_request", message)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return error_response(500, "internal_error", "something went wrong on the server")


def _describe(err: dict[str, object]) -> str:
    loc = ".".join(str(p) for p in err.get("loc", ()) if p != "body")  # type: ignore[union-attr]
    msg = str(err.get("msg"))
    return f"{loc}: {msg}" if loc else msg
