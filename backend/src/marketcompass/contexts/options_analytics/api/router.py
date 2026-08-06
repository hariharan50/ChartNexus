"""Options Lab endpoints.

Read-only and authenticated. The Open Interest view is expensive to derive and
changes on a ~15s cadence, so it is cached in Redis behind a short TTL keyed by
tenant and instrument.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query, Request

from marketcompass.contexts.options_analytics.api.dependencies import Services
from marketcompass.contexts.options_analytics.api.schemas import OiSeriesResponse, OiViewResponse
from marketcompass.contexts.options_analytics.application.oi_series_service import (
    DEFAULT_INTERVAL,
    DEFAULT_WINDOW,
    MAX_WINDOW,
)
from marketcompass.infrastructure.transport.http.dependencies import (
    CurrentPrincipal,
    get_container,
)

router = APIRouter(prefix="/options-lab", tags=["options lab"])

# Just under the client's 15s poll: fresh enough to feel live, long enough that a
# burst of viewers on the same instrument collapses onto one derivation.
_CACHE_TTL_SECONDS = 12

InstrumentParam = Annotated[
    str, Path(description="NIFTY, BANKNIFTY, or SENSEX", examples=["NIFTY"])
]


@router.get(
    "/oi/{instrument_id}",
    response_model=OiViewResponse,
    summary="Open Interest view",
    description=(
        "Per-strike call/put OI with today's change, PCR, max pain, an ATM "
        "anchor, a sentiment read, and an intraday OI series."
    ),
    responses={422: {"description": "Unknown instrument"}},
)
async def open_interest(
    request: Request,
    principal: CurrentPrincipal,
    services: Services,
    instrument_id: InstrumentParam,
) -> OiViewResponse:
    symbol = instrument_id.strip().upper()
    redis = get_container(request).redis
    cache_key = redis.key("lab:oi", str(principal.tenant_id), symbol)

    cached = await redis.client.get(cache_key)
    if cached is not None:
        return OiViewResponse.model_validate_json(cached)

    payload = await services.oi_view(principal.tenant_id, symbol)
    response = OiViewResponse.of(payload)
    await redis.client.set(cache_key, response.model_dump_json(), ex=_CACHE_TTL_SECONDS)
    return response


@router.get(
    "/oi-series/{instrument_id}",
    response_model=OiSeriesResponse,
    summary="Per-contract intraday OI and volume series",
    description=(
        "A shared time axis plus one open-interest and one volume array per "
        "contract within a window of ATM, with the tradable future overlaid. "
        "Powers Multi OI & Volume."
    ),
    responses={422: {"description": "Unknown instrument"}},
)
async def oi_series(
    request: Request,
    principal: CurrentPrincipal,
    services: Services,
    instrument_id: InstrumentParam,
    *,
    interval: Annotated[str, Query(description="1m, 5m, 15m or 1h")] = DEFAULT_INTERVAL,
    window: Annotated[int, Query(ge=1, le=MAX_WINDOW, description="Strikes either side of ATM")] = (
        DEFAULT_WINDOW
    ),
) -> OiSeriesResponse:
    symbol = instrument_id.strip().upper()
    redis = get_container(request).redis
    # Keyed by interval and window as well: they change the payload, so sharing
    # one entry across them would serve whichever shape arrived first.
    cache_key = redis.key("lab:oi-series", str(principal.tenant_id), symbol, interval, str(window))

    cached = await redis.client.get(cache_key)
    if cached is not None:
        return OiSeriesResponse.model_validate_json(cached)

    payload = await services.oi_series(
        principal.tenant_id, symbol, interval=interval, window=window
    )
    response = OiSeriesResponse.of(payload)
    await redis.client.set(cache_key, response.model_dump_json(), ex=_CACHE_TTL_SECONDS)
    return response
