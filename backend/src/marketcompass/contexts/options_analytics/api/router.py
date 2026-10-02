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
    GreeksSeriesResponse,
    IvHistoryResponse,
    MaxPainSeriesResponse,
    OiSeriesResponse,
    OiViewResponse,
    PcrSeriesResponse,
    PriceOiSeriesResponse,
    SkewResponse,
    SmartOiResponse,
    StraddleChartResponse,
    StraddleSeriesResponse,
    StrikeSeriesResponse,
    TermStructureResponse,
    VegaResponse,
)
from marketcompass.contexts.options_analytics.application.oi_series_service import (
    DEFAULT_INTERVAL,
    DEFAULT_WINDOW,
    MAX_WINDOW,
)
from marketcompass.contexts.options_analytics.application.smart_oi_service import (
    DEFAULT_INTERVAL as SMART_OI_DEFAULT_INTERVAL,
    INTERVALS as SMART_OI_INTERVALS,
    MAX_SPAN,
    MODE_AUTO,
)
from marketcompass.contexts.options_analytics.application.straddle_chart_service import (
    DEFAULT_SESSIONS,
    MAX_SESSIONS,
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
    str,
    Path(
        description="Any underlying in the instrument catalog, e.g. NIFTY or RELIANCE.",
        examples=["NIFTY"],
    ),
]

# Optional archived-session date. Present → Historical mode; absent → Live (today).
DateParam = Annotated[
    date | None,
    Query(alias="date", description="Archived session to replay (ISO date); omit for Live"),
]

#: The expiry a page is looking at. ``None`` means "whatever the backend
#: picks", which is the nearest one - the default every tool opens on.
ExpiryParam = Annotated[
    str | None,
    Query(description="ISO expiry date, e.g. 2026-10-06. Defaults to the nearest expiry."),
]


#: A specific strike to read, instead of the at-the-money one. Tools that let a
#: reader walk the ladder pass it; everything else leaves it out.
StrikeParam = Annotated[
    float | None,
    Query(gt=0, description="Strike to read; defaults to the at-the-money strike."),
]


def _trade_date(date_: date | None) -> datetime | None:
    """A picked date as an instant safely inside its IST trading day.

    Midday UTC is 17:30 IST, so the reader resolves the intended session whatever
    the UTC/IST day boundary does. ``None`` stays ``None`` — Live reads today.
    """
    return None if date_ is None else datetime.combine(date_, time(12, 0), tzinfo=UTC)


def _day_key(date_: date | None) -> str:
    """The cache-key segment distinguishing Live from each archived day."""
    return "live" if date_ is None else date_.isoformat()


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
    *,
    expiry: ExpiryParam = None,
    date_: DateParam = None,
) -> OiViewResponse:
    symbol = instrument_id.strip().upper()
    redis = get_container(request).redis
    cache_key = redis.key(
        "lab:oi", str(principal.tenant_id), symbol, expiry or "near", _day_key(date_)
    )

    cached = await redis.client.get(cache_key)
    if cached is not None:
        return OiViewResponse.model_validate_json(cached)

    payload = await services.oi_view(
        principal.tenant_id, symbol, expiry=expiry, trade_date=_trade_date(date_)
    )
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
    expiry: ExpiryParam = None,
    date_: DateParam = None,
) -> OiSeriesResponse:
    symbol = instrument_id.strip().upper()
    redis = get_container(request).redis
    # Keyed by interval and window as well: they change the payload, so sharing
    # one entry across them would serve whichever shape arrived first.
    cache_key = redis.key(
        "lab:oi-series",
        str(principal.tenant_id),
        symbol,
        interval,
        str(window),
        expiry or "near",
        _day_key(date_),
    )

    cached = await redis.client.get(cache_key)
    if cached is not None:
        return OiSeriesResponse.model_validate_json(cached)

    payload = await services.oi_series(
        principal.tenant_id,
        symbol,
        interval=interval,
        window=window,
        expiry=expiry,
        trade_date=_trade_date(date_),
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
    expiry: ExpiryParam = None,
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
        "lab:price-oi-series", str(principal.tenant_id), symbol, interval, expiry or "near", day
    )

    cached = await redis.client.get(cache_key)
    if cached is not None:
        return PriceOiSeriesResponse.model_validate_json(cached)

    payload = await services.price_oi_series(
        principal.tenant_id, symbol, interval=interval, expiry=expiry, trade_date=trade_date
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
    *,
    expiry: ExpiryParam = None,
    date_: DateParam = None,
) -> PcrSeriesResponse:
    symbol = instrument_id.strip().upper()
    redis = get_container(request).redis
    # No interval in the key: this payload is six numbers a capture, so the
    # timeframe is applied on the client and one cached entry serves them all.
    cache_key = redis.key(
        "lab:pcr-series", str(principal.tenant_id), symbol, expiry or "near", _day_key(date_)
    )

    cached = await redis.client.get(cache_key)
    if cached is not None:
        return PcrSeriesResponse.model_validate_json(cached)

    payload = await services.pcr_series(
        principal.tenant_id, symbol, expiry=expiry, trade_date=_trade_date(date_)
    )
    response = PcrSeriesResponse.of(payload)
    await redis.client.set(cache_key, response.model_dump_json(), ex=_CACHE_TTL_SECONDS)
    return response


