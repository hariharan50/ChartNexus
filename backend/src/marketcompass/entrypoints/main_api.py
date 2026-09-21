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

from marketcompass.bootstrap.container import Container
from marketcompass.bootstrap.logging import configure_logging
from marketcompass.bootstrap.route_registry import API_PREFIX, register_routes
from marketcompass.bootstrap.settings import Environment, Settings, get_settings
from marketcompass.entrypoints.catalog_runtime import load_registry, run_catalog_loop
from marketcompass.entrypoints.futures_oi_runtime import run_futures_oi_loop
from marketcompass.entrypoints.hugin_runtime import run_hugin_loop
from marketcompass.entrypoints.ingest_runtime import run_capture_loop
from marketcompass.entrypoints.mme100_runtime import run_mme100_loop
from marketcompass.entrypoints.report_runtime import run_report_loop
from marketcompass.infrastructure.cache.redis.client import redis_check
from marketcompass.infrastructure.observability.structured_logging import get_logger
from marketcompass.infrastructure.persistence.postgresql.health import postgres_check
from marketcompass.infrastructure.transport.http.exception_handlers import (
    register_exception_handlers,
)
from marketcompass.infrastructure.transport.http.health import DependencyCheck, build_health_router
from marketcompass.infrastructure.transport.http.request_id import RequestIdMiddleware

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

    Each in-process worker (ingest, HUGIN, MME100, report) is local-only: deployed
    environments run the equivalent standalone process, and ``task dev`` disables
    the in-process copy so the two do not double up.
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

        # Local-only background workers. Each has a standalone process for deployed
        # environments (``marketcompass-ingest`` / ``-hugin`` / ``-mme100`` / the
        # report worker); running them in-process lets a developer on just the API
        # get a populated snapshot archive, accruing HUGIN memory, the morning
        # briefing, and the daily PDF. ``task dev`` disables the in-process copies
        # so they never double up with their separate workers. Ingest forces
        # ``allow_mock`` on so the charts populate even when the broker never
        # answers. Shut down in reverse start order in the ``finally``.
        local = resolved.environment == Environment.LOCAL
        workers = (
            # First: everything else resolves instruments through the catalog,
            # so it has to be populated before the other loops do useful work.
            _maybe_start(
                enabled=local and resolved.catalog.enabled and resolved.catalog.in_process,
                name="catalog-refresh-loop",
                make_loop=lambda stop: run_catalog_loop(container, resolved, stop=stop),
            ),
            _maybe_start(
                enabled=local
                and resolved.futures_oi.enabled
                and resolved.futures_oi.in_process,
                name="futures-oi-sweep",
                make_loop=lambda stop: run_futures_oi_loop(container, resolved, stop=stop),
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
        title="MarketCompass API",
        version=API_VERSION,
        summary="Options and futures market intelligence",
        root_path=resolved.api_root_path,
        docs_url="/docs" if not resolved.environment.is_deployed else None,
        redoc_url=None,
        openapi_url="/openapi.json" if not resolved.environment.is_deployed else None,
        lifespan=lifespan,
    )

    app.add_middleware(RequestIdMiddleware)
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
    """Console-script entrypoint: ``uv run marketcompass-api``."""
    settings = get_settings()
    uvicorn.run(
        "marketcompass.entrypoints.main_api:create_app",
        factory=True,
        host="0.0.0.0",  # noqa: S104 — bound inside a container network
        port=8000,
        reload=settings.environment.value == "local",
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    run()
