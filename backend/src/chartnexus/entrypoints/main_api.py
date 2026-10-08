"""HTTP API process.

Serves the REST surface described by ``contracts/openapi/v1/openapi.yaml``.
Ingestion, scoring, and websocket fan-out run in their own processes so a slow
broker call can never occupy an API worker.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from chartnexus.bootstrap.container import Container
from chartnexus.bootstrap.logging import configure_logging
from chartnexus.bootstrap.route_registry import API_PREFIX, register_routes
from chartnexus.bootstrap.settings import Environment, Settings, get_settings
from chartnexus.entrypoints.catalog_runtime import (
    load_registry,
    run_catalog_loop,
    run_registry_refresh_loop,
)
from chartnexus.entrypoints.futures_board_runtime import run_futures_board_loop
from chartnexus.entrypoints.futures_oi_runtime import run_futures_oi_loop
from chartnexus.entrypoints.hugin_runtime import run_hugin_loop
from chartnexus.entrypoints.ingest_runtime import run_capture_loop
from chartnexus.entrypoints.mme100_runtime import run_mme100_loop
from chartnexus.entrypoints.report_runtime import run_report_loop
from chartnexus.infrastructure.cache.redis.client import redis_check
from chartnexus.infrastructure.observability.structured_logging import get_logger
from chartnexus.infrastructure.persistence.postgresql.health import postgres_check
from chartnexus.infrastructure.transport.http.exception_handlers import (
    register_exception_handlers,
)
from chartnexus.infrastructure.transport.http.health import DependencyCheck, build_health_router
from chartnexus.infrastructure.transport.http.middleware import SecurityHeadersMiddleware
from chartnexus.infrastructure.transport.http.request_id import RequestIdMiddleware

API_VERSION = "0.1.0"

log = get_logger(__name__)


@dataclass(slots=True)
class _LocalWorker:
    """A background loop the API runs in-process (local dev only)."""

    task: asyncio.Task[None]
    stop: asyncio.Event


def _maybe_start(
    *,
    enabled: bool,
    name: str,
    make_loop: Callable[[asyncio.Event], Coroutine[Any, Any, None]],
) -> _LocalWorker | None:
    """Start ``make_loop`` as a named background task, or return ``None`` if disabled.

    Most of these are local-only: deployed environments run the equivalent
    standalone process (ingest, HUGIN, MME100, report), and ``task dev``
    disables the in-process copy so the two do not double up. The registry
    refresh loop is the exception — every process needs its own.
    """
    if not enabled:
        return None
    stop = asyncio.Event()
    task = asyncio.create_task(make_loop(stop), name=name)
    log.info("api_worker_in_process", worker=name)
    return _LocalWorker(task=task, stop=stop)


async def _stop_worker(worker: _LocalWorker | None) -> None:
    """Signal, cancel, and await a background worker (no-op if it never started)."""
    if worker is None:
        return
    worker.stop.set()
    worker.task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await worker.task


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI application. Tests call this directly with test settings."""
    resolved = settings or get_settings()
    configure_logging(resolved)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = Container.create(resolved)
        app.state.container = container
        log.info(
            "api_starting",
            environment=resolved.environment.value,
            broker=resolved.broker.provider,
            llm=resolved.llm.provider,
        )

        # The instrument catalog backs every symbol lookup the adapters make,
        # so it is loaded before anything can serve a request.
        await load_registry(container)

        # Background workers. The registry refresh below runs everywhere; the
        # rest are local-only, each having a standalone process for deployed
        # environments (``chartnexus-ingest`` / ``-hugin`` / ``-mme100`` / the
        # report worker). Running them in-process lets a developer on just the API
        # get a populated snapshot archive, accruing HUGIN memory, the morning
        # briefing, and the daily PDF. ``task dev`` disables the in-process copies
        # so they never double up with their separate workers. Ingest forces
        # ``allow_mock`` on so the charts populate even when the broker never
        # answers. Shut down in reverse start order in the ``finally``.
        local = resolved.environment == Environment.LOCAL
        workers = (
            # Not local-only, unlike everything below it. The load above is a
            # single read: if it came back empty — a first deploy, or a start
            # that beat Postgres to accepting connections — nothing else in a
            # deployed API would ever try again, and the process would answer
            # "NIFTY is not a tradeable instrument" to every request until a
            # human restarted it. This also carries the catalog worker's daily
            # refresh across into this process.
            _maybe_start(
                enabled=True,
                name="registry-refresh-loop",
                make_loop=lambda stop: run_registry_refresh_loop(container, resolved, stop=stop),
            ),
            # First: everything else resolves instruments through the catalog,
            # so it has to be populated before the other loops do useful work.
            _maybe_start(
                enabled=local and resolved.catalog.enabled and resolved.catalog.in_process,
                name="catalog-refresh-loop",
                make_loop=lambda stop: run_catalog_loop(container, resolved, stop=stop),
            ),
            _maybe_start(
                enabled=local and resolved.futures_oi.enabled and resolved.futures_oi.in_process,
                name="futures-oi-sweep",
                make_loop=lambda stop: run_futures_oi_loop(container, resolved, stop=stop),
            ),
            # Captures the board itself. Separate from the sweep above because
            # price is cheap to fetch and open interest is not — see the
            # runtime's docstring for the quota arithmetic.
            _maybe_start(
                enabled=local
                and resolved.futures_history.enabled
                and resolved.futures_history.in_process,
                name="futures-board-capture",
                make_loop=lambda stop: run_futures_board_loop(container, resolved, stop=stop),
            ),
            _maybe_start(
                enabled=local and resolved.market.ingest_in_process,
                name="ingest-capture-loop",
                make_loop=lambda stop: run_capture_loop(
                    container, resolved, stop=stop, allow_mock=True
                ),
            ),
            _maybe_start(
                enabled=local and resolved.hugin.enabled and resolved.hugin.in_process,
                name="hugin-memory-loop",
                make_loop=lambda stop: run_hugin_loop(container, resolved, stop=stop),
            ),
            _maybe_start(
                enabled=local and resolved.mme100.enabled and resolved.mme100.in_process,
                name="mme100-briefing-loop",
                make_loop=lambda stop: run_mme100_loop(container, resolved, stop=stop),
            ),
            _maybe_start(
                enabled=local and resolved.report.enabled and resolved.report.in_process,
                name="daily-report-loop",
                make_loop=lambda stop: run_report_loop(container, resolved, stop=stop),
            ),
        )

        try:
            yield
        finally:
            for worker in reversed(workers):
                await _stop_worker(worker)
            log.info("api_stopping")
            await container.aclose()

    app = FastAPI(
        title="ChartNexus API",
        version=API_VERSION,
        summary="Options and futures market intelligence",
        root_path=resolved.api_root_path,
        docs_url="/docs" if not resolved.environment.is_deployed else None,
        redoc_url=None,
        openapi_url="/openapi.json" if not resolved.environment.is_deployed else None,
        lifespan=lifespan,
    )

    app.add_middleware(RequestIdMiddleware)
    # Inside GZip, so the content-type it branches on is the handler's own and
    # not yet rewritten for compression. CORS pre-flight responses short-circuit
    # above this and carry no body, so they do not need the headers.
    app.add_middleware(SecurityHeadersMiddleware, hsts=resolved.environment.is_deployed)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved.cors_allow_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-CSRF-Token"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )

    register_exception_handlers(app, expose_internal_detail=resolved.debug)

    # The probes resolve the container lazily: routes are declared at import
    # time, but the connections they check only exist once lifespan has run.
    async def check_postgres() -> None:
        await postgres_check(app.state.container.database)()

    async def check_redis() -> None:
        await redis_check(app.state.container.redis)()

    app.include_router(
        build_health_router(
            version=API_VERSION,
            checks=(
                DependencyCheck("postgres", check_postgres),
                DependencyCheck("redis", check_redis),
            ),
        )
    )

    register_routes(app, prefix=API_PREFIX)

    return app


def run() -> None:
    """Console-script entrypoint: ``uv run chartnexus-api``."""
    settings = get_settings()
    uvicorn.run(
        "chartnexus.entrypoints.main_api:create_app",
        factory=True,
        host="0.0.0.0",  # noqa: S104 — bound inside a container network
        port=8000,
        reload=settings.environment.value == "local",
        log_config=None,
        access_log=False,
        # Behind nginx every request arrives from the proxy, so without these
        # the scheme reads as http (breaking any absolute URL the app builds)
        # and request.client.host is the proxy for every caller. Trusted only
        # because nothing but the edge proxy can reach this port: the container
        # publishes it to the compose network, never to the host.
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    run()
