"""Adapters that feed the option-chain snapshot writer.

``market_ingestion`` may not import ``market_data`` — so, exactly like
``provider_resolver`` and ``oi_chain_source`` do for their consumers, this
infrastructure module is the seam. ``ProviderChainSource`` satisfies the
``ChainSource`` port by resolving a broker provider and translating its canonical
``OptionChain`` into the ingest context's own ``ChainObservation``.

Snapshots are market-wide, so the source resolves under *any* tenant that holds
an active FYERS connection (``find_any_active``). When none exists it falls back
to the mock provider and stamps the observation ``mock``; the use case then
decides whether that is worth persisting.
"""

from __future__ import annotations

from chartnexus.contexts.broker_connections.domain.value_objects import BrokerName
from chartnexus.contexts.market_data.application.ports import (
    MarketDataProvider,
    ProviderResolver,
)
from chartnexus.contexts.market_data.domain.implied_volatility import backfill_implied_volatility
from chartnexus.contexts.market_data.domain.instruments import InstrumentSymbol
from chartnexus.contexts.market_data.domain.market_data import (
    DataSource,
    OptionChain,
    StrikeRow,
)
from chartnexus.contexts.market_ingestion.application.capture import CaptureChainSnapshots
from chartnexus.contexts.market_ingestion.application.ports import (
    ChainObservation,
    ChainRowToWrite,
)
from chartnexus.infrastructure.brokers.fyers.quota_manager import QuotaPolicy
from chartnexus.infrastructure.brokers.mock.provider import MockMarketDataProvider
from chartnexus.infrastructure.brokers.provider_resolver import TenantProviderResolver
from chartnexus.infrastructure.persistence.postgresql.repositories.integration.broker_connection_repository import (
    SqlAlchemyBrokerConnectionRepository,
)
from chartnexus.infrastructure.persistence.postgresql.repositories.market_data.option_chain_snapshot_repository import (
    SqlAlchemyOptionChainSnapshotRepository,
)
from chartnexus.infrastructure.time.clock import SystemClock
from chartnexus.infrastructure.time.market_calendar import ExchangeCalendar
from chartnexus.shared_kernel.domain.errors import UpstreamError
from chartnexus.shared_kernel.types.identifiers import TenantId


class ProviderChainSource:
    """Implements ``market_ingestion``'s ``ChainSource`` over the broker resolver."""

    def __init__(
        self,
        *,
        resolver: ProviderResolver,
        connections: SqlAlchemyBrokerConnectionRepository,
        fallback: MockMarketDataProvider,
        risk_free_rate: float = 0.07,
    ) -> None:
        self._resolver = resolver
        self._connections = connections
        self._fallback = fallback
        self._risk_free_rate = risk_free_rate

    async def expiries(self, symbol: str) -> tuple[str, ...]:
        """The instrument's listed expiries, nearest first.

        Empty when the symbol is unknown or the provider cannot list them; the
        caller then falls back to capturing whatever the chain resolves to.
        """
        try:
            instrument = InstrumentSymbol.parse(symbol)
        except Exception:
            return ()

        provider = await self._resolve_provider()
        try:
            listed = await provider.get_expiries(instrument)
        except UpstreamError:
            return ()
        return tuple(listed.expiries)

    async def fetch(self, symbol: str, *, expiry: str | None = None) -> ChainObservation | None:
        try:
            instrument = InstrumentSymbol.parse(symbol)
        except Exception:
            return None

        provider = await self._resolve_provider()
        try:
            chain = await provider.get_option_chain(instrument, expiry=expiry)
        except UpstreamError:
            # A live provider that cannot answer degrades to simulated data,
            # which the use case then declines to store (unless mock is allowed).
            chain = await self._fallback.get_option_chain(instrument, expiry=expiry)

        # So the archive actually has IV to draw on later — FYERS never quotes
        # it, and without this every stored row's `iv` would be permanently null.
        chain = backfill_implied_volatility(
            chain, valuation_time=chain.provenance.fetched_at, risk_free_rate=self._risk_free_rate
        )

        return _to_observation(symbol, chain)

    async def _resolve_provider(self) -> MarketDataProvider:
        connection = await self._connections.find_any_active(BrokerName.FYERS)
        if connection is None:
            return self._fallback
        return await self._resolver.resolve(TenantId(connection.tenant_id))


