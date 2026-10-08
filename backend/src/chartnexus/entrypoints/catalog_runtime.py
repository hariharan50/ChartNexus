"""The instrument-catalog refresh loop, shared by every caller that runs it.

Lives in entrypoints — not infrastructure — because it wires a ``Container``,
which adapters are forbidden to import. The same loop runs from the standalone
``chartnexus-catalog`` process and, in local development only, as a
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
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from chartnexus.bootstrap.container import Container
from chartnexus.bootstrap.settings import Settings
from chartnexus.contexts.instrument_catalog.application.ports import CatalogSyncResult
from chartnexus.contexts.instrument_catalog.application.use_cases import SyncInstrumentCatalog
from chartnexus.contexts.instrument_catalog.domain.instrument import Instrument
from chartnexus.contexts.mme100.domain.schedule import next_briefing_wake, parse_hhmm
from chartnexus.infrastructure.catalog import registry
from chartnexus.infrastructure.catalog.fyers_symbol_master import FyersSymbolMaster
from chartnexus.infrastructure.observability.structured_logging import get_logger
from chartnexus.infrastructure.persistence.postgresql.repositories.instrument_catalog.instrument_repository import (
    SqlAlchemyInstrumentRepository,
)
from chartnexus.infrastructure.transport.http.dependencies import SessionUnitOfWork

log = get_logger(__name__)

#: How long to wait before trying again when the process came up without a
#: catalog. Short, because until this succeeds *every* instrument lookup in the
#: process fails; capped by :data:`_RETRY_CEILING_SECONDS` so a genuinely
#: unreachable database is not hammered.
_RETRY_BASE_SECONDS = 5.0
_RETRY_CEILING_SECONDS = 60.0


async def _read_catalog(container: Container) -> list[Instrument]:
    """The stored catalog. Propagates, so a caller can tell "the database is
    down" from "the catalog is empty" — the two want different responses."""
    async with container.database.read_session() as session:
        return await SqlAlchemyInstrumentRepository(session).search(limit=None)


async def load_registry(container: Container) -> int:
    """Populate the in-process registry from the stored catalog.

    Every process that resolves an instrument needs this before serving
    anything — the symbol mapper and the mock generator both read it. Returns
    how many instruments were loaded so a caller can complain about zero.
    """
    try:
        instruments = await _read_catalog(container)
    except Exception as exc:
        log.error("catalog_registry_load_failed", error=repr(exc))
        return 0

    registry.install(instruments)
    if not instruments:
        # Not fatal, but nothing will resolve until a sync lands, so say so
        # loudly rather than letting every request 422 without explanation.
        log.warning("catalog_registry_empty", hint="run: uv run chartnexus-catalog --once")
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


async def ensure_registry(container: Container, *, stop: asyncio.Event) -> int:
    """Keep trying until the process has a catalog, or ``stop`` is set.

    Exists because of a failure that took the whole application down for a day:
    the API started a few seconds before Postgres finished accepting
    connections, :func:`load_registry` logged its error and returned 0, and the
    one cold-start sync failed against the same unreachable database. Nothing
    retried, so a process that was otherwise healthy answered *every* request
    with "NIFTY is not a tradeable instrument" until someone restarted it.

    The order matters. A reload from the database comes first and costs one
    query: in that race the rows were already there, and only the in-process
    cache was missing. The ~19 MB symbol-master download is the fallback, for a
    catalog that is genuinely empty.
    """
    if len(registry.current()):
        return len(registry.current())

    log.info("catalog_cold_start", reason="registry_empty")
    delay = _RETRY_BASE_SECONDS
    while not stop.is_set():
        try:
            stored = await _read_catalog(container)
        except Exception as exc:
            # The database is not answering yet — which is the whole reason this
            # retries. Do *not* fall through to a sync: it writes to the same
            # database, so it would fail too, after a 19 MB download.
            log.error("catalog_registry_load_failed", error=repr(exc))
        else:
            if stored:
                registry.install(stored)
                log.info("catalog_registry_loaded", instruments=len(stored))
                return len(stored)
            # Reachable and genuinely empty: this is a first run, so fill it.
            await sync_once(container)
            if len(registry.current()):
                return len(registry.current())

        log.warning("catalog_cold_start_retrying", retry_in_seconds=delay)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=delay)
        delay = min(delay * 2, _RETRY_CEILING_SECONDS)

    return len(registry.current())


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
    # fills it rather than waiting for tomorrow's refresh — and keeps trying
    # until it has one.
    #
    # Only when it is actually empty, though; `ensure_registry` returns at once
    # otherwise. The masters are ~19 MB and the API runs this loop in-process
    # under `--reload`, so syncing on every start would put a large download in
    # front of every code change a developer makes. A populated catalog one day
    # stale is fine until the scheduled run.
    if catalog.sync_on_start:
        await ensure_registry(container, stop=stop)

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


