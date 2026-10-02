"""Wire contract for the Open Interest view.

The service produces a plain dict (cheap to cache as JSON); these models give the
endpoint a typed, documented response and validate the shape on the way out.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StrikeOiResponse(_Schema):
    strike: float
    call_oi_open: int
    call_oi_now: int
    call_oi_chg: int
    call_oi_chg_pct: float
    put_oi_open: int
    put_oi_now: int
    put_oi_chg: int
    put_oi_chg_pct: float


class SeriesFrameResponse(_Schema):
    t: str
    strikes: list[float]
    call: list[int | None]
    put: list[int | None]
    # Optional because the live tier synthesises its two frames from one chain
    # and has no stored header to read them from; the client falls back to the
    # payload-level values there.
    spot: float | None = None
    atm: float | None = None
    max_pain: float | None = None


class SentimentResponse(_Schema):
    label: str
    bullish_pct: int
    insight: str
    analysis: str


class OiViewResponse(_Schema):
    instrument_id: str
    symbol: str
    spot: float
    atm_strike: float
    max_pain: float
    lot_size: int | None
    expiry_date: str | None
    pcr_oi: float
    pcr_change: float
    open_ts: str
    now_ts: str
    data_quality: str
    # True when the 09:15 baseline was derived from the broker's day-change
    # field rather than read from a stored capture — which is what happens
    # whenever the ingest worker started after the bell.
    open_is_estimated: bool = False
    total_call_oi: int
    total_put_oi: int
    total_call_oi_chg: int
    total_put_oi_chg: int
    sentiment: SentimentResponse
    strikes: list[StrikeOiResponse]
    series: list[SeriesFrameResponse]

    @classmethod
    def of(cls, payload: dict[str, Any]) -> OiViewResponse:
        return cls.model_validate(payload)


class ContractSeriesResponse(_Schema):
    """One contract's day, aligned to the payload's shared time axis.

    ``oi_change`` is absent on purpose: index 0 is the session open, so the
    client derives ``oi[i] - oi[0]``. Sending it as well would be a third array
    per contract carrying no new information — and a second source of truth for
    a figure the Open Interest page derives the same way.
    """

    id: str
    strike: float
    option_type: str
    # `None` before a leg's first appearance. A strike listed part-way through
    # the morning was not quoted at the open; 0 would draw it along the axis and
    # then leap, inventing a build that never happened.
    oi: list[int | None]
    volume: list[int | None]


class OiSeriesResponse(_Schema):
    """Per-contract intraday series behind Multi OI & Volume."""

    instrument_id: str
    symbol: str
    expiry_date: str | None
    atm_strike: float
    lot_size: int | None
    open_ts: str
    now_ts: str
    data_quality: str
    open_is_estimated: bool = False
    # The bucket actually used, which can be coarser than the one requested:
    # no interval can produce resolution finer than the capture cadence.
    interval: str
    window: int
    t: list[str]
    # Aligned to `t`. The tradable current-month future, not index spot — and
    # `None` on the reconstructed 09:15 frame, where nothing was recorded.
    fut: list[float | None]
    contracts: list[ContractSeriesResponse]
    default_ids: list[str]
    default_vol_ids: list[str]

    @classmethod
    def of(cls, payload: dict[str, Any]) -> OiSeriesResponse:
        return cls.model_validate(payload)


class PriceOiSeriesResponse(_Schema):
    """The intraday price-vs-OI series behind Future Lab → Price vs OI.

    Two aggregate lines on a shared time axis: the tradable future price and the
    whole chain's total open interest.
    """

    instrument_id: str
    symbol: str
    expiry_date: str | None
    lot_size: int | None
    open_ts: str
    now_ts: str
    data_quality: str
    open_is_estimated: bool = False
    interval: str
    t: list[str]
    # Aligned to `t`. The tradable current-month future, `None` on the
    # reconstructed 09:15 frame where nothing was recorded.
    price: list[float | None]
    # Aligned to `t`. Total open interest across the whole captured chain.
    oi: list[int]

    @classmethod
    def of(cls, payload: dict[str, Any]) -> PriceOiSeriesResponse:
        return cls.model_validate(payload)


class PcrSeriesResponse(_Schema):
    """Chain-wide totals behind the Put-Call Ratio tool's three charts."""

    instrument_id: str
    symbol: str
    expiry_date: str | None
    lot_size: int | None
    open_ts: str
    now_ts: str
    data_quality: str
    open_is_estimated: bool = False
    t: list[str]
    # The tradable current-month future, not index spot. `None` on the
    # reconstructed 09:15 frame, where nothing was recorded.
    fut: list[float | None]
    # `None`, never 0, where there was no call interest to divide by: a ratio
    # with an empty denominator is undefined, and 0 would draw a floor the
    # market never printed.
    pcr: list[float | None]
    call_oi: list[int]
    put_oi: list[int]
    call_oi_chg: list[int]
    put_oi_chg: list[int]

    @classmethod
    def of(cls, payload: dict[str, Any]) -> PcrSeriesResponse:
        return cls.model_validate(payload)


