"""Composition bridge for the futures-analytics context.

The one module that context imports from infrastructure. Keeps the broker
resolver, the mock fallback and the instrument catalog out of the context
itself, the same way the AI agents' bridges do.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.futures_analytics.application.get_dashboard import (
    GetFuturesDashboard,
)
from marketcompass.contexts.futures_analytics.application.get_price_oi_series import (
    GetFuturesPriceOiSeries,
)
from marketcompass.contexts.futures_analytics.application.ports import ExpiryOption
from marketcompass.infrastructure.brokers.fyers.quota_manager import QuotaPolicy
from marketcompass.infrastructure.brokers.mock.provider import MockMarketDataProvider
from marketcompass.infrastructure.brokers.provider_resolver import TenantProviderResolver
from marketcompass.infrastructure.futures.board_source import CatalogFuturesBoardSource
from marketcompass.infrastructure.futures.oi_cache import RedisOpenInterestCache
from marketcompass.infrastructure.persistence.postgresql.repositories.integration.broker_connection_repository import (
    SqlAlchemyBrokerConnectionRepository,
)
from marketcompass.infrastructure.persistence.postgresql.repositories.market_data.futures_board_snapshot_repository import (
    SqlAlchemyFuturesBoardSnapshotRepository,
)
from marketcompass.infrastructure.time.clock import SystemClock
from marketcompass.shared_kernel.types.identifiers import TenantId


@dataclass(slots=True)
class FuturesServices:
    """What the futures routes are handed per request.

    Defined here rather than beside the routes so that the context's
    ``api.dependencies`` can import it from the bridge without the bridge
    having to import back — the same shape ``build_report`` uses.
    """

    dashboard: GetFuturesDashboard
    price_oi_series: GetFuturesPriceOiSeries
    #: The contract series the board can be drawn for. Handed over as the
    #: source's own bound method rather than a use case: it reads the catalog
    #: and returns it, and wrapping that in an application object would add a
    #: layer with nothing in it.
    expiries: Callable[[TenantId], Awaitable[list[ExpiryOption]]]


def build_futures_services(container: Any, session: AsyncSession) -> FuturesServices:
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

    source = CatalogFuturesBoardSource(
        resolver,
        MockMarketDataProvider(clock),
        # Filled by the background sweep; the board reads it, never writes.
        oi_cache=RedisOpenInterestCache(
            container.redis, ttl_seconds=settings.futures_oi.ttl_seconds
        ),
    )
    return FuturesServices(
        dashboard=GetFuturesDashboard(source=source),
        expiries=source.expiries,
        price_oi_series=GetFuturesPriceOiSeries(
            history=SqlAlchemyFuturesBoardSnapshotRepository(session),
            # The board is the fallback when the archive holds no session yet,
            # so the page can still say where the contract stands.
            board=source,
        ),
    )
