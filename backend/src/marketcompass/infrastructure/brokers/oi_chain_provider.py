"""Bridges the Open Interest use case to the broker/market-data adapters.

``options_analytics`` may not import ``market_data`` — so, exactly like
``provider_resolver`` does for the other direction, this module lives outside
``infrastructure.analytics`` (which import-linter can see into) and satisfies
the ``ChainProvider`` port by resolving the tenant's market-data provider and
translating its canonical option chain into the pure ``ChainRow`` values the
analytics domain speaks.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.market_data.application.ports import ProviderResolver
from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.contexts.market_data.domain.market_data import OptionChain
from marketcompass.contexts.options_analytics.application.ports import ChainProvider, ProviderChain
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


class BrokerChainProvider:
    """Implements the analytics ``ChainProvider`` port over the broker resolver."""

    def __init__(self, *, resolver: ProviderResolver, fallback: MockMarketDataProvider) -> None:
        self._resolver = resolver
        self._fallback = fallback

    async def fetch(self, tenant_id: TenantId, symbol: str) -> ProviderChain:
        instrument = InstrumentSymbol.parse(symbol)
        provider = await self._resolver.resolve(tenant_id)
        try:
            chain = await provider.get_option_chain(instrument)
        except UpstreamError:
            # A live provider that cannot answer degrades to simulated data,
            # matching how the dashboard behaves rather than erroring the page.
            chain = await self._fallback.get_option_chain(instrument)
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


def build_oi_chain_provider(*, session: AsyncSession, container: object) -> ChainProvider:
    """Wire a ``BrokerChainProvider`` the way the market-data routes wire theirs."""
    settings = container.settings  # type: ignore[attr-defined]
    resolver = TenantProviderResolver(
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
    return BrokerChainProvider(resolver=resolver, fallback=MockMarketDataProvider(SystemClock()))
