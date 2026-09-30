"""Composition bridge for the pre-market context.

The one module ``contexts/pre_market`` reaches for, and the only place in the
system that knows PMS reads from four other contexts. Same shape as
``build_global`` and ``build_breadth``; the difference is how much it composes,
which is exactly why the indirection earns its keep — swapping any upstream is
a change to ``adapters.py`` and nothing else.

``pyproject.toml`` carries one ``ignore_imports`` entry for the single edge
``contexts.pre_market.api.dependencies -> infrastructure.pre_market.build_pre_market``,
because import-linter follows this module's transitive reach and would
otherwise read it as PMS depending on market_data, options_analytics,
global_markets and market_breadth. The AST boundary test needs no exemption:
``contexts/pre_market`` genuinely imports none of them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.market_data.api.dependencies import (
    build_market_services_from,
)
from marketcompass.contexts.options_analytics.api.dependencies import (
    build_options_analytics_services_from,
)
from marketcompass.contexts.pre_market.application.get_pre_market_view import (
    GetPreMarketView,
)
from marketcompass.infrastructure.breadth.build_breadth import build_breadth_services
from marketcompass.infrastructure.global_markets.build_global import (
    build_global_services,
)
from marketcompass.infrastructure.pre_market.adapters import (
    BreadthAdapter,
    EmptyVixHistory,
    FlowAdapter,
    GlobalCueAdapter,
    MarketCandleAdapter,
    MarketPhaseAdapter,
    MarketSpotAdapter,
    NoNarrative,
    OptionsAdapter,
)
from marketcompass.infrastructure.time.clock import SystemClock
from marketcompass.shared_kernel.types.identifiers import TenantId

__all__ = ["PreMarketServices", "build_pre_market_services"]


@dataclass(frozen=True, slots=True)
class PreMarketServices:
    view: GetPreMarketView


def build_pre_market_services(
    container: Any, session: AsyncSession, tenant_id: TenantId
) -> PreMarketServices:
    """Assemble the PMS read.

    Every upstream is built through its own context's request-less builder, so
    PMS shares their caches and degrade ladders rather than opening a second
    set of connections against the same broker quota. The global board in
    particular is the same read GIA makes, cached globally.

    The tenant is bound here rather than threaded through the ports: nothing on
    this page varies by tenant, but the upstream queries want one.
    """
    market = build_market_services_from(container, session)
    options = build_options_analytics_services_from(container, session)
    breadth = build_breadth_services(container, session)
    global_services = build_global_services(container)

    return PreMarketServices(
        view=GetPreMarketView(
            spots=MarketSpotAdapter(market, tenant_id),
            candles=MarketCandleAdapter(market, tenant_id),
            options=OptionsAdapter(market, options, tenant_id),
            global_cues=GlobalCueAdapter(global_services),
            breadth=BreadthAdapter(breadth, tenant_id),
            flows=FlowAdapter(breadth, tenant_id),
            vix_history=EmptyVixHistory(),
            phase=MarketPhaseAdapter(market),
            narrative=NoNarrative(),
            clock=SystemClock(),
        )
    )