async def run_registry_refresh_loop(
    container: Container,
    settings: Settings,
    *,
    stop: asyncio.Event,
) -> None:
    """Keep *this process's* registry in step with the stored catalog.

    Reads, never syncs. Every process that resolves an instrument holds its own
    in-memory copy of the catalog, installed once at startup — and only the
    catalog worker ever refreshes its own. That left two gaps that
    :func:`load_registry` alone cannot close, both of which are invisible on a
    developer machine because there the API runs the catalog loop in-process:

    * A process that starts before the catalog is populated — a first deploy, or
      any start that wins the race against Postgres accepting connections —
      installs an empty registry and keeps it. Nothing retries, so it answers
      "NIFTY is not a tradeable instrument" to every request until a human
      restarts it.
    * A process that started fine still never sees the next morning's refresh.
      When a circular changes a lot size, the API keeps quoting yesterday's
      until it happens to be redeployed.

    Syncing is left to the catalog worker on purpose. The symbol masters are
    ~19 MB and a sync writes to the same rows, so having six processes each
    decide to fetch them would turn one cold start into a stampede. This only
    ever issues the one cheap ``SELECT``.
    """
    if not settings.catalog.enabled:
        log.info("registry_refresh_disabled")
        return

    interval = float(settings.catalog.registry_refresh_seconds)
    log.info("registry_refresh_starting", interval_seconds=interval)

    # Escalating while there is nothing to serve, the steady interval once
    # there is. An empty registry is an outage for this process, so it is worth
    # asking again soon — but a catalog that stays empty for an hour is a
    # problem a human has to fix, not one to keep querying every five seconds.
    backoff = _RETRY_BASE_SECONDS

    try:
        while not stop.is_set():
            if len(registry.current()):
                delay = interval
            else:
                delay = backoff
                backoff = min(backoff * 2, _RETRY_CEILING_SECONDS)

            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=delay)
            if stop.is_set():
                break

            before = len(registry.current())
            after = await load_registry(container)
            if after != before:
                log.info("registry_refreshed", instruments=after, previous=before)
            if after:
                backoff = _RETRY_BASE_SECONDS
    finally:
        log.info("registry_refresh_stopping")


@contextlib.asynccontextmanager
async def registry_kept_current(
    container: Container,
    settings: Settings,
    *,
    stop: asyncio.Event,
) -> AsyncIterator[None]:
    """Run a worker's main loop with :func:`run_registry_refresh_loop` alongside it.

    Every standalone worker wants exactly this and nothing more, so the task
    lifetime lives here rather than being hand-rolled seven times::

        async with registry_kept_current(container, settings, stop=stop):
            await run_capture_loop(container, settings, stop=stop)

    The refresh is cancelled on the way out, including when the body raises, so
    a worker that dies cannot leave the task behind.
    """
    task = asyncio.create_task(
        run_registry_refresh_loop(container, settings, stop=stop),
        name="registry-refresh-loop",
    )
    try:
        yield
    finally:
        stop.set()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
