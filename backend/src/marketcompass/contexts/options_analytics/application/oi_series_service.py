"""Per-contract intraday series for the Multi OI & Volume tool.

Where ``GetOiView`` answers "what does the whole chain look like at one instant",
this answers "what have these particular contracts done all day". Same archive,
transposed: a shared time axis plus one open-interest and one volume array per
contract, with the tradable future overlaid.

Three shapes of the payload are deliberate and easy to get wrong later:

* **One shared time axis.** Repeating a timestamp inside every contract would
  add roughly 40% to the JSON for no new information, and a multi-series line
  chart wants exactly this shape anyway.
* **``oi_change`` is not sent.** Point 0 is the session open, so the client
  derives ``oi[i] - oi[0]`` — the same derivation the Open Interest page already
  makes. Sending it too would create a second source of truth for a number the
  two pages have to agree on.
* **Every contract in the window ships, not just the five on screen.** Changing
  which contracts are plotted is then instant instead of a round trip, which is
  the same reasoning behind the OI page's client-side re-derivation.

Downsampling happens here rather than on the client because it is the main lever
on payload size.

Tiers, as on the Open Interest page:

    INTRADAY   (>=2 stored captures today) — real open vs the whole session
    LIVE_PROXY (0 or 1)                    — open-vs-now off the live chain
    EMPTY      (before the bell)           — no session to draw two ends of
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from itertools import pairwise
from typing import Any

from marketcompass.contexts.options_analytics.application.ports import (
    ChainProvider,
    ChainSnapshot,
    ProviderChain,
    SnapshotReader,
)
from marketcompass.contexts.options_analytics.application.session import (
    attach_utc,
    drop_future,
    future_of as _future_of,
    iso as _iso,
    live_proxy_frames,
    session_open_frame,
    session_open_utc,
)
from marketcompass.contexts.options_analytics.domain.oi_math import ChainRow, atm_strike
from marketcompass.shared_kernel.types.identifiers import TenantId

# Bucket sizes the UI offers, in seconds. A request cannot produce resolution
# finer than the capture cadence, so the smallest of these is a floor, not a
# promise — the response reports the interval actually used.
INTERVALS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
}
DEFAULT_INTERVAL = "1m"

# Strikes either side of ATM. Wide enough that the Custom Strikes picker has
# something worth searching, bounded so a shifting ladder cannot grow the
# payload without limit.
DEFAULT_WINDOW = 20
MAX_WINDOW = 40

# How many contracts the two "top N" pickers pre-select.
_DEFAULT_PICK = 5
_MIN_INTRADAY_SNAPSHOTS = 2

_MINUTE = 60
_HOUR = 3600
# How many recent captures the reported cadence is read from. Long enough to
# ignore a single late tick, short enough that changing the ingest interval is
# reflected within a few minutes rather than at tomorrow's open.
_CADENCE_SAMPLE = 12


class GetOiSeries:
    """Assembles the Multi OI & Volume payload for one instrument."""

    def __init__(
        self,
        *,
        provider: ChainProvider,
        snapshots: SnapshotReader,
        now_utc: Any = None,
    ) -> None:
        self._provider = provider
        self._snapshots = snapshots
        self._now = now_utc or (lambda: datetime.now(UTC))

    async def __call__(
        self,
        tenant_id: TenantId,
        symbol: str,
        *,
        interval: str = DEFAULT_INTERVAL,
        window: int = DEFAULT_WINDOW,
        trade_date: datetime | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        # Live reads today; Historical replays the picked archived session.
        as_of = trade_date or now
        bucket = INTERVALS.get(interval, INTERVALS[DEFAULT_INTERVAL])
        span = max(1, min(MAX_WINDOW, window))

        chain = await self._provider.fetch(tenant_id, symbol)
        snaps = await self._snapshots.day_snapshots(tenant_id, symbol, trade_date_utc=as_of)
        # Only the live day is clipped to "now"; a past session is whole.
        if trade_date is None:
            snaps = drop_future(snaps, now)

        if len(snaps) < _MIN_INTRADAY_SNAPSHOTS:
            # A past day with nothing archived is empty — never today's live chain.
            if trade_date is not None:
                return self._empty(symbol, chain, now, interval, span)
            return self._live_proxy(symbol, chain, snaps, now, interval=interval, window=span)

        ordered = sorted(snaps, key=lambda snap: snap.captured_at)
        reconstructed = session_open_frame(ordered)
        if reconstructed is not None:
            ordered = [reconstructed, *ordered]

        frames = _downsample(ordered, bucket)
        return self._payload(
            symbol,
            chain,
            frames,
            quality="intraday",
            open_is_estimated=reconstructed is not None,
            # What the archive could actually deliver, not what was asked for.
            interval=_effective_interval(bucket, snaps),
            window=span,
        )

    def _live_proxy(
        self,
        symbol: str,
        chain: ProviderChain,
        snaps: list[ChainSnapshot],
        now: datetime,
        *,
        interval: str,
        window: int,
    ) -> dict[str, Any]:
        """The tier for a day the ingest worker has not archived.

        Mirrors ``GetOiView``: one stored capture is used if there is one,
        otherwise the live chain, and the 09:15 baseline is reconstructed from
        each leg's ``oi_change``. Without this the page renders an empty panel
        all session on a machine with no ingest worker, while the Open Interest
        page one menu item away shows the very same chain.
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
            return self._empty(symbol, chain, now, interval, window)

        return self._payload(
            symbol,
            chain,
            frames,
            quality="live_proxy",
            open_is_estimated=True,
            interval=interval,
            window=window,
        )

    def _payload(
        self,
        symbol: str,
        chain: ProviderChain,
        frames: list[ChainSnapshot],
        *,
        quality: str,
        open_is_estimated: bool,
        interval: str,
        window: int,
    ) -> dict[str, Any]:
        anchor = frames[-1]
        atm = _anchor_atm(anchor, chain)
        contracts = _contract_series(frames, atm, window)

        return {
            "instrument_id": symbol,
            "symbol": symbol,
            "expiry_date": chain.expiry,
            "atm_strike": atm,
            "lot_size": chain.lot_size,
            "open_ts": _iso(frames[0].captured_at),
            "now_ts": _iso(anchor.captured_at),
            "data_quality": quality,
            "open_is_estimated": open_is_estimated,
            "interval": interval,
            "window": window,
            "t": [_iso(frame.captured_at) for frame in frames],
            "fut": [_future_of(frame) for frame in frames],
            "contracts": contracts,
            "default_ids": _top_ids(contracts, "oi"),
            "default_vol_ids": _top_ids(contracts, "volume"),
        }

    def _empty(
        self,
        symbol: str,
        chain: ProviderChain,
        now: datetime,
        interval: str,
        window: int,
    ) -> dict[str, Any]:
        """A well-formed payload for a day with nothing archived yet.

        Not an error: before the first two captures land there is genuinely no
        series to draw, and the page should say so rather than fail.
        """
        return {
            "instrument_id": symbol,
            "symbol": symbol,
            "expiry_date": chain.expiry,
            "atm_strike": _anchor_atm(None, chain),
            "lot_size": chain.lot_size,
            "open_ts": _iso(session_open_utc(now)),
            "now_ts": _iso(now),
            "data_quality": "empty",
            "open_is_estimated": False,
            "interval": interval,
            "window": window,
            "t": [],
            "fut": [],
            "contracts": [],
            "default_ids": [],
            "default_vol_ids": [],
        }


