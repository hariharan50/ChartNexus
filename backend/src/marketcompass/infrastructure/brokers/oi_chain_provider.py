"""Bridges the Options Lab use cases to the broker/market-data adapters.

``options_analytics`` may not import ``market_data`` — so, exactly like
``provider_resolver`` does for the other direction, this module lives outside
``infrastructure.analytics`` (which import-linter can see into) and satisfies
the analytics ports by resolving the tenant's market-data provider and
translating its canonical types into the pure values the analytics domain
speaks.

Two ports, one resolver: ``ChainProvider`` (the option chain) and
``CandleSource`` (the underlying's price bars). They are different upstream
calls but the same tenant, the same credentials and the same degrade-to-mock
rule, so they share the wiring rather than each building their own.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.market_data.application.ports import ProviderResolver
from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.contexts.market_data.domain.market_data import CandleInterval, OptionChain
from marketcompass.contexts.options_analytics.application.ports import (
    Candle,
    CandleSource,
    ChainProvider,
    ProviderChain,
)
from marketcompass.contexts.options_analytics.domain.oi_math import ChainRow
from marketcompass.infrastructure.brokers.fyers.quota_manager import QuotaPolicy
from marketcompass.infrastructure.brokers.mock.provider import MockMarketDataProvider
from marketcompass.infrastructure.brokers.provider_resolver import TenantProviderResolver
from marketcompass.infrastructure.persistence.postgresql.repositories.integration.broker_connection_repository import (
    SqlAlchemyBrokerConnectionRepository,
)
from marketcompass.infrastructure.time.clock import SystemClock
from marketcompass.shared_kernel.domain.errors import UpstreamError
from marketcompass.shared_kernel.types.identifiers import TenantId

# India observes no DST, so a fixed offset is correct and needs no tzdata. Same
# constant as `application/session.py`, redeclared rather than imported: this
# module is infrastructure and must not depend on a context's internals.
_IST = timezone(timedelta(hours=5, minutes=30))


class BrokerChainProvider:
    """Implements the analytics ``ChainProvider`` port over the broker resolver."""

    def __init__(self, *, resolver: ProviderResolver, fallback: MockMarketDataProvider) -> None:
        self._resolver = resolver
        self._fallback = fallback

    async def fetch(
        self, tenant_id: TenantId, symbol: str, *, expiry: str | None = None
    ) -> ProviderChain:
        instrument = InstrumentSymbol.parse(symbol)
        provider = await self._resolver.resolve(tenant_id)
        try:
            chain = await provider.get_option_chain(instrument, expiry)
        except UpstreamError:
            # A live provider that cannot answer degrades to simulated data,
            # matching how the dashboard behaves rather than erroring the page.
            chain = await self._fallback.get_option_chain(instrument, expiry)
        return _to_provider_chain(chain)


def _to_provider_chain(chain: OptionChain) -> ProviderChain:
    rows: list[ChainRow] = []
    for row in chain.strikes:
        strike = float(row.strike)
        if row.call is not None:
            rows.append(_to_row(strike, "CE", row.call))
        if row.put is not None:
            rows.append(_to_row(strike, "PE", row.put))
    return ProviderChain(
        rows=tuple(rows),
        spot=float(chain.spot_price),
        lot_size=chain.lot_size,
        expiry=chain.expiry,
    )


def _to_row(strike: float, option_type: str, leg: object) -> ChainRow:
    # ``leg`` is a market_data OptionQuote; read structurally to avoid leaking
    # that type into the analytics domain signature.
    return ChainRow(
        strike=strike,
        option_type=option_type,
        oi=int(getattr(leg, "open_interest", 0)),
        oi_change=int(getattr(leg, "open_interest_change", 0)),
        ltp=float(getattr(leg, "last_price", 0) or 0),
        volume=int(getattr(leg, "volume", 0)),
        iv=_opt_float(getattr(leg, "implied_volatility", None)),
    )


def _opt_float(value: object) -> float | None:
    return None if value is None else float(value)  # type: ignore[arg-type]


class BrokerCandleSource:
    """Implements the analytics ``CandleSource`` port over the broker resolver."""

    def __init__(self, *, resolver: ProviderResolver, fallback: MockMarketDataProvider) -> None:
        self._resolver = resolver
        self._fallback = fallback

    async def minute_candles(
        self, tenant_id: TenantId, symbol: str, *, trade_date_utc: datetime
    ) -> list[Candle]:
        instrument = InstrumentSymbol.parse(symbol)
        # The provider counts back from today, so a past session is reached by
        # asking for enough days to cover it and then keeping only that date.
        # Clamped to what the resolution allows: a request beyond `max_days` is
        # rejected upstream rather than trimmed, which would blank the pane on
        # exactly the days someone is trying to look back at.
        wanted = _ist_date(trade_date_utc)
        span = (_ist_date(datetime.now(UTC)) - wanted).days + 1
        days = max(1, min(CandleInterval.M1.max_days, span))

        provider = await self._resolver.resolve(tenant_id)
        try:
            series = await provider.get_history(instrument, CandleInterval.M1, days)
        except UpstreamError:
            series = await self._fallback.get_history(instrument, CandleInterval.M1, days)
        return _to_candles(series, wanted)


def _to_candles(series: object, wanted: date) -> list[Candle]:
    # `series` is a market_data CandleSeries; read structurally so that type
    # does not leak into an analytics-facing signature.
    bars: list[Candle] = []
    for bar in getattr(series, "candles", ()):
        opened_at = _attach_utc(bar.opened_at)
        if _ist_date(opened_at) != wanted:
            continue
        bars.append(
            Candle(
                opened_at=opened_at,
                open=float(bar.open),
                high=float(bar.high),
                low=float(bar.low),
                close=float(bar.close),
            )
        )
    bars.sort(key=lambda candle: candle.opened_at)
    return bars


def _attach_utc(moment: datetime) -> datetime:
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment


def _ist_date(moment: datetime) -> date:
    """The trading date an instant belongs to. India observes no DST."""
    return _attach_utc(moment).astimezone(_IST).date()


def _build_resolver(*, session: AsyncSession, container: object) -> ProviderResolver:
    """The tenant provider resolver, wired the way the market-data routes wire theirs."""
    settings = container.settings  # type: ignore[attr-defined]
    return TenantProviderResolver(
        connections=SqlAlchemyBrokerConnectionRepository(
            session,
            container.token_cipher,  # type: ignore[attr-defined]
        ),
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


def build_oi_chain_provider(*, session: AsyncSession, container: object) -> ChainProvider:
    """Wire a ``BrokerChainProvider`` the way the market-data routes wire theirs."""
    return BrokerChainProvider(
        resolver=_build_resolver(session=session, container=container),
        fallback=MockMarketDataProvider(SystemClock()),
    )


def build_index_candle_source(*, session: AsyncSession, container: object) -> CandleSource:
    """Wire a ``BrokerCandleSource`` over the same resolver the chain uses."""
    return BrokerCandleSource(
        resolver=_build_resolver(session=session, container=container),
        fallback=MockMarketDataProvider(SystemClock()),
    )
