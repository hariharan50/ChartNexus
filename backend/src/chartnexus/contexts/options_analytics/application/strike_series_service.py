"""One strike's price, OI and OI-change through the session, for Price vs OI.

The strike-centric counterpart to :mod:`straddle_series_service`. Where that
serves every strike's premium so the client can pick one, this serves a single
``?strike=`` in full — its call and put last price, open interest, day OI change,
the straddle (call + put price) and the per-strike put/call ratio — on one shared
time axis, plus the strike ladder for the sidebar to choose from.

Intraday-only, like the straddle series: a premium or an OI figure at the 09:15
open cannot be reconstructed from a day-change, so a thin day is empty rather than
carrying a fabricated opening bar.
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
    attach_utc,
    drop_future,
    for_expiry,
    future_of,
    iso,
    session_open_utc,
)
from chartnexus.contexts.options_analytics.domain.oi_math import ChainRow, infer_step
from chartnexus.shared_kernel.types.identifiers import TenantId

_MIN_INTRADAY_SNAPSHOTS = 2
# Strikes either side of ATM kept on the ladder the sidebar offers. Matches the
# straddle/GEX/vega span so the strike list reads the same across the tools.
_LADDER_STRIKE_SPAN = 25
_PLACES = 2


class GetStrikeSeries:
    """Assembles the Price vs OI payload for one instrument and strike."""

    def __init__(
        self,
        *,
        provider: ChainProvider,
        snapshots: SnapshotReader,
        now_utc: Any = None,
        strike_span: int = _LADDER_STRIKE_SPAN,
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
        strike: float | None = None,
        expiry: str | None = None,
        trade_date: datetime | None = None,
    ) -> dict[str, Any]:
        now = self._now()
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

        if len(snaps) < _MIN_INTRADAY_SNAPSHOTS:
            return _empty(symbol, chain, now, strike)

        ordered = sorted(snaps, key=lambda snap: snap.captured_at)
        ladder = self._ladder(ordered)
        # Omitting the strike asks for the money — the sidebar's default landing.
        target = strike if strike is not None else _default_strike(ordered)

        frames: list[dict[str, Any]] = []
        for snap in ordered:
            built = _frame(snap, strike=target, chain=chain)
            if built is not None:
                frames.append(built)

        if not frames:
            return _empty(symbol, chain, now, target)

        return {
            "instrument_id": symbol,
            "symbol": symbol,
            "expiry_date": chain.expiry,
            "lot_size": chain.lot_size,
            "spot": frames[-1]["spot"],
            "atm_strike": frames[-1]["atm"],
            "strike": target,
            "strikes": ladder,
            "open_ts": frames[0]["t"],
            "now_ts": frames[-1]["t"],
            "data_quality": "intraday",
            # Always false — a premium/OI open cannot be restated. Kept on the wire
            # so every Options Lab payload has the same header shape.
            "open_is_estimated": False,
            "t": [f["t"] for f in frames],
            "ce_price": [f["ce_price"] for f in frames],
            "pe_price": [f["pe_price"] for f in frames],
            "ce_oi": [f["ce_oi"] for f in frames],
            "pe_oi": [f["pe_oi"] for f in frames],
            "ce_oi_change": [f["ce_oi_change"] for f in frames],
            "pe_oi_change": [f["pe_oi_change"] for f in frames],
            "straddle": [f["straddle"] for f in frames],
            "pcr": [f["pcr"] for f in frames],
        }

    def _ladder(self, ordered: list[ChainSnapshot]) -> list[float]:
        """The strikes the sidebar lists, bounded around the newest ATM.

        The same window the straddle axis uses, so the strike list is a familiar
        band around the money rather than the whole chain the archive may hold.
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
    strike: float,
    chain: ProviderChain,
) -> dict[str, Any] | None:
    """One capture's readings for the selected strike, or ``None`` with no spot.

    Dropped only when no spot can be placed for the frame — the same guard the
    sibling services use, so a capture with nothing to anchor leaves a gap in the
    timeline rather than a row of misleading zeros.
    """
    captured = attach_utc(snap.captured_at)
    spot = snap.spot if snap.spot is not None else snap.atm_strike
    if spot is None:
        spot = chain.spot
    if spot is None or spot <= 0.0:
        return None

    call: ChainRow | None = None
    put: ChainRow | None = None
    for row in snap.rows:
        if row.strike != strike:
            continue
        if row.is_call:
            call = row
        else:
            put = row

    ce_price = _price(call)
    pe_price = _price(put)
    ce_oi = call.oi if call is not None else None
    pe_oi = put.oi if put is not None else None
    future = future_of(snap)

    return {
        "t": iso(captured),
        "spot": round(spot, 2),
        "atm": snap.atm_strike,
        "future": round(future, 2) if future is not None else None,
        "ce_price": ce_price,
        "pe_price": pe_price,
        "ce_oi": ce_oi,
        "pe_oi": pe_oi,
        "ce_oi_change": call.oi_change if call is not None else None,
        "pe_oi_change": put.oi_change if put is not None else None,
        # Both legs needed; `None` where either was unquoted, never a half straddle.
        "straddle": (
            round(ce_price + pe_price, _PLACES)
            if ce_price is not None and pe_price is not None
            else None
        ),
        # `None`, never 0, where there was no call interest to divide by — a ratio
        # with an empty denominator is undefined, and 0 would draw a false floor.
        "pcr": (
            round(pe_oi / ce_oi, 4)
            if ce_oi is not None and ce_oi > 0 and pe_oi is not None
            else None
        ),
    }


def _empty(
    symbol: str, chain: ProviderChain, now: datetime, strike: float | None
) -> dict[str, Any]:
    """A well-formed payload for a day with nothing usable archived yet."""
    return {
        "instrument_id": symbol,
        "symbol": symbol,
        "expiry_date": chain.expiry,
        "lot_size": chain.lot_size,
        "spot": round(chain.spot, 2) if chain.spot is not None else 0.0,
        "atm_strike": None,
        "strike": strike if strike is not None else 0.0,
        "strikes": [],
        "open_ts": iso(session_open_utc(now)),
        "now_ts": iso(now),
        "data_quality": "empty",
        "open_is_estimated": False,
        "t": [],
        "ce_price": [],
        "pe_price": [],
        "ce_oi": [],
        "pe_oi": [],
        "ce_oi_change": [],
        "pe_oi_change": [],
        "straddle": [],
        "pcr": [],
    }


# -- helpers ----------------------------------------------------------------


def _default_strike(ordered: list[ChainSnapshot]) -> float:
    """The strike to plot when none was asked for: the newest at-the-money.

    Falls back to the strike nearest spot, then the ladder's middle, so a capture
    with no ATM recorded still lands the sidebar somewhere sensible.
    """
    newest = ordered[-1]
    if newest.atm_strike is not None:
        return newest.atm_strike
    strikes = sorted({row.strike for row in newest.rows})
    if not strikes:
        return 0.0
    spot = newest.spot
    if spot is None:
        return strikes[len(strikes) // 2]
    return min(strikes, key=lambda strike: abs(strike - spot))


def _price(row: ChainRow | None) -> float | None:
    """A leg's last price, or ``None`` where the leg was absent from the frame.

    Keeps a genuine ``0.0`` print — the price chart shows what actually traded,
    and only a leg missing from the capture is a real gap.
    """
    return None if row is None else round(row.ltp, _PLACES)
