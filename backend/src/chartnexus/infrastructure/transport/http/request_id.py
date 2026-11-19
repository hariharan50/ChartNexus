"""Request-id middleware.

Accepts an inbound ``X-Request-ID`` so a correlation id survives the hop from
the edge proxy, but only when it looks like an id we issued — an unvalidated
header ends up in logs and dashboards.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from chartnexus.infrastructure.observability.api_monitor.classify import endpoint_template
from chartnexus.infrastructure.observability.api_monitor.origin import api_call_origin
from chartnexus.infrastructure.observability.request_context import bind_request_context

REQUEST_ID_HEADER = "X-Request-ID"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,128}$")


class RequestIdMiddleware:
    """Binds a request id to the ambient context and echoes it on the response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        request_id = _resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_header(message) -> None:  # type: ignore[no-untyped-def]
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.append((REQUEST_ID_HEADER.lower().encode(), request_id.encode()))
            await send(message)

        # Outbound calls made while serving this request are labelled with its
        # path in the API monitor; ids in the path are templated away.
        origin = "request:" + endpoint_template(str(scope.get("path") or "/"))
        with bind_request_context(request_id=request_id), api_call_origin(origin):
            await self.app(scope, receive, send_with_header)


def _resolve_request_id(inbound: str | None) -> str:
    if inbound and _SAFE_REQUEST_ID.match(inbound):
        return inbound
    return uuid.uuid4().hex


async def dispatch_request_id(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """BaseHTTPMiddleware-style variant, kept for tests that need a plain callable."""
    request_id = _resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
    with bind_request_context(request_id=request_id):
        response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response
