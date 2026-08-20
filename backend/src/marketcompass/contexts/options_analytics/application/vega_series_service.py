"""Per-strike vega exposure through the session, for the Vega Analysis tool.

One payload drives the whole page: a shared strike axis, and per capture the
two-sided aggregate vega at every strike plus the synthetic future read off the
money. The client sums the window it draws and plots each side's change since
the session open — that delta is the "Call Vega" / "Put Vega" the page shows,
and the sign it carries is what makes the chart cross zero.

Like Gamma Exposure, this is one of the two Options Lab services that need
implied volatility. It is available — ``ChainRow.iv`` is populated per leg — but
nullable end to end, so the payload carries ``iv_coverage`` and the page can say
when a flat profile means "balanced book" and when it means "the broker quoted
no volatility".

Two departures from the OI-family services, both shared with ``gex_service``:

* **No reconstructed 09:15 frame.** The open is rebuilt from the broker's
  day-change field, but it carries no spot — and vega, like gamma, is a function
  of where spot is. A synthetic opening bar would be an invented number, so the
  series starts where the recording does.
* **Values are emitted in crore.** Fifty strikes, two sides, a hundred-odd
  captures — raw rupee vega runs to many digits a number. Four decimals of crore
  is the same information in a fraction of the bytes, and matches the scale the
  page reads the change since open on.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from typing import Any

from marketcompass.contexts.options_analytics.application.ports import (
    ChainProvider,
    ChainSnapshot,
    ProviderChain,
    SnapshotReader,
)
from marketcompass.contexts.options_analytics.application.session import (
    IST,
    SESSION_CLOSE,
    attach_utc,
    drop_future,
    future_of,
    iso,
    session_open_utc,
)
from marketcompass.contexts.options_analytics.domain.vega_math import (
    VegaProfile,
    synthetic_future,
    vega_profile,
)
from marketcompass.shared_kernel.types.identifiers import TenantId

_MIN_INTRADAY_SNAPSHOTS = 2
# Strikes either side of ATM kept on the axis. A superset of the widest window
# the UI offers, so a day with a drifting ladder cannot grow the payload without
# bound. Matches `GetGex`'s default.
_SERIES_STRIKE_SPAN = 25
_DEFAULT_STEP = 50.0
_CRORE = 1e7
# Enough precision that a small position is still visible; anything finer is
# below the width of a rendered point.
_PLACES = 4
_YEAR_SECONDS = 365.0 * 24.0 * 3600.0


class GetVega:
    """Assembles the Vega Analysis payload for one instrument."""

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
        self, tenant_id: TenantId, symbol: str, *, trade_date: datetime | None = None
    ) -> dict[str, Any]:
        now = self._now()
        # Live reads today; Historical replays the picked archived session.
        as_of = trade_date or now
        chain = await self._provider.fetch(tenant_id, symbol)
        snaps = await self._snapshots.day_snapshots(tenant_id, symbol, trade_date_utc=as_of)
        # Only the live day is clipped to "now"; a past session is whole.
        if trade_date is None:
            snaps = drop_future(snaps, now)

        # Vega needs real captures either way, so a thin day — live or historical
        # — is simply empty; there is no live-chain proxy to fall back to.
        if len(snaps) < _MIN_INTRADAY_SNAPSHOTS:
            return _empty(symbol, chain, now)

        ordered = sorted(snaps, key=lambda snap: snap.captured_at)
        axis = self._axis(ordered)
        expiry = _parse_expiry(chain.expiry)

        frames: list[dict[str, Any]] = []
        quoted = 0.0
        for snap in ordered:
            built = _frame(snap, axis=axis, expiry=expiry, chain=chain)
            if built is None:
                continue
            frames.append(built[0])
            quoted += built[1].iv_coverage

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
            "iv_coverage": round(quoted / len(frames), _PLACES),
            "strikes": list(axis),
            "t": [frame["t"] for frame in frames],
            "frames": frames,
        }

    def _axis(self, ordered: list[ChainSnapshot]) -> list[float]:
        """One strike axis for every frame, bounded around the newest ATM.

        Shared across frames because the client indexes bars by position: an
        axis that grew a strike mid-session would slide every later frame
        sideways under the window handle.
        """
        union = sorted({row.strike for snap in ordered for row in snap.rows})
        if not union:
            return []

        newest = ordered[-1]
        current = {row.strike for row in newest.rows}
        anchor = newest.atm_strike
        if anchor is None:
            anchor = newest.spot if newest.spot is not None else union[len(union) // 2]

        reach = _infer_step(union) * self._strike_span
        return [strike for strike in union if strike in current or abs(strike - anchor) <= reach]


def _frame(
    snap: ChainSnapshot,
    *,
    axis: list[float],
    expiry: date | None,
    chain: ProviderChain,
) -> tuple[dict[str, Any], VegaProfile] | None:
    """One capture's profile, or ``None`` when vega cannot be placed.

    Vega is a function of where spot is. A capture with no recorded spot — and
    no ATM or live level to stand in for it — has no profile, and emitting a
    frame of zeros would draw a flat market that never happened. Dropping it
    leaves a gap in the timeline, which is what a gap is.
    """
    captured = attach_utc(snap.captured_at)
    spot = snap.spot if snap.spot is not None else snap.atm_strike
    if spot is None:
        spot = chain.spot
    if spot is None or spot <= 0.0:
        return None

    profile = vega_profile(
        snap.rows,
        spot=spot,
        years=_years_to_expiry(captured, expiry),
        axis=axis,
    )
    entries = profile.strikes

    # Synthetic future by parity at the money, falling back to the tradable
    # future so the price line is never left with a hole where an ATM leg was
    # simply not quoted.
    synth = synthetic_future(snap.rows, snap.atm_strike)
    if synth is None:
        synth = future_of(snap)

    return (
        {
            "t": iso(captured),
            "spot": round(spot, 2),
            "atm": snap.atm_strike,
            "synth_future": round(synth, 2) if synth is not None else None,
            "call_vega": [_crore(entry.call_vega) for entry in entries],
            "put_vega": [_crore(entry.put_vega) for entry in entries],
        },
        profile,
    )


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
        "iv_coverage": 0.0,
        "strikes": [],
        "t": [],
        "frames": [],
    }


# -- helpers ----------------------------------------------------------------


def _crore(value: float) -> float:
    return round(value / _CRORE, _PLACES)


def _parse_expiry(value: str | None) -> date | None:
    if not value:
        return None
    try:
        # Accepts both `2026-08-11` and a full ISO timestamp.
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _years_to_expiry(moment: datetime, expiry: date | None) -> float:
    """Year fraction to the 15:30 IST bell on expiry day.

    ``0.0`` when the expiry is unknown or already past, which drives vega to
    zero rather than to a negative square root. The page names this case in its
    caption instead of drawing a wall of empty points unexplained.
    """
    if expiry is None:
        return 0.0
    close = datetime.combine(expiry, SESSION_CLOSE, tzinfo=IST)
    remaining: timedelta = close - attach_utc(moment)
    return max(0.0, remaining.total_seconds() / _YEAR_SECONDS)


def _infer_step(strikes: list[float]) -> float:
    diffs = [b - a for a, b in pairwise(strikes) if b - a > 0]
    return min(diffs) if diffs else _DEFAULT_STEP