@router.get(
    "/max-pain-series/{instrument_id}",
    response_model=MaxPainSeriesResponse,
    summary="Intraday max pain against the tradable future",
    description=(
        "One point per capture: the max-pain strike and the current-month "
        "future. Where the Max Pain profile answers where max pain is now, "
        "this answers where it has been going - the migration through the "
        "session is the reading, and a single snapshot cannot show it."
    ),
    responses={422: {"description": "Unknown instrument"}},
)
async def max_pain_series(
    request: Request,
    principal: CurrentPrincipal,
    services: Services,
    instrument_id: InstrumentParam,
    *,
    expiry: ExpiryParam = None,
    date_: DateParam = None,
) -> MaxPainSeriesResponse:
    symbol = instrument_id.strip().upper()
    redis = get_container(request).redis
    # No interval in the key: three numbers a capture, so the timeframe is
    # applied on the client and one cached entry serves them all.
    cache_key = redis.key(
        "lab:max-pain-series", str(principal.tenant_id), symbol, expiry or "near", _day_key(date_)
    )

    cached = await redis.client.get(cache_key)
    if cached is not None:
        return MaxPainSeriesResponse.model_validate_json(cached)

    payload = await services.max_pain_series(
        principal.tenant_id, symbol, expiry=expiry, trade_date=_trade_date(date_)
    )
    response = MaxPainSeriesResponse.of(payload)
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
    *,
    expiry: ExpiryParam = None,
    date_: DateParam = None,
) -> GexResponse:
    symbol = instrument_id.strip().upper()
    redis = get_container(request).redis
    # The strike filter and the time scrub are both applied on the client, so one
    # entry per tenant/symbol/day serves every reader of that session.
    cache_key = redis.key(
        "lab:gex", str(principal.tenant_id), symbol, expiry or "near", _day_key(date_)
    )

    cached = await redis.client.get(cache_key)
    if cached is not None:
        return GexResponse.model_validate_json(cached)

    payload = await services.gex(
        principal.tenant_id, symbol, expiry=expiry, trade_date=_trade_date(date_)
    )
    response = GexResponse.of(payload)
    await redis.client.set(cache_key, response.model_dump_json(), ex=_CACHE_TTL_SECONDS)
    return response


