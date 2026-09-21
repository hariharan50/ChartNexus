"""The instrument-catalog refresh loop, shared by every caller that runs it.

Lives in entrypoints — not infrastructure — because it wires a ``Container``,
which adapters are forbidden to import. The same loop runs from the standalone
``marketcompass-catalog`` process and, in local development only, as a
background task in the API's lifespan.

The catalog is the F&O universe: which underlyings exist, their lot sizes, and
the broker strings needed to quote them. NSE revises that list by circular
several times a year, so it is refreshed from the exchange symbol master rather
than pinned in a seed migration. The masters are public files, so this runs
with no broker account and spends no API quota.

Refresh runs once a day, before the session opens. A failure is logged and
swallowed: yesterday's catalog is a perfectly good catalog, and taking the loop
down over a transient download error would eventually take the app with it.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime

from marketcompass.bootstrap.container import Container
from marketcompass.bootstrap.settings import Settings
from marketcompass.contexts.instrument_catalog.application.ports import CatalogSyncResult
from marketcompass.contexts.instrument_catalog.application.use_cases import SyncInstrumentCatalog
from marketcompass.contexts.mme100.domain.schedule import next_briefing_wake, parse_hhmm
from marketcompass.infrastructure.catalog import registry
from marketcompass.infrastructure.catalog.fyers_symbol_master import FyersSymbolMaster
from marketcompass.infrastructure.observability.structured_logging import get_logger
from marketcompass.infrastructure.persistence.postgresql.repositories.instrument_catalog.instrument_repository import (
    SqlAlchemyInstrumentRepository,
)
from marketcompass.infrastructure.transport.http.dependencies import SessionUnitOfWork

log = get_logger(__name__)


async def load_registry(container: Container) -> int:
    """Populate the in-process registry from the stored catalog.

    Every process that resolves an instrument needs this before serving
    anything — the symbol mapper and the mock generator both read it. Returns
    how many instruments were loaded so a caller can complain about zero.
    """
    try:
        async with container.database.read_session() as session:
            instruments = await SqlAlchemyInstrumentRepository(session).search(limit=None)
    except Exception as exc:
        log.error("catalog_registry_load_failed", error=repr(exc))
        return 0

    registry.install(instruments)
    if not instruments:
        # Not fatal, but nothing will resolve until a sync lands, so say so
        # loudly rather than letting every request 422 without explanation.
        log.warning("catalog_registry_empty", hint="run: uv run marketcompass-catalog --once")
    else:
        log.info("catalog_registry_loaded", instruments=len(instruments))
    return len(instruments)


async def sync_once(container: Container) -> CatalogSyncResult | None:
    """One refresh pass. Never propagates — the loop must survive a bad day."""
    try:
        async with container.database.session() as session:
            repository = SqlAlchemyInstrumentRepository(session)
            sync = SyncInstrumentCatalog(
                repository=repository,
                master=FyersSymbolMaster(container.http),
                uow=SessionUnitOfWork(session),
            )
            result = await sync()
    except Exception as exc:
        log.error("catalog_sync_failed", error=repr(exc))
        return None

    log.info(
        "catalog_synced",
        added=result.added,
        updated=result.updated,
        deactivated=result.deactivated,
        total=result.total,
    )
    # The rows just changed underneath the cache every other adapter reads.
    await load_registry(container)
    return result


async def run_catalog_loop(
    container: Container, settings: Settings, *, stop: asyncio.Event
) -> None:
    catalog = settings.catalog
    if not catalog.enabled:
        log.info("catalog_loop_disabled")
        return

    refresh_time = parse_hhmm(catalog.refresh_time_ist)
    log.info("catalog_loop_starting", refresh_time_ist=catalog.refresh_time_ist)

    # An empty catalog means no instrument resolves at all, so a cold start
    # fills it rather than waiting for tomorrow's refresh.
    #
    # Only when it is actually empty, though. The masters are ~19 MB and the
    # API runs this loop in-process under `--reload`, so syncing on every start
    # would put a large download in front of every code change a developer
    # makes. A populated catalog one day stale is fine until the scheduled run.
    if catalog.sync_on_start and not len(registry.current()):
        log.info("catalog_cold_start", reason="registry_empty")
        await sync_once(container)

    try:
        while not stop.is_set():
            now = datetime.now(UTC)
            wake = next_briefing_wake(now, refresh_time)
            delay = max(1.0, (wake - now).total_seconds())
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=delay)
            if stop.is_set():
                break
            await sync_once(container)
    finally:
        log.info("catalog_loop_stopping")
