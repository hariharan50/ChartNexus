"""Per-request assembly for the Open Interest routes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.options_analytics.application.gex_service import GetGex
from marketcompass.contexts.options_analytics.application.oi_series_service import GetOiSeries
from marketcompass.contexts.options_analytics.application.oi_service import GetOiView
from marketcompass.contexts.options_analytics.application.pcr_series_service import GetPcrSeries
from marketcompass.contexts.options_analytics.application.price_oi_series_service import (
    GetPriceOiSeries,
)
from marketcompass.infrastructure.analytics.oi_chain_source import SqlAlchemySnapshotReader
from marketcompass.infrastructure.brokers.oi_chain_provider import build_oi_chain_provider
from marketcompass.infrastructure.transport.http.dependencies import (
    get_container,
    get_session,
)


@dataclass(slots=True)
class OptionsAnalyticsServices:
    oi_view: GetOiView
    oi_series: GetOiSeries
    price_oi_series: GetPriceOiSeries
    pcr_series: GetPcrSeries
    gex: GetGex


def build_options_analytics_services(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OptionsAnalyticsServices:
    container = get_container(request)
    provider = build_oi_chain_provider(session=session, container=container)
    snapshots = SqlAlchemySnapshotReader(session)
    return OptionsAnalyticsServices(
        oi_view=GetOiView(
            provider=provider,
            snapshots=snapshots,
            strike_span=container.settings.market.snapshot_max_series_strikes,
        ),
        oi_series=GetOiSeries(provider=provider, snapshots=snapshots),
        price_oi_series=GetPriceOiSeries(provider=provider, snapshots=snapshots),
        pcr_series=GetPcrSeries(provider=provider, snapshots=snapshots),
        gex=GetGex(
            provider=provider,
            snapshots=snapshots,
            strike_span=container.settings.market.snapshot_max_series_strikes,
        ),
    )


Services = Annotated[OptionsAnalyticsServices, Depends(build_options_analytics_services)]