class MaxPainSeriesResponse(_Schema):
    """Max pain through the session, behind the Intraday Max Pain chart."""

    instrument_id: str
    symbol: str
    expiry_date: str | None
    lot_size: int | None
    spot: float
    open_ts: str
    now_ts: str
    data_quality: str
    open_is_estimated: bool = False
    t: list[str]
    # The tradable current-month future, not index spot. `None` on the
    # reconstructed 09:15 frame, where nothing was recorded.
    fut: list[float | None]
    # `None`, never 0, where a capture could not be priced. Zero would drag the
    # shared price scale to the floor and read as a crash that never happened.
    max_pain: list[float | None]

    @classmethod
    def of(cls, payload: dict[str, Any]) -> MaxPainSeriesResponse:
        return cls.model_validate(payload)


class StrikeSeriesResponse(_Schema):
    """One strike's price/OI series behind the six Price vs OI charts."""

    instrument_id: str
    symbol: str
    expiry_date: str | None
    lot_size: int | None
    spot: float
    atm_strike: float | None
    # The strike this payload plots, and the ladder the sidebar chooses from.
    strike: float
    strikes: list[float]
    open_ts: str
    now_ts: str
    data_quality: str
    open_is_estimated: bool = False
    t: list[str]
    # `None` where a leg was absent from the capture; a genuine 0 print is kept.
    ce_price: list[float | None]
    pe_price: list[float | None]
    ce_oi: list[int | None]
    pe_oi: list[int | None]
    ce_oi_change: list[int | None]
    pe_oi_change: list[int | None]
    # Call + put price; `None` where either leg was unquoted.
    straddle: list[float | None]
    # Per-strike put/call ratio; `None`, never 0, at an empty call-OI denominator.
    pcr: list[float | None]

    @classmethod
    def of(cls, payload: dict[str, Any]) -> StrikeSeriesResponse:
        return cls.model_validate(payload)


class GexFrameResponse(_Schema):
    """One capture's gamma profile, plus the levels read off it.

    The four levels are per-frame, not per-payload: scrubbing back to 11:00 must
    move the wall and flip markers with the bars, or the chart shows this
    morning's structure against this afternoon's positioning.
    """

    t: str
    spot: float
    #: `None` on captures taken before the ATM column was denormalised.
    atm: float | None
    # Aligned to the payload's `strikes`. Rupee gamma per 1% move in spot,
    # expressed in **crore** — see `gex_service` for why the unit is on the
    # wire rather than applied by the client.
    #
    # Signed for the dealer view: calls positive, puts negative.
    call_gex: list[float]
    put_gex: list[float]
    #: The two headline figures, same unit.
    net_total: float
    abs_total: float
    # Every level is nullable. A one-sided book has no wall, and a profile that
    # never changes sign has no flip — `None` says so, where 0 would plant a
    # marker at the bottom of the ladder.
    call_wall: float | None
    put_wall: float | None
    gamma_flip: float | None
    net_cross: float | None


