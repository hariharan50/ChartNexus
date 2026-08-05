"""Market ingestion process.

Captures option-chain snapshots on a fixed cadence during market hours and
writes them to Postgres, building the application's own time-series archive of
open interest. Runs as its own process so a slow broker call can never occupy an
API worker.

Each tick opens a fresh committing session, resolves a broker provider (any
tenant with an active FYERS connection, else mock), snapshots every configured
symbol, and sleeps ``MARKET_SNAPSHOT_INTERVAL_SECONDS``. Nothing is written
outside session hours, and — unless ``MARKET_INGEST_ALLOW_MOCK`` is set — nothing
is written on a mock-fallback day.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal

from marketcompass.bootstrap.container import Container
from marketcompass.bootstrap.logging import configure_logging
from marketcompass.bootstrap.settings import Settings, get_settings
from marketcompass.infrastructure.ingestion.chain_source import build_ingest_service
from marketcompass.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)


async def _tick(container: Container, settings: Settings) -> None:
    """One capture pass. Never propagates — the loop must survive a bad tick."""
    try:
        async with container.database.session() as session:
            service = build_ingest_service(
                session=session,
                container=container,
                symbols=tuple(settings.market.ingest_symbols),
                allow_mock=settings.market.ingest_allow_mock,
            )
            result = await service()
    except Exception as exc:
        log.error("ingest_tick_failed", error=repr(exc))
        return

    if result.skipped_closed:
        log.info("ingest_tick_skipped", reason="market_closed")
        return
    log.info(
        "ingest_tick",
        written=list(result.written),
        skipped_mock=list(result.skipped_mock),
        skipped_empty=list(result.skipped_empty),
        failed=[symbol for symbol, _ in result.failed],
    )


async def _run(settings: Settings) -> None:
    configure_logging(settings)
    container = Container.create(settings, use_db_pool=False)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        # Windows event loops do not support signal handlers; Ctrl+C still raises
        # KeyboardInterrupt out of asyncio.run and unwinds cleanly.
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    interval = settings.market.snapshot_interval_seconds
    log.info(
        "ingest_starting",
        interval_seconds=interval,
        symbols=list(settings.market.ingest_symbols),
        allow_mock=settings.market.ingest_allow_mock,
    )
    try:
        while not stop.is_set():
            await _tick(container, settings)
            # Sleep the interval, but wake immediately on a shutdown signal.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=interval)
    finally:
        log.info("ingest_stopping")
        await container.aclose()


def run() -> None:
    """Console-script entrypoint: ``uv run marketcompass-ingest``."""
    asyncio.run(_run(get_settings()))


if __name__ == "__main__":
    run()