def _to_observation(symbol: str, chain: OptionChain) -> ChainObservation:
    rows: list[ChainRowToWrite] = []
    for strike_row in chain.strikes:
        rows.extend(_legs(strike_row))

    source = "mock" if chain.provenance.source is DataSource.MOCK else "live"
    return ChainObservation(
        symbol=symbol,
        captured_at=chain.provenance.fetched_at,
        spot=chain.spot_price,
        rows=tuple(rows),
        source=source,
        expiry=chain.expiry,
        future_price=chain.future_price,
        lot_size=chain.lot_size,
    )


def _legs(strike_row: StrikeRow) -> list[ChainRowToWrite]:
    legs: list[ChainRowToWrite] = []
    if strike_row.call is not None:
        legs.append(_leg(strike_row.strike, "CE", strike_row.call))
    if strike_row.put is not None:
        legs.append(_leg(strike_row.strike, "PE", strike_row.put))
    return legs


def _leg(strike: object, option_type: str, quote: object) -> ChainRowToWrite:
    # ``quote`` is a market_data OptionQuote; read structurally to keep that type
    # out of the ingest context's shapes.
    return ChainRowToWrite(
        strike=strike,  # type: ignore[arg-type]
        option_type=option_type,
        oi=int(getattr(quote, "open_interest", 0)),
        oi_change=int(getattr(quote, "open_interest_change", 0)),
        volume=int(getattr(quote, "volume", 0)),
        ltp=getattr(quote, "last_price", None),
        iv=getattr(quote, "implied_volatility", None),
        delta=getattr(quote, "delta", None),
    )


def build_ingest_service(
    *,
    session: object,
    container: object,
    symbols: tuple[str, ...],
    allow_mock: bool,
) -> CaptureChainSnapshots:
    """Wire ``CaptureChainSnapshots`` the way the market-data routes wire theirs."""
    settings = container.settings  # type: ignore[attr-defined]
    clock = SystemClock()
    connections = SqlAlchemyBrokerConnectionRepository(
        session,  # type: ignore[arg-type]
        container.token_cipher,  # type: ignore[attr-defined]
    )
    resolver = TenantProviderResolver(
        connections=connections,
        http=container.http,  # type: ignore[attr-defined]
        redis=container.redis,  # type: ignore[attr-defined]
        rest_base_url=settings.broker.rest_base_url,
        quota=QuotaPolicy(
            requests_per_second=settings.broker.quota_requests_per_second,
            requests_per_day=settings.broker.quota_requests_per_day,
        ),
        request_timeout_seconds=settings.broker.request_timeout_seconds,
        circuit_breaker_failure_threshold=settings.broker.circuit_breaker_failure_threshold,
        circuit_breaker_reset_seconds=settings.broker.circuit_breaker_reset_seconds,
    )
    fallback = MockMarketDataProvider(clock)
    source = ProviderChainSource(
        resolver=resolver,
        connections=connections,
        fallback=fallback,
        risk_free_rate=settings.market.risk_free_rate,
    )
    writer = SqlAlchemyOptionChainSnapshotRepository(session)  # type: ignore[arg-type]
    calendar = ExchangeCalendar(
        timezone=settings.market.timezone,
        session_open=settings.market.session_open,
        session_close=settings.market.session_close,
    )
    return CaptureChainSnapshots(
        source=source,
        writer=writer,
        calendar=calendar,
        clock=clock,
        symbols=symbols,
        allow_mock=allow_mock,
        expiries=settings.market.ingest_expiries,
    )
