"""The open-interest sweep, shared by every caller that runs it.

Lives in entrypoints — not infrastructure — because it wires a ``Container``,
which adapters are forbidden to import. The same loop runs from the standalone
``marketcompass-futures-oi`` process and, in local development only, as a
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

from marketcompass.bootstrap.container import Container
from marketcompass.bootstrap.settings import Settings
from marketcompass.contexts.broker_connections.domain.value_objects import BrokerName
from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.infrastructure.brokers.futures_contract import MAX_SERIES
from marketcompass.infrastructure.brokers.fyers.quota_manager import QuotaPolicy
from marketcompass.infrastructure.brokers.provider_resolver import TenantProviderResolver
from marketcompass.infrastructure.catalog import registry
from marketcompass.infrastructure.futures.oi_cache import (
    CachedOpenInterest,
    RedisOpenInterestCache,
)
from marketcompass.infrastructure.observability.structured_logging import get_logger
from marketcompass.infrastructure.persistence.postgresql.repositories.integration.broker_connection_repository import (
    SqlAlchemyBrokerConnectionRepository,
)

log = get_logger(__name__)


async def sweep_once(container: Container, settings: Settings) -> int:
    """One pass over the universe. Never propagates — the loop must survive it.

    Returns how many contracts were priced, so a caller can tell a quiet sweep
    from a broken one.
    """
    try:
        return await _sweep(container, settings)
    except Exception as exc:
        log.error("futures_oi_sweep_failed", error=repr(exc))
        return 0


async def _sweep(container: Container, settings: Settings) -> int:
    instruments = registry.current().symbols()
    if not instruments:
        log.warning("futures_oi_sweep_skipped", reason="empty_catalog")
        return 0

    async with container.database.read_session() as session:
        connections = SqlAlchemyBrokerConnectionRepository(session, container.token_cipher)
        # Open interest is a fact about the market, not about a tenant, so any
        # working connection can fetch it and one sweep serves everybody.
        connection = await connections.find_any_active(BrokerName.FYERS)
        if connection is None:
            log.info("futures_oi_sweep_skipped", reason="no_connected_broker")
            return 0

        resolver = _resolver(container, settings, connections)
        provider = await resolver.resolve(connection.tenant_id)

        delay = 1.0 / max(settings.futures_oi.requests_per_second, 0.1)
        started = datetime.now(UTC)
        depth = min(settings.futures_oi.expiry_depth, MAX_SERIES)

        # Nearest series first, so a sweep that runs out of interval has
        # refreshed the contract almost every page is actually showing. Each
        # series is written to its own cache the moment it completes, for the
        # same reason: a slow far month must not hold back the near one.
        by_series: dict[int, dict[str, CachedOpenInterest]] = {}
        for series in range(depth):
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

    cache = RedisOpenInterestCache(container.redis, ttl_seconds=settings.futures_oi.ttl_seconds)
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


def _resolver(
    container: Container,
    settings: Settings,
    connections: SqlAlchemyBrokerConnectionRepository,
) -> TenantProviderResolver:
    return TenantProviderResolver(
        connections=connections,
        http=container.http,
        redis=container.redis,
        rest_base_url=settings.broker.rest_base_url,
        quota=QuotaPolicy(
            requests_per_second=settings.broker.quota_requests_per_second,
            requests_per_day=settings.broker.quota_requests_per_day,
        ),
        request_timeout_seconds=settings.broker.request_timeout_seconds,
        circuit_breaker_failure_threshold=settings.broker.circuit_breaker_failure_threshold,
        circuit_breaker_reset_seconds=settings.broker.circuit_breaker_reset_seconds,
    )


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
