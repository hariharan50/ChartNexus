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
from datetime import UTC, date, datetime, timedelta, timezone

from marketcompass.bootstrap.container import Container
from marketcompass.bootstrap.logging import configure_logging
from marketcompass.bootstrap.settings import Settings, get_settings
from marketcompass.contexts.market_ingestion.application.retention import PruneSnapshots
from marketcompass.infrastructure.ingestion.chain_source import build_ingest_service
from marketcompass.infrastructure.observability.structured_logging import get_logger
from marketcompass.infrastructure.persistence.postgresql.repositories.market_data.option_chain_snapshot_repository import (
    SqlAlchemyOptionChainSnapshotRepository,
)

log = get_logger(__name__)

_IST = timezone(timedelta(hours=5, minutes=30))


class _SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


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
        skipped_unchanged=list(result.skipped_unchanged),
        failed=[symbol for symbol, _ in result.failed],
    )


async def _prune(container: Container, settings: Settings) -> None:
    """Apply the retention window. Never propagates — pruning is not the job.

    Deliberately called from the loop rather than from ``CaptureChainSnapshots``:
    that use case returns early when the market is closed, which is exactly when
    this should run.
    """
    try:
        async with container.database.session() as session:
            use_case = PruneSnapshots(
                pruner=SqlAlchemyOptionChainSnapshotRepository(session),
                clock=_SystemClock(),
                retention_days=settings.market.snapshot_retention_days,
            )
            result = await use_case()
    except Exception as exc:
        log.error("ingest_prune_failed", error=repr(exc))
        return
    log.info("ingest_prune", cutoff=result.cutoff.isoformat(), deleted=result.deleted)


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
    pruned_on: date | None = None
    try:
        while not stop.is_set():
            # Once per IST trading date, before the tick, so a restarted worker
            # still prunes and a long-running one does not prune every 3 minutes.
            today = datetime.now(_IST).date()
            if pruned_on != today:
                pruned_on = today
                await _prune(container, settings)

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
