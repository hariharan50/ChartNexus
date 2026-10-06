"""Market data endpoints.

Read-only and authenticated. Each response states where its numbers came from,
so a client can render a stale or simulated badge instead of implying every
figure is live.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from chartnexus.contexts.market_data.api.dependencies import Services
from chartnexus.contexts.market_data.api.schemas import (
    ExpiriesResponse,
    FuturesQuoteResponse,
    HistoryResponse,
    MarketStatusResponse,
    OptionChainResponse,
    QuoteResponse,
)
from chartnexus.contexts.market_data.application.queries import (
    HistoryQuery,
    OptionChainQuery,
    QuoteQuery,
)
from chartnexus.contexts.market_data.domain.instruments import InstrumentSymbol
from chartnexus.contexts.market_data.domain.market_data import CandleInterval
from chartnexus.infrastructure.transport.http.dependencies import CurrentPrincipal

router = APIRouter(prefix="/market", tags=["market data"])

InstrumentParam = Annotated[
    str,
    Query(
        description="Any underlying in the instrument catalog, e.g. NIFTY or RELIANCE.",
        examples=["NIFTY"],
    ),
]


@router.get(
    "/status",
    response_model=MarketStatusResponse,
    summary="Session state and active data source",
)
async def market_status(principal: CurrentPrincipal, services: Services) -> MarketStatusResponse:
    return MarketStatusResponse.of(await services.status(principal.tenant_id))


@router.get(
    "/spot",
    response_model=QuoteResponse,
    summary="Index spot price and the session's opening gap",
    description=(
        "The last price, plus the session's **latched** opening gap. The gap is "
        "computed here rather than by the client because the opening print is a "
        "fact of the session: once observed from a live quote it is frozen, so a "
        "poll that degrades to cached or simulated data cannot rewrite it."
    ),
    responses={422: {"description": "Unknown instrument"}},
)
async def spot(
    principal: CurrentPrincipal,
    services: Services,
    instrument: InstrumentParam = "NIFTY",
) -> QuoteResponse:
    quote = await services.spot(
        QuoteQuery(tenant_id=principal.tenant_id, instrument=InstrumentSymbol.parse(instrument))
    )
    return QuoteResponse.of(quote, await services.gap(principal.tenant_id, quote))


@router.get(
    "/futures",
    response_model=FuturesQuoteResponse,
    summary="Front-month futures quote",
    description=(
        "The underlying's near-month futures contract. Rolls to the next month "
        "automatically once the current contract's expiry passes."
    ),
    responses={422: {"description": "Unknown instrument"}},
)
async def futures(
    principal: CurrentPrincipal,
    services: Services,
    instrument: InstrumentParam = "NIFTY",
) -> FuturesQuoteResponse:
    quote = await services.futures(
        QuoteQuery(tenant_id=principal.tenant_id, instrument=InstrumentSymbol.parse(instrument))
    )
    return FuturesQuoteResponse.of(quote)


@router.get(
    "/option-chain",
    response_model=OptionChainResponse,
    summary="Option chain with PCR and ATM",
    description=(
        "Strikes either side of at-the-money with both legs, plus the "
        "put/call ratio and the nearest listed strike to spot."
    ),
)
async def option_chain(
    principal: CurrentPrincipal,
    services: Services,
    instrument: InstrumentParam = "NIFTY",
    expiry: Annotated[
        str | None, Query(description="ISO date. Defaults to the nearest expiry.")
    ] = None,
) -> OptionChainResponse:
    chain = await services.option_chain(
        OptionChainQuery(
            tenant_id=principal.tenant_id,
            instrument=InstrumentSymbol.parse(instrument),
            expiry=expiry,
        )
    )
    return OptionChainResponse.of(chain)


@router.get(
    "/history",
    response_model=HistoryResponse,
    summary="Price history as OHLC candles",
    description=(
        "Bars for the requested interval, oldest first. `days` is clamped to "
        "what the interval supports — a year of one-minute bars is not a slow "
        "request, it is one the broker rejects."
    ),
    responses={422: {"description": "Unknown instrument or interval"}},
)
async def history(
    principal: CurrentPrincipal,
    services: Services,
    *,
    instrument: InstrumentParam = "NIFTY",
    interval: Annotated[CandleInterval, Query(description="Bar size")] = CandleInterval.M5,
    days: Annotated[int, Query(ge=1, le=365, description="Trading days to cover")] = 5,
    live_only: Annotated[
        bool,
        Query(
            description=(
                "Refuse simulated bars. Returns an empty series with "
                "`provenance.source = unavailable` when no real data exists, "
                "rather than falling back to the mock. Cached real bars still "
                "answer. For price charts, where a synthetic candle is "
                "indistinguishable from a traded one once drawn."
            )
        ),
    ] = False,
) -> HistoryResponse:
    series = await services.history(
        HistoryQuery(
            tenant_id=principal.tenant_id,
            instrument=InstrumentSymbol.parse(instrument),
            interval=interval,
            days=days,
            live_only=live_only,
        )
    )
    return HistoryResponse.of(series)


@router.get(
    "/expiries",
    response_model=ExpiriesResponse,
    summary="Available expiry dates",
)
async def expiries(
    principal: CurrentPrincipal,
    services: Services,
    instrument: InstrumentParam = "NIFTY",
) -> ExpiriesResponse:
    result = await services.expiries(
        QuoteQuery(tenant_id=principal.tenant_id, instrument=InstrumentSymbol.parse(instrument))
    )
    return ExpiriesResponse.of(result)
