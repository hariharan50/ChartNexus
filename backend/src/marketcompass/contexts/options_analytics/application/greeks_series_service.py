"""Intraday greeks for one strike's call and put, for the Option Greeks tool.

The page asks a narrow question — *how did this contract's IV, delta, theta,
vega and gamma move through the session?* — so the payload is narrow too: one
strike, two legs, five series each, at every capture the archive holds.

**The strike is pinned, not rolling.** The page titles its charts with the
contract's own trading symbol (``NIFTY06OCT2622400CE``), and a line whose
underlying contract changes mid-session under a fixed title is a chart that
lies. The at-the-money strike of the *latest* capture is chosen once and the
whole session is read at that strike; a caller that wants a different one names
it explicitly.

**Greeks are computed here, not read.** The feed quotes implied volatility and
nothing else, so delta/gamma/theta/vega come from ``greeks_math`` using each
capture's own spot, its own time to expiry and its own quoted IV. A leg the
broker priced no volatility on yields ``None`` across the board rather than a
fabricated sensitivity, and ``iv_coverage`` says how much of the series that
affected — without it, a chain nobody quoted volatility on draws as a flat line
and reads as a real, calm market.

Intraday-only, like the other series services: there is no ``ltp`` day-change to
restate a 09:15 greek from, so a day the ingest worker never ran falls back to a
single live-chain frame (``data_quality: "live"``) rather than inventing an open.
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
    future_of,
    iso,
    session_open_utc,
)
from marketcompass.contexts.options_analytics.domain.greeks_math import greeks, unit_vol
from marketcompass.contexts.options_analytics.domain.oi_math import ChainRow, atm_strike
from marketcompass.shared_kernel.types.identifiers import TenantId

_YEAR_SECONDS = 365.0 * 24.0 * 3600.0
_MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")

# Rounding. IV is quoted to two places; delta/theta/vega read at four, which is
# what the reference terminal shows; gamma is 1e-3-small on an index and needs
# six places to be a line rather than a staircase.
_IV_PLACES = 2
_GREEK_PLACES = 4
_GAMMA_PLACES = 6
_PRICE_PLACES = 2

_CALL = "CE"
_PUT = "PE"
_GREEK_NAMES = ("iv", "delta", "gamma", "theta", "vega", "ltp")

# Strikes ladder in fractions across parts of the F&O universe; this is the
# tolerance two of them are matched within.
_STRIKE_EPSILON = 1e-6


class GetGreeksSeries:
    """Assembles the Option Greeks payload for one strike of one instrument."""

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
        strike: float | None = None,
        trade_date: datetime | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        # Live reads today; a picked date replays that archived session.
        as_of = trade_date or now
        chain = await self._provider.fetch(tenant_id, symbol, expiry=expiry)

        snaps = await self._snapshots.day_snapshots(tenant_id, symbol, trade_date_utc=as_of)
        # Filtered by what the provider actually resolved to, not by what was
        # asked for: a broker handed an expiry it does not list answers with its
        # nearest, and keying off the request would draw one contract's archived
        # rows under another's title. Same guard as the sibling series services.
        snaps = for_expiry(snaps, chain.expiry)
        if trade_date is None:
            snaps = drop_future(snaps, now)

        ordered = sorted(snaps, key=lambda snap: snap.captured_at)
        pinned = _pin_strike(requested=strike, snapshots=ordered, chain=chain)
        if pinned is None:
            return _empty(symbol, chain, now)

        expiry_date = _parse_expiry(chain.expiry)
        frames = [
            frame
            for frame in (
                _frame(snap, strike=pinned, expiry=expiry_date, captured=snap.captured_at)
                for snap in ordered
            )
            if frame is not None
        ]
        quality = "intraday"

        if not frames:
            # Nothing archived for this session: one honest point from the live
            # chain, which is all a broker that only answers "now" can give.
            live = _live_frame(chain, strike=pinned, expiry=expiry_date, now=now)
            if live is None:
                return _empty(symbol, chain, now)
            frames = [live]
            quality = "live"

        return _payload(
            symbol=symbol,
            chain=chain,
            strike=pinned,
            frames=frames,
            now=now,
            data_quality=quality,
        )


# -- assembly ----------------------------------------------------------------


def _payload(
    *,
    symbol: str,
    chain: ProviderChain,
    strike: float,
    frames: list[dict[str, Any]],
    now: datetime,  # noqa: ARG001 — kept for symmetry with _empty's signature
    data_quality: str,
) -> dict[str, Any]:
    priced = sum(1 for frame in frames if frame["priced"])
    return {
        "instrument_id": symbol,
        "symbol": symbol,
        "expiry_date": chain.expiry,
        "lot_size": chain.lot_size,
        "strike": strike,
        "atm_strike": strike,
        "spot": round(chain.spot, _PRICE_PLACES) if chain.spot is not None else 0.0,
        "ce_symbol": trading_symbol(symbol, chain.expiry, strike, _CALL),
        "pe_symbol": trading_symbol(symbol, chain.expiry, strike, _PUT),
        "open_ts": frames[0]["t"],
        "now_ts": frames[-1]["t"],
        "data_quality": data_quality,
        # The share of frames where both legs carried a usable volatility. A
        # series of gaps and a genuinely still market look alike without it.
        "iv_coverage": round(priced / len(frames), 4),
        "t": [frame["t"] for frame in frames],
        "underlying": [frame["underlying"] for frame in frames],
        "ce": _leg_series(frames, _CALL),
        "pe": _leg_series(frames, _PUT),
    }


def _leg_series(frames: list[dict[str, Any]], side: str) -> dict[str, list[float | None]]:
    key = "ce" if side == _CALL else "pe"
    legs = [frame[key] for frame in frames]
    return {name: [leg[name] for leg in legs] for name in _GREEK_NAMES}


def _frame(
    snap: ChainSnapshot,
    *,
    strike: float,
    expiry: date | None,
    captured: datetime,
) -> dict[str, Any] | None:
    """One capture's two legs, or ``None`` when this strike is not in it.

    A capture whose ladder had drifted off the pinned strike is dropped rather
    than interpolated: a gap in the line is a fact, a bridged point is a guess.
    """
    call = _row_at(snap.rows, strike, _CALL)
    put = _row_at(snap.rows, strike, _PUT)
    if call is None and put is None:
        return None

    underlying = future_of(snap) or snap.spot
    if underlying is None or underlying <= 0.0:
        return None

    years = _years_to_expiry(captured, expiry)
    return {
        "t": iso(captured),
        "underlying": round(underlying, _PRICE_PLACES),
        "ce": _leg(call, strike=strike, spot=underlying, years=years, side=_CALL),
        "pe": _leg(put, strike=strike, spot=underlying, years=years, side=_PUT),
        "priced": _is_priced(call, years) and _is_priced(put, years),
    }


def _is_priced(row: ChainRow | None, years: float) -> bool:
    return row is not None and bool(row.iv) and years > 0.0


def _live_frame(
    chain: ProviderChain,
    *,
    strike: float,
    expiry: date | None,
    now: datetime,
) -> dict[str, Any] | None:
    if chain.spot is None or chain.spot <= 0.0:
        return None
    snapshot = ChainSnapshot(captured_at=now, rows=chain.rows, spot=chain.spot)
    return _frame(snapshot, strike=strike, expiry=expiry, captured=now)


def _leg(
    row: ChainRow | None,
    *,
    strike: float,
    spot: float,
    years: float,
    side: str,
) -> dict[str, float | None]:
    """One leg's greeks, with ``None`` wherever there is nothing to state.

    ``None`` rather than ``0.0`` for an unpriced leg: a chart draws a gap for the
    first and a confident flat line through zero for the second, and only one of
    those is true.
    """
    if row is None or not _is_priced(row, years):
        return dict.fromkeys(_GREEK_NAMES, None)

    computed = greeks(option_type=side, spot=spot, strike=strike, years=years, vol=unit_vol(row.iv))
    return {
        "iv": round(row.iv, _IV_PLACES) if row.iv is not None else None,
        "delta": round(computed.delta, _GREEK_PLACES),
        "gamma": round(computed.gamma, _GAMMA_PLACES),
        "theta": round(computed.theta, _GREEK_PLACES),
        "vega": round(computed.vega, _GREEK_PLACES),
        "ltp": round(row.ltp, _PRICE_PLACES) if row.ltp else None,
    }


def _empty(symbol: str, chain: ProviderChain, now: datetime) -> dict[str, Any]:
    return {
        "instrument_id": symbol,
        "symbol": symbol,
        "expiry_date": chain.expiry,
        "lot_size": chain.lot_size,
        "strike": None,
        "atm_strike": None,
        "spot": round(chain.spot, _PRICE_PLACES) if chain.spot is not None else 0.0,
        "ce_symbol": None,
        "pe_symbol": None,
        "open_ts": iso(session_open_utc(now)),
        "now_ts": iso(now),
        "data_quality": "empty",
        "iv_coverage": 0.0,
        "t": [],
        "underlying": [],
        "ce": {name: [] for name in _GREEK_NAMES},
        "pe": {name: [] for name in _GREEK_NAMES},
    }


# -- helpers -----------------------------------------------------------------


def _pin_strike(
    *,
    requested: float | None,
    snapshots: list[ChainSnapshot],
    chain: ProviderChain,
) -> float | None:
    """The strike the whole session is read at.

    The caller's, when they named one. Otherwise the at-the-money strike of the
    most recent capture — the latest, not the first, because the page's title
    names the contract a reader is watching *now*.
    """
    if requested is not None and requested > 0.0:
        return float(requested)

    for snap in reversed(snapshots):
        if snap.atm_strike:
            return float(snap.atm_strike)
        strikes = sorted({row.strike for row in snap.rows})
        spot = future_of(snap) or snap.spot
        if strikes and spot:
            return atm_strike(spot, strikes)

    strikes = sorted({row.strike for row in chain.rows})
    if strikes and chain.spot:
        return atm_strike(chain.spot, strikes)
    return None


def _row_at(rows: tuple[ChainRow, ...], strike: float, side: str) -> ChainRow | None:
    for row in rows:
        if row.option_type.upper() == side and _same_strike(row.strike, strike):
            return row
    return None


def _same_strike(left: float, right: float) -> bool:
    """Strikes ladder in fractions across parts of the F&O universe, so compare
    with a tolerance rather than on equality of two floats that travelled through
    a numeric column and JSON."""
    return abs(left - right) < _STRIKE_EPSILON


def trading_symbol(symbol: str, expiry: str | None, strike: float, side: str) -> str | None:
    """The contract's display symbol, e.g. ``NIFTY06OCT2622400CE``.

    A *label*, not a broker symbol: it is what the chart titles itself with, and
    the broker-specific spelling lives in the FYERS mapper, which this context
    may not reach. ``None`` when the expiry is unknown — half a symbol under a
    chart is worse than none.
    """
    parsed = _parse_expiry(expiry)
    if parsed is None:
        return None
    return (
        f"{symbol.upper()}{parsed.day:02d}{_MONTHS[parsed.month - 1]}"
        f"{parsed.year % 100:02d}{_strike_label(strike)}{side}"
    )


def _strike_label(strike: float) -> str:
    """``22400`` for a whole strike, ``2512.5`` for one laddered in halves."""
    return str(int(strike)) if float(strike).is_integer() else str(strike)


def _parse_expiry(value: str | None) -> date | None:
    if not value:
        return None
    try:
        # Accepts both `2026-10-06` and a full ISO timestamp.
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _years_to_expiry(moment: datetime, expiry: date | None) -> float:
    """Year fraction to the 15:30 IST bell on expiry day.

    ``0.0`` when the expiry is unknown or already past, which drives every greek
    to "not priceable" rather than to a negative square root.
    """
    if expiry is None:
        return 0.0
    close = datetime.combine(expiry, SESSION_CLOSE, tzinfo=IST)
    remaining: timedelta = close - attach_utc(moment)
    return max(0.0, remaining.total_seconds() / _YEAR_SECONDS)