@router.get(
    "/vega/{instrument_id}",
    response_model=VegaResponse,
    summary="Intraday per-strike vega exposure",
    description=(
        "Aggregate option vega by strike through the session — call and put "
        "vega in crore per one volatility point, at every capture, with the "
        "put-call-parity synthetic future overlaid. The client sums the window "
        "it draws and plots each side's change since the open. Powers Vega "
        "Analysis."
    ),
    responses={422: {"description": "Unknown instrument"}},
)
async def vega(
    request: Request,
    principal: CurrentPrincipal,
    services: Services,
    instrument_id: InstrumentParam,
    *,
    expiry: ExpiryParam = None,
    date_: DateParam = None,
) -> VegaResponse:
    symbol = instrument_id.strip().upper()
    redis = get_container(request).redis
    # The strike window and the timeframe are both applied on the client, so one
    # entry per tenant/symbol/day serves every reader of that session.
    cache_key = redis.key(
        "lab:vega", str(principal.tenant_id), symbol, expiry or "near", _day_key(date_)
    )

    cached = await redis.client.get(cache_key)
    if cached is not None:
        return VegaResponse.model_validate_json(cached)

    payload = await services.vega(
        principal.tenant_id, symbol, expiry=expiry, trade_date=_trade_date(date_)
    )
    response = VegaResponse.of(payload)
    await redis.client.set(cache_key, response.model_dump_json(), ex=_CACHE_TTL_SECONDS)
    return response


@router.get(
    "/straddle-chart/{instrument_id}",
    response_model=StraddleChartResponse,
    summary="The rolling at-the-money straddle across sessions",
    description=(
        "What it costs to own the at-the-money call and put together, at every "
        "capture, with the index and the put-call-parity synthetic forward "
        "beside it. The strike **rolls**: each point is priced at its own "
        "at-the-money strike and carries it, because the subject is the cost of "
        "being at the money rather than the price of one contract. `sessions` "
        "counts stored trading days, so three days is three sessions of trading "
        "and not three calendar days. Powers Straddle Chart."
    ),
    responses={422: {"description": "Unknown instrument"}},
)
async def straddle_chart(
    request: Request,
    principal: CurrentPrincipal,
    services: Services,
    instrument_id: InstrumentParam,
    *,
    expiry: ExpiryParam = None,
    sessions: Annotated[
        int,
        Query(ge=1, le=MAX_SESSIONS, description="Trading sessions to cover, latest last"),
    ] = DEFAULT_SESSIONS,
    date_: DateParam = None,
) -> StraddleChartResponse:
    symbol = instrument_id.strip().upper()
    redis = get_container(request).redis
    # Keyed by the window too: it changes the payload, so sharing one entry
    # across ranges would serve whichever arrived first.
    cache_key = redis.key(
        "lab:straddle-chart",
        str(principal.tenant_id),
        symbol,
        expiry or "near",
        str(sessions),
        _day_key(date_),
    )

    cached = await redis.client.get(cache_key)
    if cached is not None:
        return StraddleChartResponse.model_validate_json(cached)

    payload = await services.straddle_chart(
        principal.tenant_id,
        symbol,
        expiry=expiry,
        sessions=sessions,
        trade_date=_trade_date(date_),
    )
    response = StraddleChartResponse.of(payload)
    await redis.client.set(cache_key, response.model_dump_json(), ex=_CACHE_TTL_SECONDS)
    return response


