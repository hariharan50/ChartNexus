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

from chartnexus.contexts.futures_analytics.application.get_dashboard import (
    GetFuturesDashboard,
)
from chartnexus.contexts.futures_analytics.application.get_price_oi_series import (
    GetFuturesPriceOiSeries,
)
from chartnexus.contexts.futures_analytics.application.ports import ExpiryOption
from chartnexus.infrastructure.brokers.mock.provider import MockMarketDataProvider
from chartnexus.infrastructure.brokers.provider_resolver import build_provider_resolver
from chartnexus.infrastructure.futures.board_source import CatalogFuturesBoardSource
from chartnexus.infrastructure.futures.oi_cache import RedisOpenInterestCache
from chartnexus.infrastructure.persistence.postgresql.repositories.integration.broker_connection_repository import (
    SqlAlchemyBrokerConnectionRepository,
)
from chartnexus.infrastructure.persistence.postgresql.repositories.market_data.futures_board_snapshot_repository import (
    SqlAlchemyFuturesBoardSnapshotRepository,
)
from chartnexus.infrastructure.time.clock import SystemClock
from chartnexus.shared_kernel.types.identifiers import TenantId


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

    resolver = build_provider_resolver(
        container, SqlAlchemyBrokerConnectionRepository(session, container.token_cipher)
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
