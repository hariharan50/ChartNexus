"""Pure replay of a short at-the-money straddle with strike-shift adjustments.

The Straddle PnL Simulator asks one question: *had you sold the at-the-money
call and put at the open and re-struck them whenever the market walked away,
what would the running P&L look like?* This module answers it and nothing else —
no I/O, no clock, no framework, so the arithmetic can be pinned to a table of
expected numbers and stay pinned.

**The position is short.** Selling the straddle collects ``entry_straddle``; the
mark-to-market is therefore ``entry - current``, positive when premium decays and
negative when the market moves. Every P&L here is gross: no brokerage, slippage,
taxes or margin.

**The trigger is strike-to-strike, not spot-to-strike.** An adjustment fires when
the *at-the-money strike* has moved ``adjustment_points`` away from the one held,
which is a very different thing from spot having moved that far. With a 50-point
ladder and ``adjustment_points=50`` every change of ATM adjusts; with 100 the ATM
must travel two strikes. Comparing spot to the held strike instead would fire
roughly twice as often and at different moments.

**The at-the-money comes from spot.** Never from the synthetic future, which sits
a few points away on carry and would silently shift every adjustment boundary.

**A day is a round trip.** Each session opens a fresh straddle at its first
capture and squares off at its last; realised P&L and the adjustment count carry
across days, so the chart is one continuous equity curve rather than a saw that
resets each morning. The adjustment check runs on the closing capture too, so an
ADJUSTMENT and an EXIT legitimately share a timestamp — the EXIT then books
nothing, because the position it closes was opened moments earlier at that same
price.

Prices are the capture's last traded price, not a candle close: the archive this
feeds on stores point samples at the ingest cadence. For a replay that only ever
needs price-at-time, the distinction does not change the arithmetic.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from itertools import groupby

from chartnexus.contexts.options_analytics.domain.oi_math import (
    DEFAULT_STRIKE_STEP,
    ChainRow,
    atm_strike,
)
from chartnexus.contexts.options_analytics.domain.straddle_math import leg_ltp
from chartnexus.shared_kernel.domain.errors import ValidationError

#: Money is rounded here and only here — on the way out. Everything the next
#: row depends on keeps full precision, or a day of 2-dp rounding errors
#: accumulates into the running total.
_PLACES = 2

ENTRY = "ENTRY"
ADJUSTMENT = "ADJUSTMENT"
EXIT = "EXIT"


@dataclass(frozen=True, slots=True)
class PnlFrame:
    """One capture the replay walks over.

    ``session`` is the IST trading date (``YYYY-MM-DD``) and is what groups the
    frames into days. It is supplied rather than derived so this module needs no
    timezone of its own: the caller already knows which session it read.
    """

    session: str
    timestamp: str
    spot: float
    rows: tuple[ChainRow, ...]


@dataclass(frozen=True, slots=True)
class PnlPoint:
    """One row of the plotted series."""

    t: str
    spot: float
    atm_strike: float
    entry_strike: float
    ce_price: float
    pe_price: float
    straddle: float
    synthetic_future: float
    pnl: float
    adjustments: int


@dataclass(frozen=True, slots=True)
class Trade:
    """One line of the trade log.

    ``leg_pnl`` is ``None`` on an ENTRY — an opening leg has not made or lost
    anything yet, and the log renders that as a dash rather than a misleading
    0.00 sitting in a column of real numbers.

    The ``exit_*`` fields are populated on an ADJUSTMENT only, where one capture
    carries two prices: the old strike is closed and the new one opened at the
    same instant. ``ce_price``/``pe_price``/``straddle`` always describe the
    strike the position *holds* after this trade.
    """

    type: str
    t: str
    strike: float
    ce_price: float
    pe_price: float
    straddle: float
    spot: float
    cumulative_pnl: float
    leg_pnl: float | None = None
    old_strike: float | None = None
    exit_ce: float | None = None
    exit_pe: float | None = None
    exit_straddle: float | None = None


@dataclass(frozen=True, slots=True)
class Simulation:
    """Everything one run produces."""

    series: tuple[PnlPoint, ...] = ()
    trades: tuple[Trade, ...] = ()
    quantity: int = 0
    total_pnl: float = 0.0
    max_pnl: float = 0.0
    min_pnl: float = 0.0
    total_adjustments: int = 0
    sessions: tuple[str, ...] = field(default_factory=tuple)


def simulate(
    frames: Sequence[PnlFrame],
    *,
    adjustment_points: float,
    lot_size: int,
    lots: int = 1,
    strike_step: float = DEFAULT_STRIKE_STEP,
) -> Simulation:
    """Replay the adjusted short straddle over ``frames``, oldest first.

    ``frames`` must be ascending in time and already grouped-able by
    ``session``; an empty sequence yields an empty simulation rather than an
    error, which is what a day the archive never captured should look like.

    Raises :class:`ValidationError` when a strike the position must trade has no
    usable quote and none was ever seen — forward-filling cannot invent a price
    that never existed, and a straddle priced off one leg is not a cheaper
    straddle, it is a wrong one.
    """
    if lot_size <= 0 or lots <= 0:
        raise ValidationError("Lot size and lots must both be positive.", field="lot_size")
    if adjustment_points <= 0:
        raise ValidationError("Adjustment points must be positive.", field="adjustment_points")

    quantity = lot_size * lots
    if not frames:
        return Simulation(quantity=quantity)

    realized = 0.0
    adjustments = 0
    held = 0.0
    entry_straddle = 0.0
    series: list[PnlPoint] = []
    trades: list[Trade] = []
    # Last usable quote per (strike, is_call), so a strike that drops out of the
    # archive's stored window for a capture or two keeps its last known price
    # instead of tearing a hole in the curve.
    carry: dict[tuple[float, bool], float] = {}

    for day in _sessions(frames):
        for index, frame in enumerate(day):
            opening = index == 0
            closing = index == len(day) - 1
            atm = _atm(frame, strike_step)

            if opening:
                held = atm
                ce, pe = _legs(frame, held, carry)
                entry_straddle = ce + pe
                trades.append(
                    Trade(
                        type=ENTRY,
                        t=frame.timestamp,
                        strike=held,
                        ce_price=_money(ce),
                        pe_price=_money(pe),
                        straddle=_money(entry_straddle),
                        spot=_money(frame.spot),
                        leg_pnl=None,
                        cumulative_pnl=_money(realized),
                    )
                )
            elif abs(atm - held) >= adjustment_points:
                exit_ce, exit_pe = _legs(frame, held, carry)
                exit_straddle = exit_ce + exit_pe
                leg_pnl = (entry_straddle - exit_straddle) * quantity
                realized += leg_pnl

                previous = held
                held = atm
                ce, pe = _legs(frame, held, carry)
                entry_straddle = ce + pe
                adjustments += 1

                trades.append(
                    Trade(
                        type=ADJUSTMENT,
                        t=frame.timestamp,
                        old_strike=previous,
                        strike=held,
                        exit_ce=_money(exit_ce),
                        exit_pe=_money(exit_pe),
                        exit_straddle=_money(exit_straddle),
                        ce_price=_money(ce),
                        pe_price=_money(pe),
                        straddle=_money(entry_straddle),
                        spot=_money(frame.spot),
                        leg_pnl=_money(leg_pnl),
                        cumulative_pnl=_money(realized),
                    )
                )

            ce, pe = _legs(frame, held, carry)
            current = ce + pe
            unrealized = (entry_straddle - current) * quantity

            series.append(
                PnlPoint(
                    t=frame.timestamp,
                    spot=_money(frame.spot),
                    atm_strike=atm,
                    entry_strike=held,
                    ce_price=_money(ce),
                    pe_price=_money(pe),
                    straddle=_money(current),
                    # Put-call parity on the held strike: the forward the
                    # options themselves imply.
                    synthetic_future=_money(held + ce - pe),
                    pnl=_money(realized + unrealized),
                    adjustments=adjustments,
                )
            )

            if closing:
                realized += unrealized
                trades.append(
                    Trade(
                        type=EXIT,
                        t=frame.timestamp,
                        strike=held,
                        ce_price=_money(ce),
                        pe_price=_money(pe),
                        straddle=_money(current),
                        spot=_money(frame.spot),
                        leg_pnl=_money(unrealized),
                        cumulative_pnl=_money(realized),
                    )
                )

    curve = [point.pnl for point in series]
    return Simulation(
        series=tuple(series),
        trades=tuple(trades),
        quantity=quantity,
        total_pnl=curve[-1],
        max_pnl=max(curve),
        min_pnl=min(curve),
        total_adjustments=adjustments,
        sessions=tuple(dict.fromkeys(frame.session for frame in frames)),
    )


def _sessions(frames: Sequence[PnlFrame]) -> Iterator[list[PnlFrame]]:
    """The frames split into trading days, in order.

    ``groupby`` rather than a dict: the frames arrive sorted, so consecutive
    runs *are* the sessions, and grouping this way keeps a day that somehow
    appears twice from being silently merged into one long session.
    """
    for _, group in groupby(frames, key=lambda frame: frame.session):
        yield list(group)


def _atm(frame: PnlFrame, step: float) -> float:
    """The at-the-money strike for this capture, off spot."""
    strikes = sorted({row.strike for row in frame.rows})
    return atm_strike(frame.spot, strikes, step)


def _legs(
    frame: PnlFrame, strike: float, carry: dict[tuple[float, bool], float]
) -> tuple[float, float]:
    """Both legs of ``strike`` at this capture, forward-filled when unquoted."""
    return (
        _leg(frame, strike, carry, is_call=True),
        _leg(frame, strike, carry, is_call=False),
    )


def _leg(
    frame: PnlFrame,
    strike: float,
    carry: dict[tuple[float, bool], float],
    *,
    is_call: bool,
) -> float:
    price = leg_ltp(frame.rows, strike, is_call=is_call)
    key = (strike, is_call)
    if price is not None:
        carry[key] = price
        return price

    remembered = carry.get(key)
    if remembered is not None:
        return remembered

    side = "call" if is_call else "put"
    raise ValidationError(
        f"No price for the {strike:g} {side} at {frame.timestamp}; "
        "the archive does not reach that strike.",
        field="strike",
        strike=strike,
        at=frame.timestamp,
    )


def _money(value: float) -> float:
    return round(value, _PLACES)