@router.get(
    "/greeks/{instrument_id}",
    response_model=GreeksSeriesResponse,
    summary="Intraday greeks for one strike's call and put",
    description=(
        "IV, delta, gamma, theta and vega through the session for a single "
        "strike, both legs, at every capture. The strike is pinned — the "
        "at-the-money one of the latest capture unless `strike` names another — "
        "because the charts are titled with the contract's own symbol and a "
        "rolling strike under a fixed title describes a contract that is no "
        "longer there. Greeks are derived from each capture's quoted implied "
        "volatility with Black-Scholes; a leg quoted no volatility reads as a "
        "gap, never a zero. The client buckets to the timeframe it draws. "
        "Powers Option Greeks."
    ),
    responses={422: {"description": "Unknown instrument"}},
)
async def greeks_series(
    request: Request,
    principal: CurrentPrincipal,
    services: Services,
    instrument_id: InstrumentParam,
    *,
    expiry: ExpiryParam = None,
    strike: StrikeParam = None,
    date_: DateParam = None,
) -> GreeksSeriesResponse:
    symbol = instrument_id.strip().upper()
    redis = get_container(request).redis
    # The timeframe is applied on the client, so one entry per
    # tenant/symbol/expiry/strike/day serves every reader of that session.
    cache_key = redis.key(
        "lab:greeks",
        str(principal.tenant_id),
        symbol,
        expiry or "near",
        "atm" if strike is None else str(strike),
        _day_key(date_),
    )

    cached = await redis.client.get(cache_key)
    if cached is not None:
        return GreeksSeriesResponse.model_validate_json(cached)

    payload = await services.greeks_series(
        principal.tenant_id,
        symbol,
        expiry=expiry,
        strike=strike,
        trade_date=_trade_date(date_),
    )
    response = GreeksSeriesResponse.of(payload)
    await redis.client.set(cache_key, response.model_dump_json(), ex=_CACHE_TTL_SECONDS)
    return response


@router.get(
    "/iv-history/{instrument_id}",
    response_model=IvHistoryResponse,
    summary="Daily at-the-money implied volatility",
    description=(
        "One closing IV reading per trading session, oldest first, from the "
        "durable per-session archive. IV Rank and IV Percentile are left to the "
        "client, which owns the lookback the reader picks. `covered_sessions` "
        "says how much history actually exists — the archive accrues forward "
        "and cannot be backfilled past the intraday retention window. Powers "
        "the IV/HV/IVP Chart."
    ),
    responses={422: {"description": "Unknown instrument"}},
)
async def iv_history(
    request: Request,
    principal: CurrentPrincipal,
    services: Services,
    instrument_id: InstrumentParam,
    *,
    days: Annotated[int, Query(ge=1, le=365, description="Calendar days to cover")] = 365,
) -> IvHistoryResponse:
    symbol = instrument_id.strip().upper()
    redis = get_container(request).redis
    # Keyed by the window as well: it changes the payload, so sharing one entry
    # across ranges would serve whichever arrived first.
    cache_key = redis.key(
        "lab:iv-history", str(principal.tenant_id), symbol, str(days), _day_key(None)
    )

    cached = await redis.client.get(cache_key)
    if cached is not None:
        return IvHistoryResponse.model_validate_json(cached)

    payload = await services.iv_history(principal.tenant_id, symbol, days=days)
    response = IvHistoryResponse.of(payload)
    await redis.client.set(cache_key, response.model_dump_json(), ex=_CACHE_TTL_SECONDS)
    return response


@router.get(
    "/term-structure/{instrument_id}",
    response_model=TermStructureResponse,
    summary="Live at-the-money implied volatility across expiries",
    description=(
        "The volatility term structure as of now: one at-the-money reading per "
        "requested expiry, taken from that expiry's live chain. Live only — a "
        "term structure is several expiries priced at one instant, and the "
        "snapshot archive holds a single expiry per session, so there is no "
        "history to replay. Powers the IV Intraday page's Term Structure view."
    ),
    responses={422: {"description": "Unknown instrument"}},
)
async def term_structure(
    request: Request,
    principal: CurrentPrincipal,
    services: Services,
    instrument_id: InstrumentParam,
    *,
    expiries: Annotated[
        str, Query(description="Comma-separated ISO expiry dates, at most five")
    ] = "",
) -> TermStructureResponse:
    symbol = instrument_id.strip().upper()
    wanted = [part for part in expiries.split(",") if part.strip()]
    redis = get_container(request).redis
    # The expiry list shapes the payload, so it belongs in the key; sorted so
    # two readers asking for the same set in a different order share an entry.
    cache_key = redis.key(
        "lab:term-structure", str(principal.tenant_id), symbol, ",".join(sorted(wanted))
    )

    cached = await redis.client.get(cache_key)
    if cached is not None:
        return TermStructureResponse.model_validate_json(cached)

    payload = await services.term_structure(principal.tenant_id, symbol, expiries=wanted)
    response = TermStructureResponse.of(payload)
    await redis.client.set(cache_key, response.model_dump_json(), ex=_CACHE_TTL_SECONDS)
    return response


