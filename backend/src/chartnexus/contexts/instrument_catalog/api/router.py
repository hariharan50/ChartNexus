"""Instrument catalog endpoints.

Reference data, not market data: which underlyings exist and what their
contracts look like. Authenticated like everything else, but not tenant-scoped
— the NSE F&O list is the same for every tenant.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from chartnexus.contexts.instrument_catalog.api.dependencies import Services
from chartnexus.contexts.instrument_catalog.api.schemas import (
    InstrumentListResponse,
    InstrumentResponse,
)
from chartnexus.contexts.instrument_catalog.application.use_cases import (
    DEFAULT_LIST_LIMIT,
    ListInstrumentsQuery,
)
from chartnexus.contexts.instrument_catalog.domain.instrument import InstrumentKind
from chartnexus.infrastructure.transport.http.dependencies import CurrentPrincipal

router = APIRouter(prefix="/instruments", tags=["instruments"])

KindParam = Annotated[
    InstrumentKind | None,
    Query(description="Restrict to index or stock underlyings."),
]
SearchParam = Annotated[
    str | None,
    Query(max_length=64, description="Substring match on ticker or company name."),
]


@router.get(
    "",
    response_model=InstrumentListResponse,
    summary="The tradeable F&O universe",
    description=(
        "Every underlying the application can price, indices first then alphabetical. "
        "Backs the symbol picker, so it is deliberately one call rather than paged."
    ),
)
async def list_instruments(
    _principal: CurrentPrincipal,
    services: Services,
    kind: KindParam = None,
    search: SearchParam = None,
    limit: Annotated[int, Query(ge=1, le=DEFAULT_LIST_LIMIT)] = DEFAULT_LIST_LIMIT,
) -> InstrumentListResponse:
    instruments = await services.search(ListInstrumentsQuery(kind=kind, search=search, limit=limit))
    return InstrumentListResponse.of(instruments)


@router.get(
    "/{symbol}",
    response_model=InstrumentResponse,
    summary="One instrument by symbol",
    responses={404: {"description": "No such instrument"}},
)
async def get_instrument(
    symbol: str,
    _principal: CurrentPrincipal,
    services: Services,
) -> InstrumentResponse:
    return InstrumentResponse.of(await services.get(symbol))
