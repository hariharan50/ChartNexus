"""The open-interest sweep, shared by every caller that runs it.

Lives in entrypoints — not infrastructure — because it wires a ``Container``,
which adapters are forbidden to import. The same loop runs from the standalone
``chartnexus-futures-oi`` process and, in local development only, as a
background task in the API's lifespan.

**Why a worker at all.** The Future Lab classifies every contract by price
direction against open-interest direction. Price comes with the board — the
quote endpoint takes fifty symbols at a time — but the only endpoint carrying
open interest accepts exactly one contract per request and says so:

    "More than one symbol is not allowed. Please provide only one symbol."

Two hundred-odd contracts on the board's fifteen-second refresh would be about
340,000 requests a day against a 100,000 quota, and a sweep would take longer
than the interval it was trying to fill. On a five-minute cadence the same
sweep costs roughly 17,000 a day, which fits comfortably.

That trade is sound rather than merely cheap: open interest is a daily
aggregate that moves in minutes, so a reading a few minutes old classifies a
build-up just as well as a fresh one.

**Market hours only.** It also stops moving when the market shuts, so the loop
sweeps only during the session — plus one sweep just after the close, whose
readings are kept until the next open so the evening board still has its
build-up columns. It used to run around the clock, which on FYERS was ~54,000
of its ~73,500 daily calls spent re-reading figures that could not change.

**Paced, not raced.** The broker allows eight requests a second, shared with
every user request and every other worker. The sweep deliberately takes a small
slice of that, so filling a background column never makes someone's page slow.

**One pass per contract series.** The Future Lab can be pointed at the next or
far month, and each is a separate contract with its own book — there is no
deriving one from another. ``futures_oi.expiry_depth`` says how many to cover
and the cost is linear in it, so the default stops at two; a series past the
depth is still tradeable on the board, minus its open-interest columns, and the
page says so.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime

from chartnexus.bootstrap.container import Container
from chartnexus.bootstrap.settings import Settings
from chartnexus.contexts.broker_connections.domain.value_objects import BrokerName
from chartnexus.contexts.market_data.application.ports import MarketDataProvider
from chartnexus.contexts.market_data.domain.instruments import InstrumentSymbol
from chartnexus.infrastructure.brokers.futures_contract import MAX_SERIES
from chartnexus.infrastructure.brokers.provider_resolver import build_provider_resolver
from chartnexus.infrastructure.catalog import registry
from chartnexus.infrastructure.futures.oi_cache import (
    CachedOpenInterest,
    RedisOpenInterestCache,
)
from chartnexus.infrastructure.observability.structured_logging import get_logger
from chartnexus.infrastructure.persistence.postgresql.repositories.integration.broker_connection_repository import (
    SqlAlchemyBrokerConnectionRepository,
)
from chartnexus.infrastructure.time.market_calendar import ExchangeCalendar

log = get_logger(__name__)


#: Claimed by the one post-close sweep of a closed period; expires at the next
#: session open. Shared through Redis so a restart, or the API's in-process
#: copy beside a standalone worker, does not repeat it.
_CLOSED_SWEEP_MARKER = ("futures-oi", "closed-sweep")

#: Floor on any TTL derived from the time to the next open, so a sweep that
#: lands a moment before the bell still writes a usable expiry.
_MIN_TTL_SECONDS = 60


async def sweep_once(
    container: Container,
    settings: Settings,
    *,
    now: datetime | None = None,
    force: bool = False,
) -> int:
    """One pass over the universe. Never propagates — the loop must survive it.

    Returns how many contracts were priced, so a caller can tell a quiet sweep
    from a broken one. ``force`` sweeps even when the market-hours gate would
    skip — for an operator's explicit ``--once``, never for the loop.
    """
    try:
        return await _sweep(container, settings, now or datetime.now(UTC), force=force) or 0
    except Exception as exc:
        log.error("futures_oi_sweep_failed", error=repr(exc))
        return 0


def _calendar(settings: Settings) -> ExchangeCalendar:
    """The same session the option-chain ingest and the board capture gate on."""
    return ExchangeCalendar(
        timezone=settings.market.timezone,
        session_open=settings.market.session_open,
        session_close=settings.market.session_close,
    )


async def _sweep(
    container: Container, settings: Settings, now: datetime, *, force: bool = False
) -> int | None:
    """Sweep while the market trades; outside it, once, then not until the bell.

    Open interest only moves during the session. Sweeping around the clock
    cost ~444 broker calls every eight minutes overnight — about 54,000 a day
    on FYERS, where each contract is its own request — to re-read figures that
    could not change.

    Outside the session there is exactly one sweep, right after the close, to
    capture the day's final open interest. Its readings are kept until the
    next open, plus one normal TTL — as before, so the first in-session sweep
    replaces them without a blank gap — and the evening board keeps its
    build-up columns. The sweep is *claimed* in Redis before it starts, so two
    processes cannot both run it, and a sweep that dies half way is not
    retried every interval all night.
    """
    calendar = _calendar(settings)
    if calendar.is_open(now):
        return await _sweep_universe(
            container, settings, ttl_seconds=settings.futures_oi.ttl_seconds
        )

    next_open = calendar.next_open(now)
    until_open = max(int((next_open - now).total_seconds()), _MIN_TTL_SECONDS)
    closed_ttl = until_open + settings.futures_oi.ttl_seconds
    if force:
        # An operator asked. Sweep, keep the readings to the open like the
        # closing sweep does, and leave the claim alone either way.
        return await _sweep_universe(container, settings, ttl_seconds=closed_ttl)

    marker = container.redis.key(*_CLOSED_SWEEP_MARKER)
    claimed = await container.redis.client.set(marker, "1", ex=until_open, nx=True)
    if not claimed:
        log.debug("futures_oi_sweep_skipped", reason="market_closed")
        return 0

    priced = await _sweep_universe(container, settings, ttl_seconds=closed_ttl)
    if priced is None:
        # Nothing was asked of a broker — none connected, or no catalog yet.
        # Release the claim so the closing sweep still happens once one is
        # (connecting Kite at 20:00 should not leave the board bare until the
        # morning). Retrying costs nothing while there is no broker to call.
        await container.redis.client.delete(marker)
        return None

    log.info("futures_oi_closing_sweep", priced=priced, next_open=next_open.isoformat())
    return priced


async def _sweep_universe(
    container: Container, settings: Settings, *, ttl_seconds: int
) -> int | None:
    """Sweep every series once and cache it. ``None`` when no broker was called."""
    instruments = registry.current().symbols()
    if not instruments:
        log.warning("futures_oi_sweep_skipped", reason="empty_catalog")
        return None

    async with container.database.read_session() as session:
        connections = SqlAlchemyBrokerConnectionRepository(session, container.token_cipher)
        # Open interest is a fact about the market, not about a tenant, so any
        # working connection can fetch it and one sweep serves everybody.
        connection = await connections.find_market_feed()
        if connection is None:
            log.info("futures_oi_sweep_skipped", reason="no_connected_broker")
            return None

        resolver = build_provider_resolver(container, connections)
        provider = await resolver.resolve(connection.tenant_id)

        delay = 1.0 / max(settings.futures_oi.requests_per_second, 0.1)
        started = datetime.now(UTC)
        depth = min(settings.futures_oi.expiry_depth, MAX_SERIES)

        # Nearest series first, so a sweep that runs out of interval has
        # refreshed the contract almost every page is actually showing. Each
        # series is written to its own cache the moment it completes, for the
        # same reason: a slow far month must not hold back the near one.
        by_series: dict[int, dict[str, CachedOpenInterest]] = {}
        # Kite's /quote carries OI for up to 500 contracts at once, so a whole
        # series is one request instead of a paced per-contract walk.
        batched = connection.broker == BrokerName.KITE
        for series in range(depth if batched else 0):
            by_series[series] = await _board_series(provider, instruments, series)
        for series in range(0 if batched else depth):
            readings: dict[str, CachedOpenInterest] = {}
            for symbol in instruments:
                try:
                    reading = await provider.get_open_interest(
                        InstrumentSymbol(symbol), series=series
                    )
                except Exception as exc:
                    # One unquotable contract must not end the sweep for the rest.
                    log.debug(
                        "futures_oi_symbol_failed",
                        symbol=symbol,
                        series=series,
                        error=repr(exc),
                    )
                    reading = None

                if reading is not None:
                    readings[symbol] = CachedOpenInterest(
                        open_interest=reading.open_interest,
                        previous_open_interest=reading.previous_open_interest,
                        observed_at=reading.observed_at,
                    )
                # Pace between contracts, not after the last one.
                if symbol != instruments[-1]:
                    await asyncio.sleep(delay)
            by_series[series] = readings

    cache = RedisOpenInterestCache(container.redis, ttl_seconds=ttl_seconds)
    for series, readings in by_series.items():
        await cache.write_all(readings, series)

    priced = sum(len(readings) for readings in by_series.values())
    log.info(
        "futures_oi_swept",
        priced=priced,
        requested=len(instruments) * depth,
        series=depth,
        seconds=round((datetime.now(UTC) - started).total_seconds(), 1),
    )
    return priced


async def _board_series(
    provider: MarketDataProvider, instruments: tuple[str, ...], series: int
) -> dict[str, CachedOpenInterest]:
    """One series' open interest from a single board read. Never raises."""
    try:
        board = await provider.get_futures_board(
            [InstrumentSymbol(symbol) for symbol in instruments], series=series
        )
    except Exception as exc:
        log.warning("futures_oi_board_failed", series=series, error=repr(exc))
        return {}
    return {
        instrument.value: CachedOpenInterest(
            open_interest=quote.open_interest,
            previous_open_interest=quote.previous_open_interest,
            observed_at=quote.provenance.fetched_at,
        )
        for instrument, quote in board.items()
        if quote.open_interest is not None
    }


async def run_futures_oi_loop(
    container: Container, settings: Settings, *, stop: asyncio.Event
) -> None:
    oi = settings.futures_oi
    if not oi.enabled:
        log.info("futures_oi_loop_disabled")
        return

    log.info(
        "futures_oi_loop_starting",
        interval_seconds=oi.interval_seconds,
        requests_per_second=oi.requests_per_second,
    )
    try:
        while not stop.is_set():
            await sweep_once(container, settings)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=oi.interval_seconds)
    finally:
        log.info("futures_oi_loop_stopping")


__all__ = ["run_futures_oi_loop", "sweep_once"]