@router.get(
    "/skew/{instrument_id}",
    response_model=SkewResponse,
    summary="Intraday per-strike implied volatility and open interest",
    description=(
        "Each strike's call and put implied volatility through the session, "
        "with the open interest sitting on each side, at every capture. The "
        "client blends the two volatility arrays into the out-of-the-money "
        "curve it draws, scrubs the captures and windows the strikes. Powers "
        "Volatility Skew."
    ),
    responses={422: {"description": "Unknown instrument"}},
)
async def skew(
    request: Request,
    principal: CurrentPrincipal,
    services: Services,
    instrument_id: InstrumentParam,
    *,
    expiry: ExpiryParam = None,
    date_: DateParam = None,
) -> SkewResponse:
    symbol = instrument_id.strip().upper()
    redis = get_container(request).redis
    # The strike window, the frame and the curve blend are all applied on the
    # client, so one entry per tenant/symbol/day serves every reader of that
    # session.
    cache_key = redis.key(
        "lab:skew", str(principal.tenant_id), symbol, expiry or "near", _day_key(date_)
    )

    cached = await redis.client.get(cache_key)
    if cached is not None:
        return SkewResponse.model_validate_json(cached)

    payload = await services.skew(
        principal.tenant_id, symbol, expiry=expiry, trade_date=_trade_date(date_)
    )
    response = SkewResponse.of(payload)
    await redis.client.set(cache_key, response.model_dump_json(), ex=_CACHE_TTL_SECONDS)
    return response


@router.get(
    "/straddle-series/{instrument_id}",
    response_model=StraddleSeriesResponse,
    summary="Intraday ATM straddle premium and per-strike straddles",
    description=(
        "Each strike's call and put last price through the session, the rolling "
        "at-the-money straddle (call + put at each capture's ATM), and the "
        "tradable future overlaid. The client picks a strike or the rolling ATM "
        "and applies the timeframe. Powers the ATM Straddle Chart."
    ),
    responses={422: {"description": "Unknown instrument"}},
)
async def straddle_series(
    request: Request,
    principal: CurrentPrincipal,
    services: Services,
    instrument_id: InstrumentParam,
    *,
    expiry: ExpiryParam = None,
    date_: DateParam = None,
) -> StraddleSeriesResponse:
    symbol = instrument_id.strip().upper()
    redis = get_container(request).redis
    # The strike selection and the timeframe are both applied on the client, so
    # one entry per tenant/symbol/day serves every reader of that session.
    cache_key = redis.key(
        "lab:straddle-series", str(principal.tenant_id), symbol, expiry or "near", _day_key(date_)
    )

    cached = await redis.client.get(cache_key)
    if cached is not None:
        return StraddleSeriesResponse.model_validate_json(cached)

    payload = await services.straddle_series(
        principal.tenant_id, symbol, expiry=expiry, trade_date=_trade_date(date_)
    )
    response = StraddleSeriesResponse.of(payload)
    await redis.client.set(cache_key, response.model_dump_json(), ex=_CACHE_TTL_SECONDS)
    return response


