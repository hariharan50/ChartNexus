"""Composition bridge for the market-breadth context.

The one module that context imports from infrastructure, the same shape
``build_futures`` uses. It keeps the broker resolver, the instrument catalog,
the weight table and the flow placeholder out of the context itself.

The index source is built on the **same** ``CatalogFuturesBoardSource`` the
Future Dashboard uses, deliberately: an Analysis page open beside the
dashboard then shares its board read rather than opening a second one against
the shared daily quota.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.market_breadth.application.get_breadth_series import (
    GetBreadthSeries,
    GetSectorRail,
)
from marketcompass.contexts.market_breadth.application.get_fii_dii import (
    GetFiiDiiCashHistory,
    GetFiiDiiSummary,
)
from marketcompass.contexts.market_breadth.application.get_index_analysis import (
    GetAdvanceDecline,
    GetIndexContributors,
    GetIndexWeightage,
    GetSectorRotation,
)
from marketcompass.contexts.market_breadth.application.ports import (
    BreadthHistorySource,
    BreadthUniverseSource,
    InstitutionalFlowSource,
)
from marketcompass.infrastructure.breadth.breadth_history_source import (
    ArchiveBreadthHistorySource,
    CatalogBreadthUniverseSource,
)
from marketcompass.infrastructure.breadth.constituent_source import (
    BoardIndexConstituentSource,
)
from marketcompass.infrastructure.breadth.flow_source import (
    SimulatedInstitutionalFlowSource,
)
from marketcompass.infrastructure.breadth.nse.flow_source import (
    NseInstitutionalFlowSource,
)
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


@dataclass(slots=True)
class BreadthServices:
    """What the market-breadth routes are handed per request."""

    fii_dii_summary: GetFiiDiiSummary
    fii_dii_cash: GetFiiDiiCashHistory
    contributors: GetIndexContributors
    advance_decline: GetAdvanceDecline
    #: Breadth through a session, and the rail it is picked from. Both read the
    #: captured futures board rather than any breadth store, which does not
    #: exist — see `breadth_history_source`.
    breadth_series: GetBreadthSeries
    sector_rail: GetSectorRail
    weightage: GetIndexWeightage
    sector_rotation: GetSectorRotation
    #: Which indices the constituent source can actually answer for. Exposed as
    #: a callable rather than a list so the routes validate against the live
    #: table instead of a copy that can drift from it.
    indices: Callable[[], tuple[str, ...]]

    @classmethod
    def of(
        cls,
        index_source: BoardIndexConstituentSource,
        flow_source: InstitutionalFlowSource,
        history: BreadthHistorySource,
        universe: BreadthUniverseSource,
    ) -> BreadthServices:
        return cls(
            # The Summary page prints the benchmark beside the session, so it
            # gets the index source too — used only for the latest session.
            fii_dii_summary=GetFiiDiiSummary(source=flow_source, index=index_source),
            fii_dii_cash=GetFiiDiiCashHistory(source=flow_source),
            contributors=GetIndexContributors(source=index_source),
            breadth_series=GetBreadthSeries(history=history, universe=universe),
            sector_rail=GetSectorRail(
                universe=universe,
                history=history,
                indices=index_source.universe(),
            ),
            advance_decline=GetAdvanceDecline(source=index_source),
            weightage=GetIndexWeightage(source=index_source),
            sector_rotation=GetSectorRotation(source=index_source),
            indices=index_source.universe,
        )


def build_breadth_services(container: Any, session: AsyncSession) -> BreadthServices:
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

    board = CatalogFuturesBoardSource(
        resolver,
        MockMarketDataProvider(clock),
        oi_cache=RedisOpenInterestCache(
            container.redis, ttl_seconds=settings.futures_oi.ttl_seconds
        ),
    )
    return BreadthServices.of(
        index_source=BoardIndexConstituentSource(board),
        # The breadth series is counted out of the futures-board archive; the
        # rail is counted off the same board read the dashboard already makes.
        history=ArchiveBreadthHistorySource(SqlAlchemyFuturesBoardSnapshotRepository(session)),
        universe=CatalogBreadthUniverseSource(board),
        # NSE's own published files, with the generator behind it for when the
        # archive cannot be reached — an offline developer, or an outage. The
        # badge on the page says which of the two answered, every time.
        flow_source=NseInstitutionalFlowSource(
            container.http,
            container.redis,
            fallback=SimulatedInstitutionalFlowSource(clock),
            clock=clock,
        ),
    )
