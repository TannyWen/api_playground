"""A single, structured error shape for the /v1 surface.

Bare {"detail": "..."} tells a caller almost nothing. This envelope carries a
code, a request_id, and a retryable flag, because "parse the error, log the
request_id, decide whether to retry" is the skill the workshop is teaching.

Handlers are registered app-wide (FastAPI has no per-router exception handlers)
but short-circuit to FastAPI's own handlers for any path outside /v1 -- which
today means only FastAPI's own routes (/docs, /openapi.json, /redoc).
"""
import logging

from fastapi import FastAPI, Request
from fastapi.exception_handlers import (
    http_exception_handler as default_http_handler,
)
from fastapi.exception_handlers import (
    request_validation_exception_handler as default_validation_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.v1.middleware import get_request_id

log = logging.getLogger("app.v1")

V1_PREFIX = "/v1"

# Retry on transient failures only. Participants write their own should_retry()
# in the error-handling block, then discover the server was telling them all
# along via this flag.
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}

# status -> stable machine-readable code
CODE_BY_STATUS = {
    400: "invalid_cursor",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "invalid_request",
    429: "rate_limited",
    500: "internal_error",
    503: "upstream_unavailable",
}


class ApiError(Exception):
    """Raise this inside /v1 routes to produce an enveloped error directly."""

    def __init__(
        self,
        status: int,
        message: str,
        code: str | None = None,
        details: list | None = None,
        headers: dict | None = None,
    ):
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code or CODE_BY_STATUS.get(status, "error")
        self.details = details or []
        self.headers = headers or {}


def envelope(
    request: Request,
    status: int,
    message: str,
    code: str | None = None,
    details: list | None = None,
    headers: dict | None = None,
) -> JSONResponse:
    body = {
        "error": {
            "code": code or CODE_BY_STATUS.get(status, "error"),
            "message": message,
            "status": status,
            "request_id": get_request_id(request),
            "retryable": status in RETRYABLE_STATUSES,
            "details": details or [],
        }
    }
    return JSONResponse(status_code=status, content=body, headers=headers or {})


def _field_path(loc) -> str | None:
    """Turn a pydantic loc tuple into a dotted path a human can act on.

    Drops the leading "body"/"query" segment so the path matches what the caller
    actually typed, e.g. "filters.issued_from" rather than "body.filters....".
    """
    parts = [str(p) for p in loc]
    if parts and parts[0] in ("body", "query", "path", "header", "cookie"):
        parts = parts[1:]
    return ".".join(parts) or None


def install_v1_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return envelope(
            request,
            exc.status,
            exc.message,
            code=exc.code,
            details=exc.details,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        if not request.url.path.startswith(V1_PREFIX):
            return await default_validation_handler(request, exc)
        details = [
            {
                "field": _field_path(e.get("loc", ())),
                "issue": e.get("type"),
                "message": e.get("msg"),
                "input": e.get("input"),
            }
            for e in exc.errors()
        ]
        return envelope(
            request,
            422,
            "Request failed validation. Each offending field is listed in "
            "error.details, addressed by a dotted path.",
            details=details,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        if not request.url.path.startswith(V1_PREFIX):
            return await default_http_handler(request, exc)
        return envelope(
            request,
            exc.status_code,
            str(exc.detail),
            headers=dict(getattr(exc, "headers", None) or {}),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        # Re-raise outside /v1 so a 500 on a non-/v1 path (FastAPI's own routes)
        # still surfaces as a real traceback (and so
        # TestClient(raise_server_exceptions=True) keeps working).
        if not request.url.path.startswith(V1_PREFIX):
            raise exc
        log.exception("unhandled error", extra={"request_id": get_request_id(request)})
        return envelope(
            request,
            500,
            "An unexpected error occurred. Quote the request_id when reporting it.",
        )
