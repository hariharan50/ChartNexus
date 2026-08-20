"""Pure open-interest math.

No framework, no I/O, no timezone handling — just the derivations that turn a
list of option-chain rows into the numbers the Open Interest tool renders. Kept
pure so it is trivial to unit-test and safe to reuse from any layer.

The three headline figures — PCR, ATM, and max pain — are defined here once and
computed the same way for the live tier and any future snapshot tier.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

_CALL = "CE"
_PUT = "PE"
_DEFAULT_STEP = 50.0


@dataclass(frozen=True, slots=True)
class ChainRow:
    """One leg of one strike, numbers already parsed.

    ``iv`` stays ``None`` when the broker did not quote it — it must never be
    coerced to ``0.0``, which would read as a real (and wrong) volatility.
    """

    strike: float
    option_type: str  # "CE" | "PE"
    oi: int
    oi_change: int
    ltp: float
    volume: int
    price_change: float = 0.0
    iv: float | None = None

    @property
    def is_call(self) -> bool:
        return self.option_type.upper() == _CALL

    @property
    def is_put(self) -> bool:
        return self.option_type.upper() == _PUT


def pcr_oi(rows: Iterable[ChainRow]) -> float:
    """Put/Call ratio by open interest: ΣPE.oi / ΣCE.oi.

    Returns ``0.0`` when there is no call interest — a ratio with an empty
    denominator is undefined, and 0 is a safer render than an infinity.
    """
    call_oi = 0
    put_oi = 0
    for row in rows:
        if row.is_call:
            call_oi += row.oi
        elif row.is_put:
            put_oi += row.oi
    if call_oi <= 0:
        return 0.0
    return round(put_oi / call_oi, 4)


def atm_strike(spot: float, strikes: Sequence[float], step: float = _DEFAULT_STEP) -> float:
    """The listed strike nearest spot.

    Falls back to spot rounded to the nearest ``step`` when no strikes are
    listed, so a caller always gets a usable anchor.
    """
    if not strikes:
        return round(spot / step) * step
    return min(strikes, key=lambda s: abs(s - spot))


def strike_window(*, atm: float, step: float, span: int | None) -> tuple[float, float]:
    """The inclusive strike range ``span`` steps either side of ``atm``.

    ``span=None`` means "the whole chain" and widens to infinity rather than
    picking an arbitrarily large number — the caller then has one filter to
    apply, not a filter plus a special case.

    Expressed in *steps* rather than points because the same "± 10 strikes"
    means 500 points on NIFTY and 1000 on BANKNIFTY, and the reader is choosing
    strikes.
    """
    if span is None:
        return (float("-inf"), float("inf"))
    reach = abs(step) * span
    return (atm - reach, atm + reach)


def rows_within(rows: Iterable[ChainRow], low: float, high: float) -> tuple[ChainRow, ...]:
    """The legs whose strike falls inside ``[low, high]``.

    The bounds are compared with a small tolerance: strike ladders arrive as
    floats, and ``24350.0`` computed as ``24500 - 3 * 50`` is not always the
    ``24350.0`` the broker sent. Without it the edge strike of the window drops
    out roughly at random, which reads as an OI total that jitters.
    """
    return tuple(row for row in rows if low - 1e-6 <= row.strike <= high + 1e-6)


def max_pain(rows: Iterable[ChainRow], strikes: Sequence[float]) -> float:
    """The expiry level minimising total intrinsic value owed to option holders.

    For each candidate settlement price ``P`` sum the in-the-money payout across
    every leg; the strike with the least total pain is where writers would most
    like the market to close. Returns ``0.0`` when there is nothing to price.
    """
    materialised = list(rows)
    if not strikes or not materialised:
        return 0.0

    best_strike = 0.0
    least_pain = float("inf")
    for candidate in strikes:
        pain = 0.0
        for row in materialised:
            if row.is_call:
                pain += row.oi * max(0.0, candidate - row.strike)
            elif row.is_put:
                pain += row.oi * max(0.0, row.strike - candidate)
        if pain < least_pain:
            least_pain = pain
            best_strike = candidate
    return best_strike
