"""Options Lab endpoints.

Read-only and authenticated. The Open Interest view is expensive to derive and
changes on a ~15s cadence, so it is cached in Redis behind a short TTL keyed by
tenant and instrument.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Annotated

from fastapi import APIRouter, Path, Query, Request

from marketcompass.contexts.options_analytics.api.dependencies import Services
from marketcompass.contexts.options_analytics.api.schemas import (
    GexResponse,
    OiSeriesResponse,
    OiViewResponse,
    PcrSeriesResponse,
    PriceOiSeriesResponse,
)
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


@router.get(
    "/price-oi-series/{instrument_id}",
    response_model=PriceOiSeriesResponse,
    summary="Intraday future price vs total open interest",
    description=(
        "Two aggregate lines on a shared time axis: the tradable future price "
        "and the whole chain's total open interest. Powers Future Lab → Price "
        "vs OI. Pass ``date`` (ISO, e.g. 2026-08-13) to replay an archived past "
        "session (Historical); omit it for today (Live)."
    ),
    responses={422: {"description": "Unknown instrument"}},
)
async def price_oi_series(
    request: Request,
    principal: CurrentPrincipal,
    services: Services,
    instrument_id: InstrumentParam,
    *,
    interval: Annotated[str, Query(description="1m, 5m, 15m or 1h")] = DEFAULT_INTERVAL,
    date_: Annotated[
        date | None,
        Query(alias="date", description="Archived session to replay (ISO date); omit for today"),
    ] = None,
) -> PriceOiSeriesResponse:
    symbol = instrument_id.strip().upper()
    # Midday UTC (17:30 IST) sits inside the target IST trading date, so the
    # reader resolves the intended session however the day boundary falls.
    trade_date = None if date_ is None else datetime.combine(date_, time(12, 0), tzinfo=UTC)

    redis = get_container(request).redis
    day = "live" if date_ is None else date_.isoformat()
    cache_key = redis.key(
        "lab:price-oi-series", str(principal.tenant_id), symbol, interval, day
    )

    cached = await redis.client.get(cache_key)
    if cached is not None:
        return PriceOiSeriesResponse.model_validate_json(cached)

    payload = await services.price_oi_series(
        principal.tenant_id, symbol, interval=interval, trade_date=trade_date
    )
    response = PriceOiSeriesResponse.of(payload)
    await redis.client.set(cache_key, response.model_dump_json(), ex=_CACHE_TTL_SECONDS)
    return response


@router.get(
    "/pcr-series/{instrument_id}",
    response_model=PcrSeriesResponse,
    summary="Intraday put/call ratio and chain-wide OI totals",
    description=(
        "One point per capture: the put/call ratio by open interest, each "
        "side's total OI and day change, and the tradable future. Powers the "
        "Put-Call Ratio tool's three charts."
    ),
    responses={422: {"description": "Unknown instrument"}},
)
async def pcr_series(
    request: Request,
    principal: CurrentPrincipal,
    services: Services,
    instrument_id: InstrumentParam,
) -> PcrSeriesResponse:
    symbol = instrument_id.strip().upper()
    redis = get_container(request).redis
    # No interval in the key: this payload is six numbers a capture, so the
    # timeframe is applied on the client and one cached entry serves them all.
    cache_key = redis.key("lab:pcr-series", str(principal.tenant_id), symbol)

    cached = await redis.client.get(cache_key)
    if cached is not None:
        return PcrSeriesResponse.model_validate_json(cached)

    payload = await services.pcr_series(principal.tenant_id, symbol)
    response = PcrSeriesResponse.of(payload)
    await redis.client.set(cache_key, response.model_dump_json(), ex=_CACHE_TTL_SECONDS)
    return response


@router.get(
    "/gex/{instrument_id}",
    response_model=GexResponse,
    summary="Intraday per-strike gamma exposure",
    description=(
        "Dealer gamma by strike through the session — call and put exposure in "
        "crore per 1% move in spot, with the call wall, put wall, gamma flip "
        "and net-GEX crossing recomputed at every capture. Powers Gamma "
        "Exposure."
    ),
    responses={422: {"description": "Unknown instrument"}},
)
async def gex(
    request: Request,
    principal: CurrentPrincipal,
    services: Services,
    instrument_id: InstrumentParam,
) -> GexResponse:
    symbol = instrument_id.strip().upper()
    redis = get_container(request).redis
    # No query params, so one entry per tenant/symbol serves every reader — the
    # strike filter and the time scrub are both applied on the client.
    cache_key = redis.key("lab:gex", str(principal.tenant_id), symbol)

    cached = await redis.client.get(cache_key)
    if cached is not None:
        return GexResponse.model_validate_json(cached)

    payload = await services.gex(principal.tenant_id, symbol)
    response = GexResponse.of(payload)
    await redis.client.set(cache_key, response.model_dump_json(), ex=_CACHE_TTL_SECONDS)
    return response