# -- shaping ----------------------------------------------------------------


def _downsample(ordered: list[ChainSnapshot], bucket_seconds: int) -> list[ChainSnapshot]:
    """One snapshot per time bucket, keeping the **last** in each.

    Last, not mean: open interest and cumulative volume are stocks, not flows.
    Averaging them would invent readings the market never printed, and the final
    bucket would lag the live figure the rest of the page shows.

    The session open is always kept, whatever bucket it lands in — it is the
    baseline every change on the page is measured from.
    """
    if not ordered:
        return []

    kept: dict[int, ChainSnapshot] = {}
    origin = attach_utc(ordered[0].captured_at)
    for snap in ordered:
        elapsed = (attach_utc(snap.captured_at) - origin).total_seconds()
        kept[int(elapsed // bucket_seconds)] = snap

    frames = [kept[key] for key in sorted(kept)]
    if frames[0] is not ordered[0]:
        frames.insert(0, ordered[0])
    return frames


def _contract_series(frames: list[ChainSnapshot], atm: float, window: int) -> list[dict[str, Any]]:
    """One OI and one volume array per contract, aligned to the frame order.

    A leg missing from a frame carries its last known value forward rather than
    reading zero — a contract that stopped being quoted did not have its open
    interest wiped, and a line dropping to the axis would say it did.

    Frames *before* a leg's first appearance are ``None``, not zero. With the
    previous session carried in behind today, a strike listed only after this
    morning's move would otherwise run along the axis all through yesterday and
    then leap to its real value at the open — a spike the market never printed.
    ``None`` starts the line where the contract starts.

    The ladder is the **union** across the session, not the newest frame's. A
    strike quoted all morning and delisted by the afternoon is exactly the case
    the forward-fill exists for, and reading only the last frame would drop it
    from the picker entirely instead.
    """
    union = sorted({row.strike for frame in frames for row in frame.rows})
    step = _infer_step(union)
    reach = step * window
    listed = [strike for strike in union if abs(strike - atm) <= reach + 1e-6]

    series: list[dict[str, Any]] = []
    for strike in listed:
        for side in ("CE", "PE"):
            oi: list[int | None] = []
            volume: list[int | None] = []
            last_oi: int | None = None
            last_volume: int | None = None
            for frame in frames:
                row = _find(frame.rows, strike, side)
                if row is not None:
                    last_oi, last_volume = row.oi, row.volume
                oi.append(last_oi)
                volume.append(last_volume)

            if any(oi) or any(volume):
                series.append(
                    {
                        "id": f"{strike:g}{side}",
                        "strike": strike,
                        "option_type": side,
                        "oi": oi,
                        "volume": volume,
                    }
                )
    return series


def _effective_interval(requested_seconds: int, captured: list[ChainSnapshot]) -> str:
    """The bucket the archive can actually deliver, as a label.

    A request cannot produce resolution finer than the capture cadence: asking
    for 1m against a worker running every 180s yields 3m spacing whatever the
    query said. The field is documented — here and in the client's wire type —
    as *the bucket actually used*, but it echoed the request, so the page
    captioned a 3-minute series "1m buckets".

    Read from the **most recent** captures, not the whole day. The cadence is a
    setting an operator can change mid-session, and after a change the day holds
    a mix; taking the whole day's median then reports the cadence that has been
    retired rather than the one the chart is filling in at now. This is a live
    chart, so what matters is the resolution it is currently arriving at.

    Measured from the stored captures rather than from the returned frames: the
    reconstructed 09:15 open is not a capture, and the gap between it and the
    first real one would otherwise be read as the cadence.

    The median of that window, not the minimum — one late tick should not
    restate the resolution.
    """
    ordered = sorted(attach_utc(snap.captured_at) for snap in captured)
    recent = ordered[-_CADENCE_SAMPLE:]
    gaps = sorted((b - a).total_seconds() for a, b in pairwise(recent))
    if not gaps:
        return _interval_label(requested_seconds)
    cadence = gaps[len(gaps) // 2]
    return _interval_label(max(requested_seconds, round(cadence)))


def _interval_label(seconds: float) -> str:
    """`180` -> `3m`. Matches how the UI's own interval choices read."""
    if seconds < _MINUTE:
        return f"{round(seconds)}s"
    if seconds < _HOUR:
        return f"{round(seconds / _MINUTE)}m"
    return f"{round(seconds / _HOUR)}h"


def _top_ids(contracts: list[dict[str, Any]], key: str) -> list[str]:
    """The busiest contracts by their latest reading, biggest first.

    ``or 0`` rather than a bare index: a leg can now end on ``None`` (never
    quoted in the window), and comparing that against an int during the sort
    raises rather than ranking it last.
    """
    ranked = sorted(
        contracts,
        key=lambda contract: (contract[key][-1] or 0) if contract[key] else 0,
        reverse=True,
    )
    return [contract["id"] for contract in ranked[:_DEFAULT_PICK]]


# -- helpers ----------------------------------------------------------------


def _find(rows: Iterable[ChainRow], strike: float, side: str) -> ChainRow | None:
    for row in rows:
        if row.strike == strike and row.option_type == side:
            return row
    return None


def _infer_step(strikes: list[float]) -> float:
    gaps = [b - a for a, b in pairwise(strikes) if b > a]
    return min(gaps) if gaps else 50.0


def _anchor_atm(frame: ChainSnapshot | None, chain: ProviderChain) -> float:
    if frame is not None and frame.atm_strike is not None:
        return frame.atm_strike
    spot = (frame.spot if frame is not None else None) or chain.spot
    strikes = sorted({row.strike for row in (frame.rows if frame is not None else chain.rows)})
    if spot is None or not strikes:
        return strikes[len(strikes) // 2] if strikes else 0.0
    return atm_strike(spot, strikes)