@router.get(
    "/strike-series/{instrument_id}",
    response_model=StrikeSeriesResponse,
    summary="One strike's intraday price, OI and OI-change series",
    description=(
        "For a single strike: its call and put last price, open interest, day OI "
        "change, the straddle (call + put price) and the per-strike put/call "
        "ratio, on one shared time axis, plus the strike ladder for the sidebar. "
        "Powers the Price vs OI tool's six charts."
    ),
    responses={422: {"description": "Unknown instrument"}},
)
async def strike_series(
    request: Request,
    principal: CurrentPrincipal,
    services: Services,
    instrument_id: InstrumentParam,
    *,
    strike: Annotated[
        float | None, Query(gt=0, description="The strike to plot; omit for at-the-money")
    ] = None,
    expiry: ExpiryParam = None,
    date_: DateParam = None,
) -> StrikeSeriesResponse:
    symbol = instrument_id.strip().upper()
    redis = get_container(request).redis
    # Keyed by strike as well: it changes the payload, so sharing one entry across
    # strikes would serve whichever arrived first. "atm" is the omitted default.
    cache_key = redis.key(
        "lab:strike-series",
        str(principal.tenant_id),
        symbol,
        "atm" if strike is None else f"{strike:g}",
        expiry or "near",
        _day_key(date_),
    )

    cached = await redis.client.get(cache_key)
    if cached is not None:
        return StrikeSeriesResponse.model_validate_json(cached)

    payload = await services.strike_series(
        principal.tenant_id, symbol, strike=strike, expiry=expiry, trade_date=_trade_date(date_)
    )
    response = StrikeSeriesResponse.of(payload)
    await redis.client.set(cache_key, response.model_dump_json(), ex=_CACHE_TTL_SECONDS)
    return response


@router.get(
    "/smart-oi/{instrument_id}",
    response_model=SmartOiResponse,
    summary="Per-bar OI flow against the underlying's price",
    description=(
        "Two aligned axes: the chain's cumulative OI change and both put/call "
        "ratios at the archive's own cadence, plus per-bar OI flow and option "
        "volume on the candle grid. Every total respects the strike window. "
        "Powers Smart OI."
    ),
    responses={422: {"description": "Unknown instrument"}},
)
async def smart_oi(
    request: Request,
    principal: CurrentPrincipal,
    services: Services,
    instrument_id: InstrumentParam,
    *,
    interval: Annotated[
        str, Query(description=f"Bar size: {', '.join(SMART_OI_INTERVALS)}")
    ] = SMART_OI_DEFAULT_INTERVAL,
    mode: Annotated[
        str,
        Query(
            description=(
                "`auto` re-centres the strike window on each capture's ATM; "
                "`fixed` pins it to the session open's."
            ),
            pattern="^(auto|fixed)$",
        ),
    ] = MODE_AUTO,
    span: Annotated[
        int | None,
        Query(
            ge=1, le=MAX_SPAN, description="Strikes either side of ATM; omit for the whole chain"
        ),
    ] = None,
    min_strike: Annotated[
        float | None, Query(description="Absolute window floor; overrides `mode` and `span`")
    ] = None,
    max_strike: Annotated[
        float | None, Query(description="Absolute window ceiling; overrides `mode` and `span`")
    ] = None,
    expiry: Annotated[
        str | None, Query(description="ISO date. Defaults to the nearest expiry.")
    ] = None,
    date_: DateParam = None,
) -> SmartOiResponse:
    symbol = instrument_id.strip().upper()
    redis = get_container(request).redis
    # Every parameter that changes the payload is in the key. Windowing happens
    # server-side because the client only ever receives totals, so two windows
    # sharing one cache entry would serve the wrong numbers rather than merely
    # stale ones.
    cache_key = redis.key(
        "lab:smart-oi",
        str(principal.tenant_id),
        symbol,
        interval,
        mode,
        "all" if span is None else str(span),
        "-" if min_strike is None else f"{min_strike:g}",
        "-" if max_strike is None else f"{max_strike:g}",
        expiry or "near",
        _day_key(date_),
    )

    cached = await redis.client.get(cache_key)
    if cached is not None:
        return SmartOiResponse.model_validate_json(cached)

    payload = await services.smart_oi(
        principal.tenant_id,
        symbol,
        interval=interval,
        mode=mode,
        span=span,
        min_strike=min_strike,
        max_strike=max_strike,
        expiry=expiry,
        trade_date=_trade_date(date_),
    )
    response = SmartOiResponse.of(payload)
    await redis.client.set(cache_key, response.model_dump_json(), ex=_CACHE_TTL_SECONDS)
    return response
