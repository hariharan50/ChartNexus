"""The httpx transport that times every outbound call.

It wraps the real transport and changes nothing about the call: the same
request goes out, the same response or exception comes back. The only
addition is one :meth:`ApiCallRecorder.record` per call, which is an in-memory
update. A failure inside the monitor is swallowed, so it can never surface as
a broker error.

The response is timed to its headers, which is what "latency" means for an
API: the body is read by the caller afterwards, and every broker payload here
is small enough that headers and body arrive together.
"""

from __future__ import annotations

import time

import httpx

from chartnexus.infrastructure.observability.api_monitor.classify import (
    app_from_authorization,
    endpoint_template,
    provider_for,
)
from chartnexus.infrastructure.observability.api_monitor.origin import current_origin
from chartnexus.infrastructure.observability.api_monitor.recorder import (
    ApiCallRecorder,
    CallOutcome,
)
from chartnexus.infrastructure.observability.api_monitor.schema import SeriesKey

_TOO_MANY_REQUESTS = 429
_CLIENT_ERROR = 400
_SERVER_ERROR = 500


def error_class_for_status(status: int) -> str | None:
    if status == _TOO_MANY_REQUESTS:
        return "http_429"
    if status >= _SERVER_ERROR:
        return "http_5xx"
    if status >= _CLIENT_ERROR:
        return "http_4xx"
    return None


def error_class_for_exception(exc: BaseException) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.ConnectError):
        return "connect"
    return "network"


class MonitoredTransport(httpx.AsyncBaseTransport):
    def __init__(self, inner: httpx.AsyncBaseTransport, recorder: ApiCallRecorder) -> None:
        self._inner = inner
        self._recorder = recorder

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if not self._recorder.enabled:
            return await self._inner.handle_async_request(request)

        started = time.perf_counter()
        try:
            response = await self._inner.handle_async_request(request)
        except BaseException as exc:
            if isinstance(exc, Exception):
                self._record(request, started, status=None, error=error_class_for_exception(exc))
            raise
        self._record(
            request,
            started,
            status=response.status_code,
            error=error_class_for_status(response.status_code),
        )
        return response

    def _record(
        self, request: httpx.Request, started: float, *, status: int | None, error: str | None
    ) -> None:
        try:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            provider = provider_for(request.url.host)
            series = SeriesKey(
                provider=provider,
                endpoint=endpoint_template(request.url.path),
                origin=current_origin(),
                app=app_from_authorization(provider, request.headers.get("Authorization")),
            )
            self._recorder.record(
                CallOutcome(
                    series=series,
                    method=request.method,
                    elapsed_ms=elapsed_ms,
                    status=status,
                    error=error,
                    at=time.time(),
                )
            )
        except Exception:  # noqa: S110 — the monitor must never break a call
            pass

    async def aclose(self) -> None:
        await self._inner.aclose()
