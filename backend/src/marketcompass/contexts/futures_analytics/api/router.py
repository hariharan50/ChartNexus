"""Futures analytics endpoints.

The Future Lab's universe-wide reads: one board of front-month futures across
the whole F&O catalog, classified by price direction against open-interest
direction.

Board percentages here are **day-over-day**, measured against each contract's
own previous close and previous open interest. The intraday series beside them
reads the board archive the capture worker writes, which is what lets Future
Lab draw a real session instead of an open-versus-now proxy.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from marketcompass.contexts.futures_analytics.api.dependencies import Services
from marketcompass.contexts.futures_analytics.api.schemas import (
    FuturesBoardResponse,
    FuturesDashboardResponse,
    PriceOiSeriesResponse,
)
from marketcompass.contexts.futures_analytics.application.get_dashboard import (
    DEFAULT_PANEL_LIMIT,
    MAX_PANEL_LIMIT,
    FuturesDashboardQuery,
)
from marketcompass.contexts.futures_analytics.application.get_price_oi_series import (
    DEFAULT_INTERVAL,
    INTERVALS,
    PriceOiSeriesQuery,
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


IntervalParam = Annotated[
    str,
    Query(description=f"Bucket width: {', '.join(INTERVALS)}."),
]
TradeDateParam = Annotated[
    date | None,
    Query(
        alias="date",
        description="Archived session to replay. Omit for today, which is Live.",
    ),
]


@router.get(
    "/price-oi-series/{instrument_id}",
    response_model=PriceOiSeriesResponse,
    summary="One contract's intraday price against its open interest",
    description=(
        "The front-month futures price and **that contract's own** open "
        "interest through the session. Not the option chain's OI — the Options "
        "Lab series of a similar name sums every strike, and the two answer "
        "different questions. "
        "`data_quality` says what the numbers are worth: `intraday` is the "
        "captured session, `live_proxy` is previous-close-versus-now for a day "
        "with nothing archived yet, and `empty` means there is nothing to draw. "
        "`oi` carries nulls where a frame fell between open-interest sweeps, "
        "which run slower than price captures."
    ),
)
async def price_oi_series(
    instrument_id: str,
    principal: CurrentPrincipal,
    services: Services,
    interval: IntervalParam = DEFAULT_INTERVAL,
    date_: TradeDateParam = None,
) -> PriceOiSeriesResponse:
    payload = await services.price_oi_series(
        PriceOiSeriesQuery(
            tenant_id=principal.tenant_id,
            symbol=instrument_id,
            interval=interval,
            trade_date=date_,
        )
    )
    return PriceOiSeriesResponse.model_validate(payload)
