"""The futures board, assembled from the catalog and the broker.

Implements ``FuturesBoardSource``. This is the sanctioned bridge: the
``futures_analytics`` context owns the maths and declares the port, and this
adapter is the only thing that knows the catalog and the market-data provider
both exist.

The comparison baseline is the **previous close** — the contract's own prior
settlement price and open interest, as the broker reports them. That makes the
dashboard's percentages day-over-day, which is what a futures board means by
"up 3.8%", and it needs no stored history to produce.

Intraday comparison windows (the reference UI's 3m / 5m / 15m / 1h options) are
a different question that this source deliberately does not answer: they need a
snapshot archive of the board, which does not exist yet. Better to serve the
one window we can compute honestly than to fake four more.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from decimal import Decimal

from marketcompass.contexts.futures_analytics.application.ports import BoardSnapshot
from marketcompass.contexts.futures_analytics.domain.buildup import FuturesReading
from marketcompass.contexts.market_data.application.ports import (
    MarketDataProvider,
    ProviderResolver,
)
from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.contexts.market_data.domain.market_data import DataSource, FuturesQuote
from marketcompass.infrastructure.brokers.mock.provider import (
    PROVIDER_NAME as MOCK_PROVIDER_NAME,
)
from marketcompass.infrastructure.catalog import registry
from marketcompass.infrastructure.futures.oi_cache import RedisOpenInterestCache
from marketcompass.infrastructure.observability.structured_logging import get_logger
from marketcompass.shared_kernel.types.identifiers import TenantId

log = get_logger(__name__)


class CatalogFuturesBoardSource:
    """Implements the ``FuturesBoardSource`` port."""

    def __init__(
        self,
        resolver: ProviderResolver,
        fallback: MarketDataProvider,
        oi_cache: RedisOpenInterestCache | None = None,
    ) -> None:
        self._resolver = resolver
        self._fallback = fallback
        # Optional so a caller without Redis still gets a board — minus the
        # open-interest columns, which is the honest degradation.
        self._oi_cache = oi_cache

    async def read(self, tenant_id: TenantId) -> BoardSnapshot:
        instruments = [
            InstrumentSymbol(instrument.symbol) for instrument in registry.current().all()
        ]
        if not instruments:
            log.warning("futures_board_empty_catalog")
            return BoardSnapshot()

        provider = await self._resolve(tenant_id)
        readings, expiry = await self._read_from(provider, instruments)

        # Whether this is real data is decided by what the provider *is*, not by
        # which object we happen to hold. The resolver builds its own mock when
        # a tenant has no usable broker connection, so an identity check against
        # our fallback silently labelled generated numbers as live — the one
        # mistake this app's provenance rule exists to prevent.
        source = DataSource.MOCK if _is_mock(provider) else DataSource.LIVE

        # Open interest arrives from the background sweep, not from the quote
        # that produced these rows: the endpoint carrying it takes one contract
        # per request, so it cannot ride along with a whole-universe read.
        #
        # Only ever merged onto a live board. The sweep's figures are real, and
        # pairing them with generated prices would classify a simulated move
        # against an observed one — a build-up state derived from two unrelated
        # worlds, presented with the same confidence as a true one. A mock
        # board carries the mock's own open interest, which at least agrees
        # with the prices beside it.
        if self._oi_cache is not None and source is DataSource.LIVE:
            readings = await self._merge_open_interest(readings)

        # Degrade to the mock when a real broker gave us nothing usable.
        #
        # Without this the page simply renders empty, which is the worst of both
        # worlds: a tenant *with* a broker connection gets a blank board the
        # moment their token lapses or the market is shut, while a tenant with
        # no broker at all sees a full one. An empty board is not a market
        # observation, and every other market-data read in this app degrades
        # rather than showing nothing.
        if not readings and source is DataSource.LIVE:
            log.warning(
                "futures_board_degraded",
                reason="broker_returned_nothing",
                requested=len(instruments),
            )
            readings, expiry = await self._read_from(self._fallback, instruments)
            source = DataSource.MOCK

        log.info(
            "futures_board_read",
            requested=len(instruments),
            usable=len(readings),
            source=source.value,
        )
        return BoardSnapshot(
            readings=readings,
            universe=len(instruments),
            source=source.value,
            expiry=expiry,
        )

    async def _merge_open_interest(
        self, readings: list[FuturesReading]
    ) -> list[FuturesReading]:
        if not readings or self._oi_cache is None:
            return readings

        cached = await self._oi_cache.read_all()
        if not cached:
            return readings

        merged = [
            replace(
                reading,
                open_interest=entry.open_interest,
                open_interest_open=entry.previous_open_interest,
            )
            if (entry := cached.get(reading.symbol)) is not None
            else reading
            for reading in readings
        ]
        log.info("futures_board_open_interest_merged", matched=len(cached), rows=len(merged))
        return merged

    async def _read_from(
        self, provider: MarketDataProvider, instruments: list[InstrumentSymbol]
    ) -> tuple[list[FuturesReading], str | None]:
        try:
            board = await provider.get_futures_board(instruments)
        except Exception as exc:
            log.warning("futures_board_fetch_failed", error=repr(exc))
            return [], None

        readings = [
            reading
            for symbol, quote in board.items()
            if (reading := _to_reading(symbol, quote)) is not None
        ]
        # No board-wide expiry: NSE and BSE settle on different days, so one
        # date would be wrong for part of the universe. Each reading carries
        # its own and the caller derives whatever the view needs.
        return readings, _modal_expiry(readings)

    async def _resolve(self, tenant_id: TenantId) -> MarketDataProvider:
        """The tenant's broker, or the mock when they have not connected one."""
        try:
            return await self._resolver.resolve(tenant_id)
        except Exception as exc:
            log.warning("futures_board_provider_unavailable", error=repr(exc))
            return self._fallback


def _modal_expiry(readings: list[FuturesReading]) -> str | None:
    """The expiry most of these contracts share."""
    counts = Counter(r.expiry for r in readings if r.expiry)
    return counts.most_common(1)[0][0] if counts else None


def _is_mock(provider: MarketDataProvider) -> bool:
    """Whether this provider generates its data rather than observing it."""
    return provider.name == MOCK_PROVIDER_NAME


def _to_reading(symbol: InstrumentSymbol, quote: FuturesQuote) -> FuturesReading | None:
    """A quote becomes a reading if it carries a price and something to
    measure that price against.

    Open interest is **not** required. It is needed to classify a build-up, and
    a row without it is reported NEUTRAL rather than guessed at — but a feed
    that omits OI still carries a perfectly good price, and discarding the
    whole row for want of one column is what silently replaced an entire live
    board with simulated data.
    """
    row = registry.current().find(symbol)

    baseline = quote.previous_close
    if baseline is None or baseline == 0:
        # Fall back to reconstructing it from the reported day change, which is
        # the same number by a different route.
        if quote.change is None:
            return None
        baseline = quote.price - quote.change

    return FuturesReading(
        symbol=str(symbol),
        price=quote.price,
        price_open=Decimal(baseline),
        open_interest=quote.open_interest,
        open_interest_open=quote.previous_open_interest,
        name=row.name if row else None,
        kind=row.kind.value if row else None,
        expiry=quote.expiry or None,
        lot_size=row.lot_size if row else None,
        volume=quote.volume,
        volume_open=quote.previous_volume,
        day_open=quote.day_open,
        day_high=quote.day_high,
        day_low=quote.day_low,
        sector=row.sector if row else None,
    )
