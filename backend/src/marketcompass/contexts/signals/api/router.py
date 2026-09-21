"""AI Market Guider endpoints.

Read-only and authenticated. Guidance is expensive to derive (it fans out to the
option chain, candle history and the gamma view) and changes on a ~15s cadence,
so it is cached in Redis behind a short TTL keyed by tenant and instrument, the
same shape the Options Lab routes use.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query, Request

from marketcompass.contexts.signals.api.dependencies import Services
from marketcompass.contexts.signals.api.schemas import (
    FactorsResponse,
    GuidanceResponse,
    HistoryResponse,
)
from marketcompass.infrastructure.transport.http.dependencies import (
    CurrentPrincipal,
    get_container,
)

router = APIRouter(prefix="/signals", tags=["signals"])

# Just under the client's 15s poll: fresh enough to feel live, long enough that a
# burst of viewers on one instrument collapses onto a single derivation.
_CACHE_TTL_SECONDS = 12

InstrumentParam = Annotated[
    str,
    Path(
        description="NIFTY, BANKNIFTY, or SENSEX. This surface is index-only;"
        " the wider F&O catalog is not covered here yet.",
        examples=["NIFTY"],
    ),
]


@router.get(
    "/{instrument_id}/guidance",
    response_model=GuidanceResponse,
    summary="AI guidance for an instrument",
    description=(
        "An explicit BUY / SELL / HOLD call with confidence, the four-skill "
        "breakdown it was fused from, an illustrative trade scaffold, a "
        "rule-based rationale, and — always — the worst provenance of any input. "
        "Not investment advice."
    ),
    responses={422: {"description": "Unknown instrument"}},
)
async def guidance(
    request: Request,
    principal: CurrentPrincipal,
    services: Services,
    instrument_id: InstrumentParam,
) -> GuidanceResponse:
    symbol = instrument_id.strip().upper()
    redis = get_container(request).redis
    cache_key = redis.key("signals:guidance", str(principal.tenant_id), symbol)

    cached = await redis.client.get(cache_key)
    if cached is not None:
        return GuidanceResponse.model_validate_json(cached)

    result = await services.guidance(principal.tenant_id, symbol)
    response = GuidanceResponse.of(result)
    await redis.client.set(cache_key, response.model_dump_json(), ex=_CACHE_TTL_SECONDS)
    return response


@router.get(
    "/{instrument_id}/factors",
    response_model=FactorsResponse,
    summary="Per-skill factor breakdown",
    description="The raw per-skill scores and reads behind the call, for a 'why' panel.",
    responses={422: {"description": "Unknown instrument"}},
)
async def factors(
    principal: CurrentPrincipal,
    services: Services,
    instrument_id: InstrumentParam,
) -> FactorsResponse:
    symbol = instrument_id.strip().upper()
    result = await services.guidance(principal.tenant_id, symbol)
    return FactorsResponse.of(result)


@router.get(
    "/{instrument_id}/history",
    response_model=HistoryResponse,
    summary="Past decisions",
    description="Recorded decision changes for this instrument, newest first.",
)
async def history(
    principal: CurrentPrincipal,
    services: Services,
    instrument_id: InstrumentParam,
    *,
    limit: Annotated[int, Query(ge=1, le=200, description="Max decisions to return")] = 50,
) -> HistoryResponse:
    symbol = instrument_id.strip().upper()
    records = await services.history(principal.tenant_id, symbol, limit=limit)
    return HistoryResponse.of(symbol, records)
