"""How far the index can plausibly travel today, by three different measures.

The three are reported **side by side and never blended**, which is the one
design decision in this module worth defending.

They are not three estimates of one quantity:

* **Straddle** — what the option market is charging for a move between now and
  this expiry. A price, set by people with money on it.
* **VIX** — an annualised 30-day implied volatility, scaled down to one
  session. A different horizon and a different instrument set.
* **ATR** — what the index has actually travelled lately. Realised, not
  implied, and backward-looking by construction.

Averaging them produces a number with no definition — it is neither what the
market charges nor what the index does. Worse, the *gap between them* is the
informative part: straddle far above ATR means options are pricing an event
(a policy day, a result), straddle far below means complacency. A blend
destroys exactly the signal a pre-market reader wants.

So :func:`reconcile` returns all three, plus a note when they disagree enough
to be worth saying out loud.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

#: Trading sessions in a year — the divisor that scales an annualised VIX to a
#: single session. 252, not 365: volatility accrues on days the market trades.
_SESSIONS_PER_YEAR = 252

#: Straddle price as a fraction of the move it implies. A long-standing
#: approximation: an at-the-money straddle costs roughly 0.8 of the one-sigma
#: move it covers. Good to a few percent, and honest about being a rule of
#: thumb rather than a Black-Scholes inversion.
_STRADDLE_TO_SIGMA = 1.25

#: Below this the three measures are saying the same thing and the note stays
#: quiet. Above it, the disagreement is the reading.
_DIVERGENCE_PERCENT = 35.0


@dataclass(frozen=True, slots=True)
class MoveEstimate:
    """One measure's expected move, in points and percent."""

    basis: str
    points: float
    percent: float
    upper: float
    lower: float


@dataclass(frozen=True, slots=True)
class ExpectedMove:
    """Every measure available, and what their spread implies."""

    spot: float
    straddle: MoveEstimate | None
    vix: MoveEstimate | None
    atr: MoveEstimate | None
    days_to_expiry: int | None
    #: Set only when the measures disagree materially. The UI prints it beside
    #: the three rows rather than resolving the disagreement itself.
    note: str | None


def _estimate(basis: str, spot: float, points: float) -> MoveEstimate | None:
    if spot <= 0 or points <= 0 or not math.isfinite(points):
        return None
    return MoveEstimate(
        basis=basis,
        points=points,
        percent=points / spot * 100,
        upper=spot + points,
        lower=spot - points,
    )


def from_straddle(spot: Decimal | None, straddle_price: Decimal | None) -> MoveEstimate | None:
    """The move the option market is charging for, to this expiry.

    Note the horizon: this is the move to **expiry**, not to today's close. On
    a Monday with a Thursday expiry it covers four sessions, and presenting it
    as a one-day range would overstate today by roughly double.
    """
    if spot is None or straddle_price is None or straddle_price <= 0:
        return None
    return _estimate("straddle", float(spot), float(straddle_price) / _STRADDLE_TO_SIGMA)


def from_vix(
    spot: Decimal | None, india_vix: Decimal | None, *, sessions: int = 1
) -> MoveEstimate | None:
    """One sigma over ``sessions``, from the annualised volatility index."""
    if spot is None or india_vix is None or india_vix <= 0 or sessions < 1:
        return None
    annual = float(india_vix) / 100
    scaled = annual * math.sqrt(sessions / _SESSIONS_PER_YEAR)
    return _estimate("vix", float(spot), float(spot) * scaled)


def from_atr(spot: Decimal | None, atr: float | None) -> MoveEstimate | None:
    """What the index has actually been travelling, per session."""
    if spot is None or atr is None or atr <= 0:
        return None
    return _estimate("atr", float(spot), atr)


def reconcile(
    spot: Decimal | None,
    *,
    straddle_price: Decimal | None = None,
    india_vix: Decimal | None = None,
    atr: float | None = None,
    days_to_expiry: int | None = None,
) -> ExpectedMove | None:
    """All three measures, with a note when they materially disagree."""
    if spot is None or spot <= 0:
        return None

    straddle = from_straddle(spot, straddle_price)
    vix = from_vix(spot, india_vix, sessions=max(1, days_to_expiry or 1))
    realised = from_atr(spot, atr)

    return ExpectedMove(
        spot=float(spot),
        straddle=straddle,
        vix=vix,
        atr=realised,
        days_to_expiry=days_to_expiry,
        note=_note(straddle, realised),
    )


def _note(implied_move: MoveEstimate | None, realised: MoveEstimate | None) -> str | None:
    """Name a material gap between what is priced and what has been happening."""
    if implied_move is None or realised is None or realised.points <= 0:
        return None

    divergence = (implied_move.points - realised.points) / realised.points * 100
    if abs(divergence) < _DIVERGENCE_PERCENT:
        return None
    if divergence > 0:
        return (
            "Options are pricing a wider move than the index has been making — "
            "typically an event premium."
        )
    return (
        "Options are pricing a narrower move than the index has been making — "
        "the range is cheap relative to realised movement."
    )
