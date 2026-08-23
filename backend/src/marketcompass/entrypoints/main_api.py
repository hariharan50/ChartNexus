"""HTTP API process.

Serves the REST surface described by ``contracts/openapi/v1/openapi.yaml``.
Ingestion, scoring, and websocket fan-out run in their own processes so a slow
broker call can never occupy an API worker.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from marketcompass.bootstrap.container import Container
from marketcompass.bootstrap.logging import configure_logging
from marketcompass.bootstrap.route_registry import API_PREFIX, register_routes
from marketcompass.bootstrap.settings import Environment, Settings, get_settings
from marketcompass.entrypoints.hugin_runtime import run_hugin_loop
from marketcompass.entrypoints.ingest_runtime import run_capture_loop
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

        # Local-only: run the snapshot capture loop as a background task so a
        # developer who starts just the API still gets a populated archive. The
        # Options Lab charts (Multi OI, PCR, Gamma, Vega) read that archive; with
        # no writer they show a two-point straight-line estimate, or nothing.
        # Never enabled outside local — deployed environments run the standalone
        # ``marketcompass-ingest`` worker, and ``task dev`` sets the flag false so
        # its separate worker does not double up with this one. ``allow_mock`` is
        # forced on so the charts populate even on a day the broker never answers.
        ingest_stop = asyncio.Event()
        ingest_task: asyncio.Task[None] | None = None
        if resolved.environment == Environment.LOCAL and resolved.market.ingest_in_process:
            ingest_task = asyncio.create_task(
                run_capture_loop(container, resolved, stop=ingest_stop, allow_mock=True),
                name="ingest-capture-loop",
            )
            log.info(
                "api_ingest_in_process",
                interval_seconds=resolved.market.snapshot_interval_seconds,
            )

        # Local-only, same rationale as the ingest loop: run HUGIN's hourly
        # market-memory worker in-process so a developer on just the API sees its
        # memory accrue. Deployed environments run the standalone
        # ``marketcompass-hugin`` process; ``task dev`` sets the flag false so the
        # separate worker does not double up.
        hugin_stop = asyncio.Event()
        hugin_task: asyncio.Task[None] | None = None
        if (
            resolved.environment == Environment.LOCAL
            and resolved.hugin.enabled
            and resolved.hugin.in_process
        ):
            hugin_task = asyncio.create_task(
                run_hugin_loop(container, resolved, stop=hugin_stop),
                name="hugin-memory-loop",
            )
            log.info("api_hugin_in_process", interval_seconds=resolved.hugin.interval_seconds)

        try:
            yield
        finally:
            if hugin_task is not None:
                hugin_stop.set()
                hugin_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await hugin_task
            if ingest_task is not None:
                ingest_stop.set()
                ingest_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await ingest_task
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