class GexResponse(_Schema):
    """Per-strike gamma exposure behind the Gamma Exposure tool."""

    instrument_id: str
    symbol: str
    expiry_date: str | None
    lot_size: int | None
    spot: float
    atm_strike: float | None
    open_ts: str
    now_ts: str
    data_quality: str
    #: Always `False` here — gamma has no reconstructable session open.
    open_is_estimated: bool = False
    # Fraction of legs that carried a quoted implied volatility, 0-1. Without
    # it, a chain the broker priced no volatility on renders as a flat profile
    # indistinguishable from a balanced book.
    iv_coverage: float
    #: The shared strike axis every frame's arrays are aligned to.
    strikes: list[float]
    t: list[str]
    frames: list[GexFrameResponse]

    @classmethod
    def of(cls, payload: dict[str, Any]) -> GexResponse:
        return cls.model_validate(payload)


class VegaFrameResponse(_Schema):
    """One capture's aggregate-vega profile, plus the synthetic future.

    The two vega arrays are aligned to the payload's ``strikes`` and are the
    per-strike aggregate vega on each side, in **crore** per one volatility
    point. Both sides are positive; the page plots each side's change since the
    open, and that delta is what carries the sign the chart reads.
    """

    t: str
    spot: float
    #: `None` on captures taken before the ATM column was denormalised.
    atm: float | None
    #: Put-call parity forward at the money, falling back to the tradable
    #: future; `None` only when neither is available for this capture.
    synth_future: float | None
    call_vega: list[float]
    put_vega: list[float]


class VegaResponse(_Schema):
    """Per-strike vega exposure behind the Vega Analysis tool."""

    instrument_id: str
    symbol: str
    expiry_date: str | None
    lot_size: int | None
    spot: float
    atm_strike: float | None
    open_ts: str
    now_ts: str
    data_quality: str
    #: Always `False` here — vega has no reconstructable session open.
    open_is_estimated: bool = False
    # Fraction of legs that carried a quoted implied volatility, 0-1. Without
    # it, a chain the broker priced no volatility on renders as a flat profile
    # indistinguishable from a balanced book.
    iv_coverage: float
    #: The shared strike axis every frame's arrays are aligned to.
    strikes: list[float]
    t: list[str]
    frames: list[VegaFrameResponse]

    @classmethod
    def of(cls, payload: dict[str, Any]) -> VegaResponse:
        return cls.model_validate(payload)


class StraddleChartSeriesResponse(_Schema):
    """The plotted arrays, all aligned index-for-index with `t`."""

    t: list[str]
    #: The at-the-money strike each point was priced at — it rolls.
    strike: list[float]
    ce: list[float | None]
    pe: list[float | None]
    straddle: list[float]
    spot: list[float | None]
    #: Put-call parity forward, falling back to the tradable future.
    synthetic: list[float | None]


class StraddleChartResponse(_Schema):
    """The rolling at-the-money straddle behind the Straddle Chart tool."""

    instrument_id: str
    symbol: str
    expiry_date: str | None
    lot_size: int | None
    #: The right edge of the chart: what it costs to be at the money now.
    straddle_price: float | None
    atm_strike: float | None
    ce_ltp: float | None
    pe_ltp: float | None
    spot: float | None
    synthetic_future: float | None
    requested_sessions: int
    #: Sessions actually covered. The archive accrues forward and is pruned, so
    #: a request for three days may honestly answer with one.
    covered_sessions: int
    open_ts: str
    now_ts: str
    #: `intraday`, `live` (one point from the live chain) or `empty`.
    data_quality: str
    rolling_strike: bool
    series: StraddleChartSeriesResponse

    @classmethod
    def of(cls, payload: dict[str, Any]) -> StraddleChartResponse:
        return cls.model_validate(payload)


class GreekLegResponse(_Schema):
    """One leg's five series, aligned index-for-index with the payload's `t`.

    Every value is nullable: a capture whose leg the broker quoted no implied
    volatility on has nothing to state, and a gap in the line is the honest
    render of that. Zero would draw as a real, calm reading.
    """

    #: Implied volatility in points (14.25 means 14.25%).
    iv: list[float | None]
    #: Per unit of underlying; positive for calls, negative for puts.
    delta: list[float | None]
    #: Delta change per one-point move in the underlying.
    gamma: list[float | None]
    #: Rupees per calendar day; negative for a long option.
    theta: list[float | None]
    #: Rupees per one-point (1%) move in implied volatility.
    vega: list[float | None]
    #: The leg's own last traded price.
    ltp: list[float | None]


