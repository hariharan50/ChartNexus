"""The option-chain capture loop, shared by every caller that runs it.

Lives in the entrypoints layer — not infrastructure — because it wires a
``Container`` (a composition root), which adapters are forbidden to import. Two
entry points drive the exact same loop, and this module exists so they cannot
drift:

* the standalone ``marketcompass-ingest`` process (:mod:`entrypoints.main_ingest`),
  which is what a deployed environment runs; and
* a background task the API starts in its lifespan **in local development only**,
  so a developer who runs just the API still gets a populated snapshot archive
  instead of the two-point "open vs now" estimate the Options Lab charts fall back
  to when today has no history.

One tick opens a fresh committing session, resolves a broker provider, snapshots
every configured symbol and sleeps ``MARKET_SNAPSHOT_INTERVAL_SECONDS``. Nothing
is written outside session hours, and — unless ``allow_mock`` is set — nothing is
written on a mock-fallback day. A bad tick is logged and swallowed: the loop must
outlive any single failure.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, date, datetime, timedelta, timezone

from marketcompass.bootstrap.container import Container
from marketcompass.bootstrap.settings import Settings
from marketcompass.contexts.market_ingestion.application.retention import PruneSnapshots
from marketcompass.infrastructure.ingestion.chain_source import build_ingest_service
from marketcompass.infrastructure.observability.structured_logging import get_logger
from marketcompass.infrastructure.persistence.postgresql.repositories.market_data.option_chain_snapshot_repository import (
    SqlAlchemyOptionChainSnapshotRepository,
)

log = get_logger(__name__)

# India observes no DST; a fixed +05:30 offset matches how the ingest use case
# and the OI service both reason about the trading session.
_IST = timezone(timedelta(hours=5, minutes=30))


class _SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


async def capture_tick(container: Container, settings: Settings, *, allow_mock: bool) -> None:
    """One capture pass. Never propagates — the loop must survive a bad tick."""
    try:
        async with container.database.session() as session:
            service = build_ingest_service(
                session=session,
                container=container,
                symbols=tuple(settings.market.ingest_symbols),
                allow_mock=allow_mock,
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


async def prune_once(container: Container, settings: Settings) -> None:
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


async def run_capture_loop(
    container: Container,
    settings: Settings,
    *,
    stop: asyncio.Event,
    allow_mock: bool | None = None,
) -> None:
    """Capture on a fixed cadence until ``stop`` is set.

    ``allow_mock`` overrides ``MARKET_INGEST_ALLOW_MOCK`` when passed — the API's
    local in-process loop forces it on so the charts populate even on a day the
    broker never answers, matching what ``task dev`` does for the standalone
    worker.
    """
    resolved_allow_mock = (
        settings.market.ingest_allow_mock if allow_mock is None else allow_mock
    )
    interval = settings.market.snapshot_interval_seconds
    log.info(
        "ingest_loop_starting",
        interval_seconds=interval,
        symbols=list(settings.market.ingest_symbols),
        allow_mock=resolved_allow_mock,
    )
    pruned_on: date | None = None
    try:
        while not stop.is_set():
            # Once per IST trading date, before the tick, so a restarted worker
            # still prunes and a long-running one does not prune every interval.
            today = datetime.now(_IST).date()
            if pruned_on != today:
                pruned_on = today
                await prune_once(container, settings)

            await capture_tick(container, settings, allow_mock=resolved_allow_mock)
            # Sleep the interval, but wake immediately on a stop signal.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=interval)
    finally:
        log.info("ingest_loop_stopping")
