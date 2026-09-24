"""Per-strike gamma exposure through the session, for the Gamma Exposure tool.

One payload drives the whole page: a shared strike axis, and per capture the
two-sided exposure at every strike plus the four levels read off it.

This is the only Options Lab service that needs implied volatility. It is
available — ``ChainRow.iv`` is populated by both broker adapters and persisted
per leg — but it is nullable end to end, so the payload carries ``iv_coverage``
and the page can say when a flat profile means "balanced book" and when it means
"the broker quoted no volatility".

Two departures from the sibling services, both deliberate:

* **No reconstructed 09:15 frame.** ``session_open_frame`` rebuilds the open
  from the broker's day-change field, but it carries no spot — nobody recorded
  where the index was at the bell. Open interest can be restated without one;
  gamma cannot. A synthetic opening bar would be an invented number, so the
  series starts where the recording does.
* **Values are emitted in crore.** Fifty strikes, two sides, a hundred-odd
  captures — that product is this payload's entire size story, and raw rupee
  gamma runs to twelve digits a number. Four decimal places of crore is the
  same information in a fifth of the bytes.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
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
    for_expiry,
    iso,
    session_open_utc,
)
from marketcompass.contexts.options_analytics.domain.gex_math import (
    GexProfile,
    call_wall,
    net_cross,
    put_wall,
    strike_profile,
    zero_gamma,
)
from marketcompass.contexts.options_analytics.domain.oi_math import infer_step
from marketcompass.shared_kernel.types.identifiers import TenantId

_MIN_INTRADAY_SNAPSHOTS = 2
# Strikes either side of ATM kept on the axis. The widest filter the UI offers
# is ±20, so this is a superset — it exists so a day with a drifting ladder
# cannot grow the payload without bound. Matches `GetOiView`'s default.
_SERIES_STRIKE_SPAN = 25
_CRORE = 1e7
# Enough precision that a 1-lakh exposure is still visible; anything finer is
# below the width of a rendered bar.
_PLACES = 4
_YEAR_SECONDS = 365.0 * 24.0 * 3600.0


class GetGex:
    """Assembles the Gamma Exposure payload for one instrument."""

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

        # GEX needs real captures either way, so a thin day — live or historical —
        # is simply empty; there is no live-chain proxy to fall back to.
        if len(snaps) < _MIN_INTRADAY_SNAPSHOTS:
            return _empty(symbol, chain, now)

        ordered = sorted(snaps, key=lambda snap: snap.captured_at)
        axis = self._axis(ordered)
        # Named apart from the `expiry` parameter, which is the ISO string the
        # caller asked for; this is the resolved chain's expiry as a date, for
        # the time-to-expiry maths.
        expiry_date = _parse_expiry(chain.expiry)

        frames: list[dict[str, Any]] = []
        quoted = 0.0
        for snap in ordered:
            frame = _frame(snap, axis=axis, expiry=expiry_date, chain=chain)
            if frame is None:
                continue
            frames.append(frame[0])
            quoted += frame[1].iv_coverage

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
        sideways under the scrub handle.
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
    expiry: date | None,
    chain: ProviderChain,
) -> tuple[dict[str, Any], GexProfile] | None:
    """One capture's profile, or ``None`` when gamma cannot be placed.

    Gamma is a function of where spot is. A capture with no recorded spot —
    and no ATM or live level to stand in for it — has no profile, and emitting
    a frame of zeros would draw a flat market that never happened. Dropping it
    leaves a gap in the timeline, which is what a gap is.
    """
    captured = attach_utc(snap.captured_at)
    spot = snap.spot if snap.spot is not None else snap.atm_strike
    if spot is None:
        spot = chain.spot
    if spot is None or spot <= 0.0:
        return None

    years = _years_to_expiry(captured, expiry)
    profile = strike_profile(snap.rows, spot=spot, years=years, axis=axis)
    entries = profile.strikes

    return (
        {
            "t": iso(captured),
            "spot": round(spot, 2),
            "atm": snap.atm_strike,
            "call_gex": [_crore(entry.call_gex) for entry in entries],
            "put_gex": [_crore(entry.put_gex) for entry in entries],
            "net_total": _crore(profile.net_total),
            "abs_total": _crore(profile.abs_total),
            "call_wall": call_wall(entries),
            "put_wall": put_wall(entries),
            # The flip is the re-priced zero-gamma spot, so it needs the raw
            # chain and the year fraction, not the profile priced at today's spot.
            "gamma_flip": _round_level(zero_gamma(snap.rows, spot=spot, years=years, axis=axis)),
            "net_cross": _round_level(net_cross(entries, spot)),
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


def _round_level(level: float | None) -> float | None:
    """Interpolated levels are prices; two decimals is finer than any tick."""
    return None if level is None else round(level, 2)


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

    ``0.0`` when the expiry is unknown or already past, which drives gamma to
    zero rather than to a negative square root. The page names this case in its
    caption instead of drawing a wall of empty bars unexplained.
    """
    if expiry is None:
        return 0.0
    close = datetime.combine(expiry, SESSION_CLOSE, tzinfo=IST)
    remaining: timedelta = close - attach_utc(moment)
    return max(0.0, remaining.total_seconds() / _YEAR_SECONDS)
