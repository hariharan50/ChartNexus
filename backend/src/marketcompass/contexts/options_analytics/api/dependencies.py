"""Per-request assembly for the Open Interest routes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.options_analytics.application.oi_service import GetOiView
from marketcompass.infrastructure.analytics.oi_chain_source import SqlAlchemySnapshotReader
from marketcompass.infrastructure.brokers.oi_chain_provider import build_oi_chain_provider
from marketcompass.infrastructure.transport.http.dependencies import (
    get_container,
    get_session,
)


@dataclass(slots=True)
class OptionsAnalyticsServices:
    oi_view: GetOiView


def build_options_analytics_services(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OptionsAnalyticsServices:
    container = get_container(request)
    provider = build_oi_chain_provider(session=session, container=container)
    return OptionsAnalyticsServices(
        oi_view=GetOiView(
            provider=provider,
            snapshots=SqlAlchemySnapshotReader(session),
            strike_span=container.settings.market.snapshot_max_series_strikes,
        ),
    )


Services = Annotated[OptionsAnalyticsServices, Depends(build_options_analytics_services)]
