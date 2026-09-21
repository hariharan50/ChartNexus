"""Futures analytics endpoints.

The Future Lab's universe-wide reads: one board of front-month futures across
the whole F&O catalog, classified by price direction against open-interest
direction.

Percentages here are **day-over-day**, measured against each contract's own
previous close and previous open interest. The intraday comparison windows the
Future Lab offers elsewhere need a snapshot archive of the board, which does
not exist yet.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from marketcompass.contexts.futures_analytics.api.dependencies import Services
from marketcompass.contexts.futures_analytics.api.schemas import (
    FuturesBoardResponse,
    FuturesDashboardResponse,
)
from marketcompass.contexts.futures_analytics.application.get_dashboard import (
    DEFAULT_PANEL_LIMIT,
    MAX_PANEL_LIMIT,
    FuturesDashboardQuery,
)
from marketcompass.infrastructure.transport.http.dependencies import CurrentPrincipal

router = APIRouter(prefix="/futures", tags=["futures"])

LimitParam = Annotated[
    int,
    Query(ge=1, le=MAX_PANEL_LIMIT, description="Rows per panel."),
]
SectorParam = Annotated[
    str | None,
    Query(max_length=64, description="Restrict the board to one sector."),
]
KindParam = Annotated[
    Literal["index", "stock"] | None,
    Query(description="Restrict the board to index or stock underlyings."),
]


@router.get(
    "/dashboard",
    response_model=FuturesDashboardResponse,
    summary="Top movers and the four build-up buckets",
    description=(
        "One pass over the whole F&O universe, sliced into the six panels the "
        "Future Dashboard shows. Changes are against the previous close."
    ),
)
async def dashboard(
    principal: CurrentPrincipal,
    services: Services,
    limit: LimitParam = DEFAULT_PANEL_LIMIT,
    sector: SectorParam = None,
) -> FuturesDashboardResponse:
    result = await services.dashboard(
        FuturesDashboardQuery(tenant_id=principal.tenant_id, limit=limit, sector=sector)
    )
    return FuturesDashboardResponse.of(result)


@router.get(
    "/board",
    response_model=FuturesBoardResponse,
    summary="Every classified contract",
    description=(
        "The same readings the dashboard panels are drawn from, unsliced — for "
        "the table view, the stock list and the market-movers page. `covered` "
        "against `universe` says how much of the catalog was actually priced."
    ),
)
async def board(
    principal: CurrentPrincipal,
    services: Services,
    sector: SectorParam = None,
    kind: KindParam = None,
) -> FuturesBoardResponse:
    result = await services.dashboard(
        FuturesDashboardQuery(
            tenant_id=principal.tenant_id,
            limit=MAX_PANEL_LIMIT,
            sector=sector,
            kind=kind,
        )
    )
    return FuturesBoardResponse.of(result)
