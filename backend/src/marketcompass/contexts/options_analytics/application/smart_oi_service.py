"""Chain-wide OI flow read against the underlying's own price, for Smart OI.

Where the Put-Call Ratio tool collapses the chain to one number per side per
capture and plots it against the synthetic future, this plots it against real
candles and asks a different question: not "where does the book stand" but
"what was added to it *during this bar*".

That difference is the whole page. ``pe_ce_chg`` is a level — puts minus calls
written since the bell — and it only ever drifts. Its first difference is a
flow, and a flow has a sign per bar: green where puts were written into a bar
(support being sold), red where calls were. That per-bar series is "Smart OI".

Two axes ship, deliberately, and conflating them is the easy mistake here:

* the **frame axis** (``t``) is the archive's own capture cadence, and carries
  the cumulative lines and both ratios. It stays raw because those are levels;
  thinning them only costs resolution.
* the **bar axis** (``bars``) is the candle grid, and carries the three per-bar
  flows. It exists because a histogram under a candlestick has to line up with
  the candles or it is describing a different market.

Strike windowing applies to both. A "PCR" computed over 300 strikes is
dominated by wings nobody is trading; the reader picks the window and every
total on the page respects it.

Tiers, as on the Open Interest page:

    INTRADAY   (>=2 stored captures today) — real open vs the whole session
    LIVE_PROXY (0 or 1)                    — open-vs-now off the live chain
    EMPTY      (before the bell)           — no session to draw two ends of

Candles are fetched independently of that tier: the price pane is real history
from the broker either way, so a machine with no ingest worker still draws a
chart rather than an empty panel.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from marketcompass.contexts.options_analytics.application.oi_series_service import (
    _anchor_atm,
    _effective_interval,
    _infer_step,
)
from marketcompass.contexts.options_analytics.application.ports import (
    Candle,
    CandleSource,
    ChainProvider,
    ChainSnapshot,
    ProviderChain,
    SnapshotReader,
)
from marketcompass.contexts.options_analytics.application.session import (
    attach_utc,
    drop_future,
    future_of,
    iso,
    live_proxy_frames,
    session_open_frame,
    session_open_utc,
)
from marketcompass.contexts.options_analytics.domain.oi_math import (
    ChainRow,
    rows_within,
    strike_window,
)
from marketcompass.shared_kernel.types.identifiers import TenantId

# Bucket sizes this page offers, in seconds. Deliberately not the Multi OI set:
# a price chart wants 3m and does not want 1h, and both are ordinary readings of
# an intraday tape. Every one of these divides the 09:15 IST bell evenly when
# bucketed on absolute epoch seconds, which is why the first bar starts at the
# open rather than straddling it.
INTERVALS: dict[str, int] = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
}
DEFAULT_INTERVAL = "5m"

# Strikes either side of ATM the window may reach. Matches ``MAX_WINDOW`` on the
# Multi OI endpoint so the two pages cannot disagree about what "± 40" means.
MAX_SPAN = 40

MODE_AUTO = "auto"
MODE_FIXED = "fixed"

_MIN_INTRADAY_SNAPSHOTS = 2
_MINUTE = 60


class GetSmartOi:
    """Assembles the Smart OI payload for one instrument."""

    def __init__(
        self,
        *,
        provider: ChainProvider,
        snapshots: SnapshotReader,
        candles: CandleSource,
        now_utc: Any = None,
    ) -> None:
        self._provider = provider
        self._snapshots = snapshots
        self._candles = candles
        self._now = now_utc or (lambda: datetime.now(UTC))

    async def __call__(
        self,
        tenant_id: TenantId,
        symbol: str,
        *,
        interval: str = DEFAULT_INTERVAL,
        mode: str = MODE_AUTO,
        span: int | None = None,
        min_strike: float | None = None,
        max_strike: float | None = None,
        expiry: str | None = None,
        trade_date: datetime | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        # Live reads today; Historical replays the picked archived session.
        as_of = trade_date or now
        bucket = INTERVALS.get(interval, INTERVALS[DEFAULT_INTERVAL])
        reach = None if span is None else max(1, min(MAX_SPAN, span))

        chain = await self._provider.fetch(tenant_id, symbol, expiry=expiry)
        bars = await self._candles.minute_candles(tenant_id, symbol, trade_date_utc=as_of)
        if trade_date is None:
            # A bar that has not opened yet is not a bar. Real feeds do not send
            # one, but a seeded day can, and it would draw the chart into the
            # future while every other panel stopped at now.
            bars = [candle for candle in bars if attach_utc(candle.opened_at) <= now]

        snaps = await self._snapshots.day_snapshots(tenant_id, symbol, trade_date_utc=as_of)
        # Only the live day is clipped to "now"; a past session is whole.
        if trade_date is None:
            snaps = drop_future(snaps, now)

        window = _Window(mode=mode, span=reach, low=min_strike, high=max_strike)

        if len(snaps) < _MIN_INTRADAY_SNAPSHOTS:
            # A past day with nothing archived is empty — never today's live chain.
            if trade_date is not None:
                return _empty(symbol, chain, now, interval=interval, bars=bars, bucket=bucket)
            return self._live_proxy(
                symbol,
                chain,
                snaps,
                now,
                interval=interval,
                bars=bars,
                bucket=bucket,
                window=window,
            )

        ordered = sorted(snaps, key=lambda snap: snap.captured_at)
        reconstructed = session_open_frame(ordered)
        if reconstructed is not None:
            ordered = [reconstructed, *ordered]

        return _payload(
            symbol,
            chain,
            ordered,
            bars=bars,
            bucket=bucket,
            window=window,
            quality="intraday",
            open_is_estimated=reconstructed is not None,
            # What the archive could actually deliver, not what was asked for.
            interval=_effective_interval(bucket, snaps),
        )

    def _live_proxy(
        self,
        symbol: str,
        chain: ProviderChain,
        snaps: list[ChainSnapshot],
        now: datetime,
        *,
        interval: str,
        bars: list[Candle],
        bucket: int,
        window: _Window,
    ) -> dict[str, Any]:
        """The tier for a day the ingest worker has not archived.

        Mirrors ``GetPcrSeries``: one stored capture if there is one, otherwise
        the live chain, with the 09:15 baseline reconstructed from each leg's
        ``oi_change``. Two frames is enough to state where the book stands; it
        is not enough to say *when* it got there, so the per-bar flows collapse
        onto whichever bar the live capture lands in and the rest read ``None``.
        That is the honest shape — a page with no archive genuinely cannot tell
        the reader which bar the writing happened in.
        """
        stored = snaps[0] if snaps else None
        rows = stored.rows if stored is not None else chain.rows
        spot = (stored.spot if stored is not None else None) or chain.spot
        frames = live_proxy_frames(
            rows,
            now,
            spot=spot,
            future_price=stored.future_price if stored is not None else None,
        )
        if not frames:
            return _empty(symbol, chain, now, interval=interval, bars=bars, bucket=bucket)

        return _payload(
            symbol,
            chain,
            frames,
            bars=bars,
            bucket=bucket,
            window=window,
            quality="live_proxy",
            open_is_estimated=True,
            interval=interval,
        )


class _Window:
    """How the strike filter is chosen, and what it resolves to for a frame.

    Three ways to ask for the same thing, in priority order:

    * an explicit ``[low, high]`` — the toolbar's Custom tab, absolute levels;
    * ``fixed`` — ``span`` steps around the ATM **at the session open**, pinned,
      so the totals series is measured over one unchanging set of strikes;
    * ``auto`` — ``span`` steps around *this frame's* ATM, so the window follows
      a trending market and always describes the money at play.

    The distinction matters more than it looks: on a day that trends 400 points,
    ``auto`` keeps reporting the near strikes while ``fixed`` watches the same
    ladder drift out of the money. Both are legitimate readings, and a chart
    that silently switches between them is neither.
    """

    __slots__ = ("_high", "_low", "_pinned", "mode", "span")

    def __init__(
        self, *, mode: str, span: int | None, low: float | None, high: float | None
    ) -> None:
        self.mode = MODE_FIXED if mode == MODE_FIXED else MODE_AUTO
        self.span = span
        self._low = low
        self._high = high
        self._pinned: tuple[float, float] | None = None

    def pin(self, atm: float, step: float) -> None:
        """Fix the window to ``atm``, for the modes that do not track it."""
        self._pinned = strike_window(atm=atm, step=step, span=self.span)

    def bounds(self, atm: float, step: float) -> tuple[float, float]:
        if self._low is not None and self._high is not None:
            return (self._low, self._high)
        if self.mode == MODE_FIXED and self._pinned is not None:
            return self._pinned
        return strike_window(atm=atm, step=step, span=self.span)


class _Totals:
    """One capture collapsed to a per-side summary, over the windowed strikes."""

    __slots__ = (
        "call_chg",
        "call_oi",
        "call_vol",
        "oi_pcr",
        "pe_ce_chg",
        "put_chg",
        "put_oi",
        "put_vol",
        "vol_pcr",
    )

    def __init__(self, rows: tuple[ChainRow, ...]) -> None:
        call_oi = put_oi = call_chg = put_chg = call_vol = put_vol = 0
        for row in rows:
            if row.is_call:
                call_oi += row.oi
                call_chg += row.oi_change
                call_vol += row.volume
            else:
                put_oi += row.oi
                put_chg += row.oi_change
                put_vol += row.volume

        self.call_oi = call_oi
        self.put_oi = put_oi
        # Summed from the legs' own day-change rather than differenced against
        # the open. The broker's `oi_change` is the authority, and the two
        # diverge the moment a strike is delisted mid-session.
        self.call_chg = call_chg
        self.put_chg = put_chg
        self.call_vol = call_vol
        self.put_vol = put_vol
        self.pe_ce_chg = put_chg - call_chg
        # `None`, never 0, when there is nothing to divide by — the same rule
        # `GetPcrSeries` documents. A ratio line at 0 draws a floor the market
        # never printed and anchors the axis to it, where `None` simply breaks.
        self.oi_pcr = (put_oi / call_oi) if call_oi > 0 else None
        self.vol_pcr = (put_vol / call_vol) if call_vol > 0 else None


def _payload(
    symbol: str,
    chain: ProviderChain,
    frames: list[ChainSnapshot],
    *,
    bars: list[Candle],
    bucket: int,
    window: _Window,
    quality: str,
    open_is_estimated: bool,
    interval: str,
) -> dict[str, Any]:
    step = _infer_step(sorted({row.strike for frame in frames for row in frame.rows}))
    window.pin(_anchor_atm(_opening_anchor(frames), chain), step)

    totals: list[_Totals] = []
    low = high = None
    for frame in frames:
        bounds = window.bounds(_anchor_atm(frame, chain), step)
        totals.append(_Totals(rows_within(frame.rows, *bounds)))
        low, high = bounds

    anchor = frames[-1]
    candles = _aggregate(bars, bucket)
    flows = _bar_flows(candles, frames, totals, bucket)

    return {
        "instrument_id": symbol,
        "symbol": symbol,
        "expiry_date": chain.expiry,
        "lot_size": chain.lot_size,
        "atm_strike": _anchor_atm(anchor, chain),
        "open_ts": iso(frames[0].captured_at),
        "now_ts": iso(anchor.captured_at),
        "data_quality": quality,
        "open_is_estimated": open_is_estimated,
        "interval": interval,
        # The readout under the toolbar. Reported as the strikes actually
        # summed rather than the requested arithmetic bounds, so "All" reads as
        # the real ladder instead of ±infinity, and a window wider than the
        # chain reads as the chain.
        **_reported_bounds(frames[-1].rows, low, high),
        # -- frame axis: the archive's cadence, for the cumulative lines --
        "t": [iso(frame.captured_at) for frame in frames],
        "fut": [future_of(frame) for frame in frames],
        "call_oi_chg": [total.call_chg for total in totals],
        "put_oi_chg": [total.put_chg for total in totals],
        "pe_ce_chg": [total.pe_ce_chg for total in totals],
        "oi_pcr": [total.oi_pcr for total in totals],
        "vol_pcr": [total.vol_pcr for total in totals],
        # -- bar axis: the candle grid, for the price pane and its histograms --
        "bars": [
            {
                "t": iso(candle.opened_at),
                "o": candle.open,
                "h": candle.high,
                "l": candle.low,
                "c": candle.close,
            }
            for candle in candles
        ],
        "smart_oi": flows["smart_oi"],
        "call_vol": flows["call_vol"],
        "put_vol": flows["put_vol"],
    }


def _reported_bounds(
    rows: tuple[ChainRow, ...], low: float | None, high: float | None
) -> dict[str, float | None]:
    listed = sorted({row.strike for row in rows}) if rows else []
    if not listed or low is None or high is None:
        return {"strike_low": None, "strike_high": None}
    inside = [strike for strike in listed if low - 1e-6 <= strike <= high + 1e-6]
    if not inside:
        return {"strike_low": None, "strike_high": None}
    return {"strike_low": inside[0], "strike_high": inside[-1]}


# -- shaping ----------------------------------------------------------------


def _opening_anchor(frames: list[ChainSnapshot]) -> ChainSnapshot:
    """The earliest frame that knows where the market was.

    ``frames[0]`` is usually the reconstructed 09:15 open, which deliberately
    carries no spot — nobody recorded one. Pinning ``fixed`` mode to it would
    fall through to the *live* chain's spot, i.e. to now, which is the one thing
    a window pinned to the open must not follow. The first real observation is
    the closest honest answer to "where was the money at the open".
    """
    for frame in frames:
        if frame.atm_strike is not None or frame.spot is not None:
            return frame
    return frames[0]


def _bucket_of(moment: datetime, bucket: int) -> int:
    """The bucket a moment falls in, keyed on absolute epoch seconds.

    Absolute rather than relative to the first frame, because the candles and
    the captures have to land in the *same* buckets and they do not start at the
    same instant. Every interval this page offers divides the 09:15 IST bell
    evenly, so bucket boundaries fall on the open.
    """
    return int(attach_utc(moment).timestamp()) // bucket


def _aggregate(bars: list[Candle], bucket: int) -> list[Candle]:
    """One-minute bars rolled up to the display interval.

    Open from the first minute, close from the last, high and low from the
    extremes — the only aggregation that is still a real bar. Incomplete
    buckets are kept: the newest bar of a live session is always incomplete,
    and dropping it would leave the chart a full interval behind the price the
    rest of the page is quoting.
    """
    if not bars:
        return []
    if bucket <= _MINUTE:
        return list(bars)

    rolled: list[Candle] = []
    current_key: int | None = None
    for bar in bars:
        key = _bucket_of(bar.opened_at, bucket)
        if key != current_key:
            rolled.append(bar)
            current_key = key
            continue
        open_bar = rolled[-1]
        rolled[-1] = Candle(
            opened_at=open_bar.opened_at,
            open=open_bar.open,
            high=max(open_bar.high, bar.high),
            low=min(open_bar.low, bar.low),
            close=bar.close,
        )
    return rolled


def _bar_flows(
    candles: list[Candle],
    frames: list[ChainSnapshot],
    totals: list[_Totals],
    bucket: int,
) -> dict[str, list[int | None]]:
    """The three per-bar flows, aligned one-to-one with ``candles``.

    Each is the first difference of a cumulative quantity — OI change since the
    bell, and volume traded since the bell — so a bar's value is what was added
    *during* it.

    The last capture in a bucket wins, for the reason ``_downsample`` gives:
    open interest and cumulative volume are stocks, and a bucket's mean is a
    reading the market never printed.

    A bar with no capture in it reads ``None``, not ``0``: on a cadence coarser
    than the chart's interval most bars genuinely have no observation, and
    drawing them as zero-height bars claims — wrongly — that nothing was written
    in them. The next bar that *does* have a capture carries the whole interval's
    flow, which is the most the archive can honestly attribute.

    The baseline is zero, not the first bucket's level: at 09:15 nothing had
    been written and nothing had traded, so the opening bar's flow is the whole
    move off the bell.
    """
    empty: list[int | None] = [None] * len(candles)
    if not candles:
        return {"smart_oi": [], "call_vol": [], "put_vol": []}

    latest: dict[int, _Totals] = {}
    for frame, total in zip(frames, totals, strict=True):
        latest[_bucket_of(frame.captured_at, bucket)] = total

    smart: list[int | None] = list(empty)
    call: list[int | None] = list(empty)
    put: list[int | None] = list(empty)

    previous = (0, 0, 0)
    for index, candle in enumerate(candles):
        key = _bucket_of(candle.opened_at, bucket)
        if key not in latest:
            continue
        total = latest[key]
        current = (total.pe_ce_chg, total.call_vol, total.put_vol)
        smart[index] = current[0] - previous[0]
        call[index] = current[1] - previous[1]
        put[index] = current[2] - previous[2]
        previous = current

    return {"smart_oi": smart, "call_vol": call, "put_vol": put}


def _empty(
    symbol: str,
    chain: ProviderChain,
    now: datetime,
    *,
    interval: str,
    bars: list[Candle],
    bucket: int,
) -> dict[str, Any]:
    """A well-formed payload for a day with no option series to draw.

    Not an error: before two captures land there is genuinely no OI flow. The
    candles still ship — they come from a different upstream and are perfectly
    good — so the page renders a price chart with empty histograms rather than
    nothing at all.
    """
    candles = _aggregate(bars, bucket)
    return {
        "instrument_id": symbol,
        "symbol": symbol,
        "expiry_date": chain.expiry,
        "lot_size": chain.lot_size,
        "atm_strike": _anchor_atm(None, chain),
        "open_ts": iso(session_open_utc(now)),
        "now_ts": iso(now),
        "data_quality": "empty",
        "open_is_estimated": False,
        "interval": interval,
        "strike_low": None,
        "strike_high": None,
        "t": [],
        "fut": [],
        "call_oi_chg": [],
        "put_oi_chg": [],
        "pe_ce_chg": [],
        "oi_pcr": [],
        "vol_pcr": [],
        "bars": [
            {
                "t": iso(candle.opened_at),
                "o": candle.open,
                "h": candle.high,
                "l": candle.low,
                "c": candle.close,
            }
            for candle in candles
        ],
        "smart_oi": [None] * len(candles),
        "call_vol": [None] * len(candles),
        "put_vol": [None] * len(candles),
    }
