"""Market data endpoints.

Read-only and authenticated. Each response states where its numbers came from,
so a client can render a stale or simulated badge instead of implying every
figure is live.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from marketcompass.contexts.market_data.api.dependencies import Services
from marketcompass.contexts.market_data.api.schemas import (
    ExpiriesResponse,
    MarketStatusResponse,
    OptionChainResponse,
    QuoteResponse,
)
from marketcompass.contexts.market_data.application.queries import (
    OptionChainQuery,
    QuoteQuery,
)
from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.infrastructure.transport.http.dependencies import CurrentPrincipal

router = APIRouter(prefix="/market", tags=["market data"])

InstrumentParam = Annotated[
    str, Query(description="NIFTY, BANKNIFTY, or SENSEX", examples=["NIFTY"])
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
    summary="Index spot price",
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
    return QuoteResponse.of(quote)


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