class GreeksSeriesResponse(_Schema):
    """Intraday greeks for one strike behind the Option Greeks tool."""

    instrument_id: str
    symbol: str
    expiry_date: str | None
    lot_size: int | None
    #: The pinned strike every series is read at; `None` only on an empty payload.
    strike: float | None
    atm_strike: float | None
    spot: float
    #: Display symbols for the two legs, e.g. `NIFTY06OCT2622400CE`.
    ce_symbol: str | None
    pe_symbol: str | None
    open_ts: str
    now_ts: str
    #: `intraday` (archived captures), `live` (one point from the live chain) or
    #: `empty`.
    data_quality: str
    #: Share of frames, 0-1, where both legs carried a usable implied volatility.
    iv_coverage: float
    t: list[str]
    #: The tradable future at each capture, for context under the greek.
    underlying: list[float]
    ce: GreekLegResponse
    pe: GreekLegResponse

    @classmethod
    def of(cls, payload: dict[str, Any]) -> GreeksSeriesResponse:
        return cls.model_validate(payload)


class IvSessionResponse(_Schema):
    """One session's closing at-the-money implied volatility."""

    #: IST trading date, `YYYY-MM-DD`.
    d: str
    #: Volatility points (13.2 means 13.2%).
    iv: float
    #: The tradable future at the same capture; `None` on older rows.
    future_close: float | None
    #: Intraday captures behind the reading.
    captures: int


class IvHistoryResponse(_Schema):
    """Daily implied-volatility history behind the IV/HV/IVP Chart."""

    instrument_id: str
    symbol: str
    #: The window asked for, after clamping to 1-365.
    requested_days: int
    # Sessions actually stored in that window. The archive only began accruing
    # when the rollup landed, so this is routinely far short of `requested_days`
    # — and a page that cannot tell a short history from a flat one draws a
    # confident, wrong IV Percentile.
    covered_sessions: int
    start: str
    end: str
    sessions: list[IvSessionResponse]

    @classmethod
    def of(cls, payload: dict[str, Any]) -> IvHistoryResponse:
        return cls.model_validate(payload)


class TermPointResponse(_Schema):
    """One expiry's at-the-money implied volatility."""

    #: The expiry the broker actually answered with, `YYYY-MM-DD`.
    expiry: str
    #: Volatility points; `None` where that chain quoted none at the money —
    #: never interpolated from a neighbour.
    atm_iv: float | None
    #: Calendar days from the IST trading date; `None` on an unparseable expiry.
    days_to_expiry: int | None


class TermStructureResponse(_Schema):
    """Live at-the-money volatility across expiries.

    Live only, and deliberately so: a term structure is several expiries priced
    at one instant, and the snapshot archive holds a single expiry per session.
    There is no historical term structure to serve, so there is no date param.
    """

    instrument_id: str
    symbol: str
    spot: float
    as_of: str
    #: Sorted by expiry, oldest first — a curve is read along the calendar.
    points: list[TermPointResponse]

    @classmethod
    def of(cls, payload: dict[str, Any]) -> TermStructureResponse:
        return cls.model_validate(payload)


class SkewFrameResponse(_Schema):
    """One capture's per-strike implied volatility and open interest.

    All four arrays are aligned to the payload's ``strikes``. ``ce_iv`` /
    ``pe_iv`` are volatility points as quoted, `None` where that leg carried no
    IV — never `0.0`, which would read as a real (and impossible) volatility.
    The two OI arrays are contracts, and `0` where the leg was not quoted: a leg
    nobody quoted holds no position, which unlike volatility is a fact.
    """

    t: str
    spot: float
    #: `None` on captures taken before the ATM column was denormalised.
    atm: float | None
    #: The tradable future at this capture, falling back to spot on rows older
    #: than that column; `None` when neither was recorded.
    future: float | None
    ce_iv: list[float | None]
    pe_iv: list[float | None]
    call_oi: list[int]
    put_oi: list[int]


