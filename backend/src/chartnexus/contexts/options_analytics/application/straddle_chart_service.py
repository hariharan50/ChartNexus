"""The rolling at-the-money straddle through several sessions, for Straddle Chart.

One line a reader watches all day: what it costs to own the at-the-money call
and put together, with the index and the options' own implied forward behind it.

**The strike rolls.** Each capture is priced at *its own* at-the-money strike,
not at one pinned for the window — the subject is the cost of being at the money,
and a strike pinned at 09:15 stops describing that the moment the index moves.
The strike travels with every frame so the chart can say which contract each
point belongs to, and the header names the one in force now. This is the
deliberate opposite of Option Greeks, which pins its strike because its panels
are titled with a contract symbol.

**Three series, two scales.** The straddle is a premium in the hundreds; spot
and the synthetic forward are index levels in the tens of thousands. They cannot
share an axis, so the payload simply ships all three and the client puts the
premium on its own. The synthetic forward is the put-call parity one — the
forward the options themselves imply — falling back to the stored future so the
line is never left with a hole where an ATM leg was unquoted.

**Several sessions, counted as sessions.** The range is a count of *stored*
trading days, so "3 Days" is three sessions of trading rather than three
calendar days that a long weekend would cut to one and a half.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from chartnexus.contexts.options_analytics.application.ports import (
    ChainProvider,
    ChainSnapshot,
    ProviderChain,
    SnapshotReader,
)
from chartnexus.contexts.options_analytics.application.session import (
    drop_future,
    for_expiry,
    future_of,
    iso,
    session_open_utc,
)
from chartnexus.contexts.options_analytics.domain.oi_math import atm_strike
from chartnexus.contexts.options_analytics.domain.straddle_math import atm_straddle, leg_ltp
from chartnexus.contexts.options_analytics.domain.vega_math import synthetic_future
from chartnexus.shared_kernel.types.identifiers import TenantId

#: Sessions a reader may ask for. One is today; the ceiling is well inside the
#: archive's retention window, so a full request can always be answered.
DEFAULT_SESSIONS = 1
MAX_SESSIONS = 10

_PLACES = 2


class GetStraddleChart:
    """Assembles the Straddle Chart payload for one instrument."""

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
        expiry: str | None = None,
        sessions: int = DEFAULT_SESSIONS,
        trade_date: datetime | None = None,
    ) -> dict[str, Any]:
        window = max(1, min(sessions, MAX_SESSIONS))
        now = self._now()
        # Live ends at today; a picked date ends at that archived session.
        end = trade_date or now
        chain = await self._provider.fetch(tenant_id, symbol, expiry=expiry)

        if window == 1:
            snaps = await self._snapshots.day_snapshots(tenant_id, symbol, trade_date_utc=end)
        else:
            snaps = await self._snapshots.recent_session_snapshots(
                tenant_id, symbol, end_utc=end, sessions=window
            )

        # Filtered by what the provider resolved to, not by what was asked for:
        # a broker handed an expiry it does not list answers with its nearest,
        # and keying off the request would draw one contract's archived rows
        # under another's header.
        snaps = for_expiry(snaps, chain.expiry)
        if trade_date is None:
            snaps = drop_future(snaps, now)

        ordered = sorted(snaps, key=lambda snap: snap.captured_at)
        frames = [frame for frame in (_frame(snap) for snap in ordered) if frame is not None]

        if not frames:
            # Nothing archived: one honest point from the live chain, which is
            # all a broker that only answers "now" can give.
            live = _frame(
                ChainSnapshot(captured_at=now, rows=chain.rows, spot=chain.spot),
                fallback_spot=chain.spot,
            )
            if live is None:
                return _empty(symbol, chain, now, window)
            return _payload(symbol, chain, [live], now, window, quality="live")

        return _payload(symbol, chain, frames, now, window, quality="intraday")


# -- assembly ----------------------------------------------------------------


def _payload(
    symbol: str,
    chain: ProviderChain,
    frames: list[dict[str, Any]],
    now: datetime,  # noqa: ARG001 — the timestamps come from the frames themselves
    window: int,
    *,
    quality: str,
) -> dict[str, Any]:
    last = frames[-1]
    return {
        "instrument_id": symbol,
        "symbol": symbol,
        "expiry_date": chain.expiry,
        "lot_size": chain.lot_size,
        # The headline figures: what the chart's right edge is sitting at.
        "straddle_price": last["straddle"],
        "atm_strike": last["strike"],
        "ce_ltp": last["ce"],
        "pe_ltp": last["pe"],
        "spot": last["spot"],
        "synthetic_future": last["synthetic"],
        "requested_sessions": window,
        "covered_sessions": len({frame["d"] for frame in frames}),
        "open_ts": frames[0]["t"],
        "now_ts": last["t"],
        "data_quality": quality,
        #: Always true here, and stated rather than assumed: the series is only
        #: readable as "the cost of being at the money" if the strike rolls.
        "rolling_strike": True,
        "series": {
            "t": [frame["t"] for frame in frames],
            "strike": [frame["strike"] for frame in frames],
            "ce": [frame["ce"] for frame in frames],
            "pe": [frame["pe"] for frame in frames],
            "straddle": [frame["straddle"] for frame in frames],
            "spot": [frame["spot"] for frame in frames],
            "synthetic": [frame["synthetic"] for frame in frames],
        },
    }


def _frame(snap: ChainSnapshot, *, fallback_spot: float | None = None) -> dict[str, Any] | None:
    """One capture's rolling straddle, or ``None`` when it cannot be priced.

    A capture with no at-the-money strike, or with one leg of it unquoted, is
    dropped rather than half-drawn: a straddle missing a leg is not a cheaper
    straddle, it is an unknown one, and plotting the single leg would read as a
    collapse in premium.
    """
    spot = snap.spot if snap.spot is not None else fallback_spot
    strikes = sorted({row.strike for row in snap.rows})
    if not strikes:
        return None

    strike = snap.atm_strike
    if not strike:
        anchor = future_of(snap) or spot
        if anchor is None:
            return None
        strike = atm_strike(anchor, strikes)

    straddle = atm_straddle(snap.rows, strike)
    if straddle is None:
        return None

    # The forward the options imply, falling back to the tradable future so the
    # line is never left with a hole where parity could not be taken.
    synthetic = synthetic_future(snap.rows, strike) or future_of(snap)

    captured = snap.captured_at
    return {
        "t": iso(captured),
        # Which session this capture belongs to, used only to count how many
        # are covered. The UTC date is safe as that key: an IST trading day runs
        # 03:45-10:00 UTC, so it never straddles a UTC midnight.
        "d": iso(captured)[:10],
        "strike": strike,
        "ce": _round(leg_ltp(snap.rows, strike, is_call=True)),
        "pe": _round(leg_ltp(snap.rows, strike, is_call=False)),
        "straddle": round(straddle, _PLACES),
        "spot": _round(spot),
        "synthetic": _round(synthetic),
    }


def _empty(symbol: str, chain: ProviderChain, now: datetime, window: int) -> dict[str, Any]:
    return {
        "instrument_id": symbol,
        "symbol": symbol,
        "expiry_date": chain.expiry,
        "lot_size": chain.lot_size,
        "straddle_price": None,
        "atm_strike": None,
        "ce_ltp": None,
        "pe_ltp": None,
        "spot": _round(chain.spot),
        "synthetic_future": None,
        "requested_sessions": window,
        "covered_sessions": 0,
        "open_ts": iso(session_open_utc(now)),
        "now_ts": iso(now),
        "data_quality": "empty",
        "rolling_strike": True,
        "series": {
            name: [] for name in ("t", "strike", "ce", "pe", "straddle", "spot", "synthetic")
        },
    }


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, _PLACES)
