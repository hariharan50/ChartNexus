"""Per-strike straddle premiums through the session, for the ATM Straddle Chart.

One payload drives the whole page: a shared strike axis, and per capture each
strike's call and put last price plus the rolling at-the-money straddle and the
tradable future. The client picks a strike (or "Auto Rolling", the ATM straddle)
and re-buckets the timeframe without a refetch — the same client-side windowing
Gamma Exposure and Vega Analysis use.

Intraday-only, like those two siblings: a straddle premium at the 09:15 open
cannot be reconstructed (there is no ``ltp`` day-change to restate it from), so a
thin day is simply empty rather than fabricating an opening bar.
"""

from __future__ import annotations

from datetime import UTC, datetime
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
    for_expiry,
    future_of,
    iso,
    session_open_utc,
)
from marketcompass.contexts.options_analytics.domain.oi_math import ChainRow, infer_step
from marketcompass.contexts.options_analytics.domain.straddle_math import atm_straddle
from marketcompass.shared_kernel.types.identifiers import TenantId

_MIN_INTRADAY_SNAPSHOTS = 2
# Strikes either side of ATM kept on the axis. A superset of the widest window
# the UI offers, so a day with a drifting ladder cannot grow the payload without
# bound. Matches `GetGex` / `GetVega`.
_SERIES_STRIKE_SPAN = 25
_PLACES = 2


class GetStraddleSeries:
    """Assembles the ATM Straddle Chart payload for one instrument."""

    def __init__(
        self,
        *,
        provider: ChainProvider,
        snapshots: SnapshotReader,
        now_utc: Any = None,
        strike_span: int = _SERIES_STRIKE_SPAN,
    ) -> None:
        self._provider = provider
        self._snapshots = snapshots
        self._now = now_utc or (lambda: datetime.now(UTC))
        self._strike_span = strike_span

    async def __call__(
        self,
        tenant_id: TenantId,
        symbol: str,
        *,
        expiry: str | None = None,
        trade_date: datetime | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        # Live reads today; Historical replays the picked archived session.
        as_of = trade_date or now
        chain = await self._provider.fetch(tenant_id, symbol, expiry=expiry)
        snaps = await self._snapshots.day_snapshots(tenant_id, symbol, trade_date_utc=as_of)
        # Filtered by what the chain actually resolved to, not by what was
        # asked for. A provider handed an expiry it does not list answers
        # with its nearest instead, and keying off the request would then
        # draw one contract's archived rows under another's header. Anything
        # the archive does not hold drops to live-proxy, which is honest.
        snaps = for_expiry(snaps, chain.expiry)
        # Only the live day is clipped to "now"; a past session is whole.
        if trade_date is None:
            snaps = drop_future(snaps, now)

        # A straddle needs real captures either way; there is no live-chain proxy.
        if len(snaps) < _MIN_INTRADAY_SNAPSHOTS:
            return _empty(symbol, chain, now)

        ordered = sorted(snaps, key=lambda snap: snap.captured_at)
        axis = self._axis(ordered)

        frames: list[dict[str, Any]] = []
        for snap in ordered:
            built = _frame(snap, axis=axis, chain=chain)
            if built is None:
                continue
            frames.append(built)

        if not frames:
            return _empty(symbol, chain, now)

        return {
            "instrument_id": symbol,
            "symbol": symbol,
            "expiry_date": chain.expiry,
            "lot_size": chain.lot_size,
            "spot": frames[-1]["spot"],
            "atm_strike": frames[-1]["atm"],
            "open_ts": frames[0]["t"],
            "now_ts": frames[-1]["t"],
            "data_quality": "intraday",
            # Always false here — see the module docstring. Kept on the wire so
            # every Options Lab payload has the same header shape.
            "open_is_estimated": False,
            "strikes": list(axis),
            "t": [frame["t"] for frame in frames],
            "frames": frames,
        }

    def _axis(self, ordered: list[ChainSnapshot]) -> list[float]:
        """One strike axis for every frame, bounded around the newest ATM.

        Shared across frames because the client indexes each strike's series by
        position: an axis that grew a strike mid-session would slide every later
        frame sideways under the selection.
        """
        union = sorted({row.strike for snap in ordered for row in snap.rows})
        if not union:
            return []

        newest = ordered[-1]
        current = {row.strike for row in newest.rows}
        anchor = newest.atm_strike
        if anchor is None:
            anchor = newest.spot if newest.spot is not None else union[len(union) // 2]

        reach = infer_step(union) * self._strike_span
        return [strike for strike in union if strike in current or abs(strike - anchor) <= reach]


def _frame(
    snap: ChainSnapshot,
    *,
    axis: list[float],
    chain: ProviderChain,
) -> dict[str, Any] | None:
    """One capture's per-strike LTPs, the rolling ATM straddle, and the future.

    Dropped (``None``) only when no spot can be placed for the frame — the same
    guard the sibling services use so a capture with nothing to anchor leaves a
    gap in the timeline rather than a row of misleading zeros.
    """
    captured = attach_utc(snap.captured_at)
    spot = snap.spot if snap.spot is not None else snap.atm_strike
    if spot is None:
        spot = chain.spot
    if spot is None or spot <= 0.0:
        return None

    call_by: dict[float, ChainRow] = {}
    put_by: dict[float, ChainRow] = {}
    for row in snap.rows:
        (call_by if row.is_call else put_by)[row.strike] = row

    ce_ltp = [_ltp(call_by.get(strike)) for strike in axis]
    pe_ltp = [_ltp(put_by.get(strike)) for strike in axis]

    straddle = atm_straddle(snap.rows, snap.atm_strike)
    future = future_of(snap)

    return {
        "t": iso(captured),
        "spot": round(spot, 2),
        "atm": snap.atm_strike,
        "future": round(future, 2) if future is not None else None,
        "atm_straddle": round(straddle, _PLACES) if straddle is not None else None,
        "ce_ltp": ce_ltp,
        "pe_ltp": pe_ltp,
    }


def _empty(symbol: str, chain: ProviderChain, now: datetime) -> dict[str, Any]:
    """A well-formed payload for a day with nothing usable archived yet.

    Not an error: before two captures land there is genuinely no session to
    replay, and the page should say so rather than fail.
    """
    return {
        "instrument_id": symbol,
        "symbol": symbol,
        "expiry_date": chain.expiry,
        "lot_size": chain.lot_size,
        "spot": round(chain.spot, 2) if chain.spot is not None else 0.0,
        "atm_strike": None,
        "open_ts": iso(session_open_utc(now)),
        "now_ts": iso(now),
        "data_quality": "empty",
        "open_is_estimated": False,
        "strikes": [],
        "t": [],
        "frames": [],
    }


# -- helpers ----------------------------------------------------------------


def _ltp(row: ChainRow | None) -> float | None:
    """A leg's last price for the strike table, or ``None`` where it is absent.

    Unlike the rolling-ATM guard this keeps a genuine ``0.0`` print: the sidebar
    table shows what each leg actually last traded at, and only a leg missing
    from the frame is a real gap.
    """
    return None if row is None else round(row.ltp, _PLACES)
