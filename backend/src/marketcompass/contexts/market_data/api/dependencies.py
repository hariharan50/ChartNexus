"""Per-request assembly for market data routes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.market_data.application.queries import (
    GetExpiries,
    GetFuturesQuote,
    GetHistory,
    GetMarketStatus,
    GetOptionChain,
    GetSpotPrice,
)
from marketcompass.infrastructure.brokers.fyers.quota_manager import QuotaPolicy
from marketcompass.infrastructure.brokers.mock.provider import MockMarketDataProvider
from marketcompass.infrastructure.brokers.provider_resolver import TenantProviderResolver
from marketcompass.infrastructure.cache.redis.iv_history import RedisIvHistoryRecorder
from marketcompass.infrastructure.persistence.postgresql.repositories.integration.broker_connection_repository import (
    SqlAlchemyBrokerConnectionRepository,
)
from marketcompass.infrastructure.persistence.postgresql.repositories.market_data.price_candle_repository import (
    SqlAlchemyPriceCandleRepository,
)
from marketcompass.infrastructure.time.clock import SystemClock
from marketcompass.infrastructure.time.market_calendar import ExchangeCalendar
from marketcompass.infrastructure.transport.http.dependencies import (
    get_container,
    get_session,
)


@dataclass(slots=True)
class MarketServices:
    spot: GetSpotPrice
    futures: GetFuturesQuote
    option_chain: GetOptionChain
    expiries: GetExpiries
    history: GetHistory
    status: GetMarketStatus


def build_market_services(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MarketServices:
    return build_market_services_from(get_container(request), session)


def build_market_services_from(container: Any, session: AsyncSession) -> MarketServices:
    """Assemble the market services from a container + session, with no request.

    The request-scoped ``build_market_services`` above is a thin wrapper over this.
    A background worker (e.g. HUGIN) that has a ``Container`` but no request builds
    the same services through here, so both paths stay identical.
    """
    settings = container.settings
    clock = SystemClock()

    resolver = TenantProviderResolver(
        connections=SqlAlchemyBrokerConnectionRepository(session, container.token_cipher),
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
    fallback = MockMarketDataProvider(clock)
    calendar = ExchangeCalendar(
        timezone=settings.market.timezone,
        session_open=settings.market.session_open,
        session_close=settings.market.session_close,
    )

    return MarketServices(
        spot=GetSpotPrice(resolver=resolver, fallback=fallback, clock=clock),
        futures=GetFuturesQuote(resolver=resolver, fallback=fallback, clock=clock),
        option_chain=GetOptionChain(
            resolver=resolver,
            fallback=fallback,
            clock=clock,
            risk_free_rate=settings.market.risk_free_rate,
            iv_history=RedisIvHistoryRecorder(container.redis),
        ),
        expiries=GetExpiries(resolver=resolver, fallback=fallback, clock=clock),
        history=GetHistory(
            resolver=resolver,
            fallback=fallback,
            clock=clock,
            cache=SqlAlchemyPriceCandleRepository(session),
            cache_retention_days=settings.market.candle_cache_retention_days,
        ),
        status=GetMarketStatus(resolver=resolver, clock=clock, calendar=calendar),
    )


Services = Annotated[MarketServices, Depends(build_market_services)]
