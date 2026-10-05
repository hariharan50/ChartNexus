"""Futures analytics endpoints.

The Future Lab's universe-wide reads: one board of futures across the whole
F&O catalog, classified by price direction against open-interest direction.

Which contract that board prices is a choice — ``series`` selects the near,
next or far month, and ``GET /futures/expiries`` says what those are. It is an
index rather than a date because the dates do not agree across the universe,
so no single date could name the same contract for every row.

Board percentages here are **day-over-day**, measured against each contract's
own previous close and previous open interest. The intraday series beside them
reads the board archive the capture worker writes, which is what lets Future
Lab draw a real session instead of an open-versus-now proxy.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from chartnexus.contexts.futures_analytics.api.dependencies import Services
from chartnexus.contexts.futures_analytics.api.schemas import (
    ExpiryListResponse,
    FuturesBoardResponse,
    FuturesDashboardResponse,
    PriceOiSeriesResponse,
)
from chartnexus.contexts.futures_analytics.application.get_dashboard import (
    DEFAULT_PANEL_LIMIT,
    MAX_PANEL_LIMIT,
    FuturesDashboardQuery,
)
from chartnexus.contexts.futures_analytics.application.get_price_oi_series import (
    DEFAULT_INTERVAL,
    INTERVALS,
    PriceOiSeriesQuery,
)
from chartnexus.infrastructure.brokers.futures_contract import MAX_SERIES
from chartnexus.infrastructure.transport.http.dependencies import CurrentPrincipal

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
SeriesParam = Annotated[
    int,
    Query(
        ge=0,
        le=MAX_SERIES - 1,
        description=(
            "Which contract series to price: 0 near month, 1 next, 2 far. An "
            "index rather than a date, because expiry dates differ across the "
            "universe and no one date names the same contract for every row. "
            "GET /futures/expiries lists them with the date each settles on."
        ),
    ),
]


@router.get(
    "/expiries",
    response_model=ExpiryListResponse,
    summary="The contract series the board can be drawn for",
    description=(
        "Nearest first. `series` is what every other endpoint here takes; "
        "`expiry` is the date most of the universe settles that series on, for "
        "the label — the rows themselves carry their own, since NSE and BSE do "
        "not settle on the same day. Whether a series carries open interest "
        "depends on the provider answering the request, so the board response "
        "says, not this listing."
    ),
)
async def expiries(
    principal: CurrentPrincipal,
    services: Services,
) -> ExpiryListResponse:
    return ExpiryListResponse.of(await services.expiries(principal.tenant_id))


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
    series: SeriesParam = 0,
) -> FuturesDashboardResponse:
    result = await services.dashboard(
        FuturesDashboardQuery(
            tenant_id=principal.tenant_id, limit=limit, sector=sector, series=series
        )
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
    series: SeriesParam = 0,
) -> FuturesBoardResponse:
    result = await services.dashboard(
        FuturesDashboardQuery(
            tenant_id=principal.tenant_id,
            limit=MAX_PANEL_LIMIT,
            sector=sector,
            kind=kind,
            series=series,
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
