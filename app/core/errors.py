"""Stable public error codes and request correlation.

Every error response carries a machine-readable `code` (stable across
releases, safe to branch client logic on) alongside the existing
human-readable `detail`, and a `request_id` that also appears on the
`X-Request-Id` response header — so a user reporting "I got a 500" can
hand over one ID that finds the exact matching server-side log line,
without the response itself ever containing internal exception details.
"""

import uuid

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.logging_config import get_logger

logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-Id"

# Stable, status-code-derived codes. Deliberately coarse (one per HTTP
# status actually used by this API) rather than one bespoke code per
# endpoint — enough for a client to branch on ("is this a conflict I
# should retry past, or a validation error I should fix"), without
# committing to a code taxonomy finer than the API actually distinguishes.
_STATUS_CODES: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    502: "UPSTREAM_ERROR",
    500: "INTERNAL_ERROR",
}


def _code_for_status(status_code: int) -> str:
    return _STATUS_CODES.get(status_code, f"HTTP_{status_code}")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException):
        request_id = _request_id(request)
        headers = dict(exc.headers or {})
        headers[REQUEST_ID_HEADER] = request_id
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "code": _code_for_status(exc.status_code),
                "request_id": request_id,
            },
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        request_id = _request_id(request)
        return JSONResponse(
            status_code=422,
            content={
                "detail": jsonable_encoder(exc.errors(), exclude={"input"}),
                "code": _code_for_status(422),
                "request_id": request_id,
            },
            headers={REQUEST_ID_HEADER: request_id},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(request: Request, exc: Exception):
        request_id = _request_id(request)
        # The public response never includes exception details — only the
        # request_id, which is what actually correlates to the full
        # traceback logged here, server-side only.
        logger.error(
            "unhandled exception",
            extra={
                "request_id": request_id,
                "path": request.url.path,
                "method": request.method,
                "exception_type": type(exc).__name__,
            },
            exc_info=exc,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "code": "INTERNAL_ERROR",
                "request_id": request_id,
            },
            headers={REQUEST_ID_HEADER: request_id},
        )
