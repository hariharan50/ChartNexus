"""Per-strike implied volatility and open interest, for the Volatility Skew tool.

One payload drives the whole page: a shared strike axis, and per capture the
call and put IV at every strike alongside the open interest sitting on each
side. The client blends the two IV arrays into the curve it draws (put IV below
spot, call IV above — the out-of-the-money wing is what "skew" means), scrubs
the frames, and windows the strikes.

Unlike ``gex_service`` and ``vega_series_service``, which also need IV, nothing
here is computed: this is a straight projection of ``ChainRow.{iv, oi}`` onto
the axis. That is deliberate. A skew chart's whole job is to show the numbers
the market quoted, and any smoothing or interpolation applied on this side would
be invisible to the reader looking at it.

Three properties shared with its two IV siblings:

* **``iv`` stays ``None`` where it was not quoted.** Coercing to ``0.0`` would
  draw a volatility of zero, which is not a thing; the client leaves a gap.
* **``iv_coverage``** rides on the header, so the page can distinguish "the book
  really is this flat" from "the broker quoted no volatility".
* **No reconstructed 09:15 frame.** The open is rebuilt from the broker's
  day-change field and carries no spot, and without spot there is no telling
  which side of the money a strike was on — so the series starts where the
  recording does.
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
    future_of,
    iso,
    session_open_utc,
)
from marketcompass.contexts.options_analytics.domain.oi_math import ChainRow, infer_step
from marketcompass.shared_kernel.types.identifiers import TenantId

_MIN_INTRADAY_SNAPSHOTS = 2
# Strikes either side of ATM kept on the axis. A superset of the widest window
# the UI offers, so a day with a drifting ladder cannot grow the payload without
# bound. Matches `GetGex` and `GetVega`.
_SERIES_STRIKE_SPAN = 25
# IV is quoted in volatility points; three decimals is finer than any exchange
# publishes and keeps the payload from carrying float noise.
_IV_PLACES = 3
_PLACES = 4


class GetSkew:
    """Assembles the Volatility Skew payload for one instrument."""

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

        # The skew is a shape read across strikes at a moment, and the page
        # scrubs those moments — so a day with nothing archived is empty rather
        # than proxied off the live chain, same as its two IV siblings.
        if len(snaps) < _MIN_INTRADAY_SNAPSHOTS:
            return _empty(symbol, chain, now)

        ordered = sorted(snaps, key=lambda snap: snap.captured_at)
        axis = self._axis(ordered)

        frames: list[dict[str, Any]] = []
        quoted = 0.0
        for snap in ordered:
            built = _frame(snap, axis=axis)
            if built is None:
                continue
            frame, coverage = built
            frames.append(frame)
            quoted += coverage

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
        sideways under the strike-range handles.
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


def _frame(snap: ChainSnapshot, *, axis: list[float]) -> tuple[dict[str, Any], float] | None:
    """One capture's per-strike IV and OI, with the coverage it contributed.

    ``None`` when the capture has no spot to place the money at: which side of
    the money a strike sits on decides which leg's volatility the curve takes,
    so a frame without spot cannot be drawn as a skew at all. Dropping it leaves
    a gap in the timeline, which is what a gap is.

    Unlike ``vega_series_service``, there is deliberately **no fallback to the
    live chain's spot**. This page scrubs a whole session, and today's level
    says nothing about where the money was at 10:30 — borrowing it would place
    the curve's turn at the wrong strike and look entirely plausible doing it.
    """
    captured = attach_utc(snap.captured_at)
    spot = snap.spot if snap.spot is not None else snap.atm_strike
    if spot is None or spot <= 0.0:
        return None

    calls = {row.strike: row for row in snap.rows if row.option_type == "CE"}
    puts = {row.strike: row for row in snap.rows if row.option_type == "PE"}

    ce_iv: list[float | None] = []
    pe_iv: list[float | None] = []
    call_oi: list[int] = []
    put_oi: list[int] = []
    legs = 0
    with_iv = 0

    for strike in axis:
        call = calls.get(strike)
        put = puts.get(strike)

        ce_iv.append(_iv(call))
        pe_iv.append(_iv(put))
        # A leg that was not quoted holds no position either, so zero is the
        # honest OI — unlike IV, where zero would be a claim about volatility.
        call_oi.append(call.oi if call is not None else 0)
        put_oi.append(put.oi if put is not None else 0)

        for leg in (call, put):
            if leg is None:
                continue
            legs += 1
            if leg.iv is not None:
                with_iv += 1

    frame = {
        "t": iso(captured),
        "spot": round(spot, 2),
        "atm": snap.atm_strike,
        # The tradable future, for a page that draws volatility against price.
        # Spot is the fallback only for captures older than that column.
        "future": future_of(snap),
        "ce_iv": ce_iv,
        "pe_iv": pe_iv,
        "call_oi": call_oi,
        "put_oi": put_oi,
    }
    return frame, (with_iv / legs if legs else 0.0)


def _iv(row: ChainRow | None) -> float | None:
    if row is None or row.iv is None:
        return None
    return round(row.iv, _IV_PLACES)


def _empty(symbol: str, chain: ProviderChain, now: datetime) -> dict[str, Any]:
    """A well-formed payload for a day with nothing usable archived yet.

    Not an error: before two captures land there is genuinely no session to
    scrub, and the page should say so rather than fail.
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
