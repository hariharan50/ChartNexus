"""Per-request assembly for the Open Interest routes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.options_analytics.application.gex_service import GetGex
from marketcompass.contexts.options_analytics.application.greeks_series_service import (
    GetGreeksSeries,
)
from marketcompass.contexts.options_analytics.application.iv_history_service import (
    GetIvHistory,
)
from marketcompass.contexts.options_analytics.application.max_pain_series_service import (
    GetMaxPainSeries,
)
from marketcompass.contexts.options_analytics.application.oi_series_service import GetOiSeries
from marketcompass.contexts.options_analytics.application.oi_service import GetOiView
from marketcompass.contexts.options_analytics.application.pcr_series_service import GetPcrSeries
from marketcompass.contexts.options_analytics.application.price_oi_series_service import (
    GetPriceOiSeries,
)
from marketcompass.contexts.options_analytics.application.skew_series_service import GetSkew
from marketcompass.contexts.options_analytics.application.smart_oi_service import GetSmartOi
from marketcompass.contexts.options_analytics.application.straddle_series_service import (
    GetStraddleSeries,
)
from marketcompass.contexts.options_analytics.application.strike_series_service import (
    GetStrikeSeries,
)
from marketcompass.contexts.options_analytics.application.term_structure_service import (
    GetTermStructure,
)
from marketcompass.contexts.options_analytics.application.vega_series_service import GetVega
from marketcompass.infrastructure.analytics.daily_iv_source import SqlAlchemyDailyIvReader
from marketcompass.infrastructure.analytics.oi_chain_source import SqlAlchemySnapshotReader
from marketcompass.infrastructure.brokers.oi_chain_provider import (
    build_index_candle_source,
    build_oi_chain_provider,
)
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
    max_pain_series: GetMaxPainSeries
    gex: GetGex
    iv_history: GetIvHistory
    greeks_series: GetGreeksSeries
    skew: GetSkew
    term_structure: GetTermStructure
    vega: GetVega
    straddle_series: GetStraddleSeries
    strike_series: GetStrikeSeries
    smart_oi: GetSmartOi


def build_options_analytics_services(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OptionsAnalyticsServices:
    return build_options_analytics_services_from(get_container(request), session)


def build_options_analytics_services_from(
    container: Any, session: AsyncSession
) -> OptionsAnalyticsServices:
    """Assemble the OI services from a container + session, with no request.

    Mirrors ``build_market_services_from``: the request-scoped builder wraps this,
    and a worker with a ``Container`` but no request uses it directly.
    """
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
        max_pain_series=GetMaxPainSeries(provider=provider, snapshots=snapshots),
        gex=GetGex(
            provider=provider,
            snapshots=snapshots,
            strike_span=container.settings.market.snapshot_max_series_strikes,
        ),
        iv_history=GetIvHistory(readings=SqlAlchemyDailyIvReader(session)),
        greeks_series=GetGreeksSeries(provider=provider, snapshots=snapshots),
        term_structure=GetTermStructure(provider=provider),
        skew=GetSkew(
            provider=provider,
            snapshots=snapshots,
            strike_span=container.settings.market.snapshot_max_series_strikes,
        ),
        vega=GetVega(
            provider=provider,
            snapshots=snapshots,
            strike_span=container.settings.market.snapshot_max_series_strikes,
        ),
        straddle_series=GetStraddleSeries(
            provider=provider,
            snapshots=snapshots,
            strike_span=container.settings.market.snapshot_max_series_strikes,
        ),
        strike_series=GetStrikeSeries(
            provider=provider,
            snapshots=snapshots,
            strike_span=container.settings.market.snapshot_max_series_strikes,
        ),
        smart_oi=GetSmartOi(
            provider=provider,
            snapshots=snapshots,
            candles=build_index_candle_source(session=session, container=container),
        ),
    )


Services = Annotated[OptionsAnalyticsServices, Depends(build_options_analytics_services)]
