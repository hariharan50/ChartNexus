"""Maps domain errors onto RFC 9457 problem responses.

One shape for every error the API can return, so the frontend has a single
branch to write. Unhandled exceptions are logged with a stack trace and
answered with a generic 500 — internal messages never reach the client.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from chartnexus.infrastructure.observability.request_context import current_request_id
from chartnexus.infrastructure.observability.structured_logging import get_logger
from chartnexus.shared_kernel.domain.errors import (
    AuthenticationError,
    AuthorizationError,
    ChartNexusError,
    ConcurrencyError,
    ConflictError,
    EntitlementError,
    NotFoundError,
    RateLimitError,
    StaleDataError,
    UpstreamError,
    ValidationError,
)

log = get_logger(__name__)

PROBLEM_CONTENT_TYPE = "application/problem+json"

# Spelled out rather than taken from `status`: Starlette renamed the
# constant (UNPROCESSABLE_ENTITY -> UNPROCESSABLE_CONTENT) and deprecated
# the old name, so referencing either couples us to a Starlette version.
_UNPROCESSABLE = 422

_STATUS_BY_ERROR: tuple[tuple[type[ChartNexusError], int], ...] = (
    # Most specific first — subclasses must be matched before their base.
    (EntitlementError, status.HTTP_402_PAYMENT_REQUIRED),
    (AuthorizationError, status.HTTP_403_FORBIDDEN),
    (AuthenticationError, status.HTTP_401_UNAUTHORIZED),
    (NotFoundError, status.HTTP_404_NOT_FOUND),
    (ConcurrencyError, status.HTTP_409_CONFLICT),
    (ConflictError, status.HTTP_409_CONFLICT),
    (ValidationError, _UNPROCESSABLE),
    (RateLimitError, status.HTTP_429_TOO_MANY_REQUESTS),
    (StaleDataError, status.HTTP_503_SERVICE_UNAVAILABLE),
    (UpstreamError, status.HTTP_502_BAD_GATEWAY),
)


def register_exception_handlers(app: FastAPI, *, expose_internal_detail: bool = False) -> None:
    @app.exception_handler(ChartNexusError)
    async def _domain_error(_request: Request, exc: ChartNexusError) -> JSONResponse:
        status_code = _status_for(exc)
        if status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
            log.error("domain_error", code=exc.code, error=exc.message, **exc.details)
        else:
            log.info("domain_error", code=exc.code, error=exc.message, **exc.details)

        headers: dict[str, str] = {}
        if isinstance(exc, RateLimitError) and exc.retry_after_seconds is not None:
            headers["Retry-After"] = str(int(exc.retry_after_seconds))

        return _problem(
            status_code=status_code,
            code=exc.code,
            detail=exc.message,
            extra=exc.details,
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return _problem(
            status_code=_UNPROCESSABLE,
            code="request_invalid",
            detail="The request body or parameters failed validation.",
            extra={"errors": _sanitise_validation_errors(exc.errors())},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _problem(
            status_code=exc.status_code,
            code=_code_for_status(exc.status_code),
            detail=str(exc.detail),
            headers=dict(exc.headers or {}),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            error=type(exc).__name__,
        )
        return _problem(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            detail=str(exc) if expose_internal_detail else "An unexpected error occurred.",
        )


def _status_for(exc: ChartNexusError) -> int:
    for error_type, status_code in _STATUS_BY_ERROR:
        if isinstance(exc, error_type):
            return status_code
    return status.HTTP_500_INTERNAL_SERVER_ERROR


def _code_for_status(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "unauthenticated",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        409: "conflict",
        413: "payload_too_large",
        415: "unsupported_media_type",
        429: "rate_limited",
    }.get(
        status_code,
        "internal_error"
        if status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR
        else "request_failed",
    )


def _sanitise_validation_errors(errors: Sequence[Any]) -> list[dict[str, str]]:
    """Keep the field path and reason; drop the submitted value.

    Pydantic echoes the offending input, which for a login route means the
    password ends up in the response body and in logs.
    """
    sanitised: list[dict[str, str]] = []
    for error in errors:
        location = ".".join(str(part) for part in error.get("loc", ()) if part != "body")
        sanitised.append({"field": location or "body", "reason": str(error.get("msg", ""))})
    return sanitised


def _problem(
    *,
    status_code: int,
    code: str,
    detail: str,
    extra: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"https://docs.chartnexus.app/errors/{code}",
        "title": code.replace("_", " ").title(),
        "status": status_code,
        "detail": detail,
        "code": code,
    }
    request_id = current_request_id()
    if request_id:
        body["request_id"] = request_id
    if extra:
        body.update({key: value for key, value in extra.items() if value is not None})

    return JSONResponse(
        status_code=status_code,
        content=body,
        headers=headers or None,
        media_type=PROBLEM_CONTENT_TYPE,
    )