class SkewResponse(_Schema):
    """Per-strike volatility and open interest behind the Volatility Skew tool."""

    instrument_id: str
    symbol: str
    expiry_date: str | None
    lot_size: int | None
    spot: float
    atm_strike: float | None
    open_ts: str
    now_ts: str
    data_quality: str
    #: Always `False` here — the skew has no reconstructable session open.
    open_is_estimated: bool = False
    # Fraction of legs that carried a quoted implied volatility, 0-1. Without
    # it, a chain the broker priced no volatility on renders as an empty curve
    # indistinguishable from a strike range nobody trades.
    iv_coverage: float
    #: The shared strike axis every frame's arrays are aligned to.
    strikes: list[float]
    t: list[str]
    frames: list[SkewFrameResponse]

    @classmethod
    def of(cls, payload: dict[str, Any]) -> SkewResponse:
        return cls.model_validate(payload)


class StraddleFrameResponse(_Schema):
    """One capture's per-strike premiums, the rolling ATM straddle, the future.

    ``ce_ltp`` / ``pe_ltp`` are aligned to the payload's ``strikes`` — each
    strike's last call and put price, `None` where that leg was not quoted in
    the frame. ``atm_straddle`` is `call + put` at the money for the frame, the
    rolling line the chart draws by default; `None` when the ATM legs are gone.
    """

    t: str
    spot: float
    #: `None` on captures taken before the ATM column was denormalised.
    atm: float | None
    #: The tradable future overlay; `None` only when neither future nor spot is
    #: available for this capture.
    future: float | None
    atm_straddle: float | None
    ce_ltp: list[float | None]
    pe_ltp: list[float | None]


class StraddleSeriesResponse(_Schema):
    """Intraday per-strike straddle premiums behind the ATM Straddle Chart."""

    instrument_id: str
    symbol: str
    expiry_date: str | None
    lot_size: int | None
    spot: float
    atm_strike: float | None
    open_ts: str
    now_ts: str
    data_quality: str
    #: Always `False` here — a straddle premium has no reconstructable open.
    open_is_estimated: bool = False
    #: The shared strike axis every frame's arrays are aligned to.
    strikes: list[float]
    t: list[str]
    frames: list[StraddleFrameResponse]

    @classmethod
    def of(cls, payload: dict[str, Any]) -> StraddleSeriesResponse:
        return cls.model_validate(payload)


class SmartOiBarResponse(_Schema):
    """One price bar of the underlying, at the requested interval."""

    t: str
    o: float
    h: float
    l: float  # noqa: E741 — `l` is the OHLC convention the chart client reads.
    c: float


class SmartOiResponse(_Schema):
    """Everything the Smart OI page draws, on its two deliberate axes.

    The frame arrays (`t` .. `vol_pcr`) share one length and describe the
    archive's capture cadence. The bar arrays (`bars`, `smart_oi`, `call_vol`,
    `put_vol`) share a *different* length and describe the candle grid. They are
    not interchangeable and nothing should zip one against the other.
    """

    instrument_id: str
    symbol: str
    expiry_date: str | None
    lot_size: int | None
    atm_strike: float
    open_ts: str
    now_ts: str
    data_quality: str
    open_is_estimated: bool = False
    # The bucket actually used, which can be coarser than the one requested when
    # the ingest cadence cannot deliver it.
    interval: str
    # The strikes actually summed, for the toolbar's "(21200 - 27200)" readout.
    # `None` when there is no chain to window.
    strike_low: float | None
    strike_high: float | None

    # -- frame axis --
    t: list[str]
    # The tradable current-month future, not index spot. `None` on the
    # reconstructed 09:15 frame, where nothing was recorded.
    fut: list[float | None]
    call_oi_chg: list[int]
    put_oi_chg: list[int]
    # Put minus call OI change: the level whose first difference is Smart OI.
    pe_ce_chg: list[int]
    # `None`, never 0, where the denominator was empty — see `PcrSeriesResponse`.
    oi_pcr: list[float | None]
    vol_pcr: list[float | None]

    # -- bar axis --
    bars: list[SmartOiBarResponse]
    # Per-bar flows, aligned to `bars`. `None` where no capture landed in that
    # bar, which is not the same statement as "nothing was written in it".
    smart_oi: list[int | None]
    call_vol: list[int | None]
    put_vol: list[int | None]

    @classmethod
    def of(cls, payload: dict[str, Any]) -> SmartOiResponse:
        return cls.model_validate(payload)
