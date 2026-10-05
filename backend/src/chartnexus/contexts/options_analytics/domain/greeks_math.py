"""Pure Black-Scholes greeks for a single option leg.

No framework, no I/O, no timezone handling — the four sensitivities the Option
Greeks tool plots, derived from the quantities a chain row already carries.

Re-derived here rather than imported from ``market_data.domain.implied_volatility``
for the same reason ``vega_math`` and ``gex_math`` re-derive theirs: contexts may
not import each other, and a bridging adapter in ``infrastructure`` for a handful
of arithmetic functions buys nothing. That module remains the reference for the
formula and for the 0.07 risk-free convention used across the codebase.

**Conventions**, chosen to match what a reader expects to see on the chart:

* ``delta`` — per unit of underlying. Calls are positive, puts negative, both
  bounded by ±1.
* ``gamma`` — delta change per one-point move in the underlying. Same for calls
  and puts; a small number for an index (1e-4 … 1e-3), and deliberately not
  rescaled, because the figure in every other tool and in a broker terminal is
  the raw one.
* ``theta`` — rupees per *calendar day*, negative for a long option. The annual
  BS theta divided by 365, which is the number traders quote and the one the
  reference screenshots show (-14.88 on an index ATM option, not -5,400).
* ``vega`` — rupees per *one volatility point* (a 1% move in IV), i.e. raw BS
  vega scaled by 0.01. Identical to ``vega_math.bs_vega``, which this module
  does not import only because that one aggregates by open interest.

Every function returns ``0.0`` for a degenerate input — expiry day, a missing
volatility, a non-positive price — rather than raising or returning NaN. Both
are ordinary states of a live chain, and one bad leg must not take out a series.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Same rate the implied-volatility solver and the vega profile assume. The three
# must not disagree, or a chain's IV and its greeks describe different worlds.
DEFAULT_RISK_FREE_RATE = 0.07

# Brokers quote implied volatility in percent (``12.0`` meaning 12%).
IV_PERCENT = 100.0

# Below this a quote is noise rather than a volatility, and d1 explodes.
_MIN_VOL = 1e-6

# One volatility point is 1/100 of a unit of vol; raw BS vega is per unit.
_ONE_VOL_POINT = 0.01

# Theta is quoted per calendar day, and the year fraction is calendar-based too.
_DAYS_IN_YEAR = 365.0

_CALL = "CE"


@dataclass(frozen=True, slots=True)
class Greeks:
    """One leg's four sensitivities, in the units documented above."""

    delta: float
    gamma: float
    theta: float
    vega: float

    @classmethod
    def zero(cls) -> Greeks:
        return cls(delta=0.0, gamma=0.0, theta=0.0, vega=0.0)


def greeks(
    *,
    option_type: str,
    spot: float,
    strike: float,
    years: float,
    vol: float,
    rate: float = DEFAULT_RISK_FREE_RATE,
) -> Greeks:
    """The four greeks for one leg. ``vol`` is a unit volatility (0.14 == 14%).

    A degenerate leg returns zeros across the board — see the module docstring.
    """
    if vol <= _MIN_VOL or years <= 0.0 or spot <= 0.0 or strike <= 0.0:
        return Greeks.zero()

    is_call = option_type.upper() == _CALL
    sqrt_t = math.sqrt(years)
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * years) / (vol * sqrt_t)
    d2 = d1 - vol * sqrt_t
    pdf = _norm_pdf(d1)
    discount = math.exp(-rate * years)

    delta = _norm_cdf(d1) if is_call else _norm_cdf(d1) - 1.0
    gamma = pdf / (spot * vol * sqrt_t)
    vega = spot * sqrt_t * pdf * _ONE_VOL_POINT

    # Two terms: the decay of optionality, which is negative for both sides, and
    # the carry on the discounted strike, whose sign flips with the side.
    decay = -(spot * pdf * vol) / (2.0 * sqrt_t)
    carry = rate * strike * discount * (_norm_cdf(d2) if is_call else -_norm_cdf(-d2))
    theta = (decay - carry) / _DAYS_IN_YEAR

    return Greeks(delta=delta, gamma=gamma, theta=theta, vega=vega)


def unit_vol(iv_percent: float | None) -> float:
    """A quoted percentage volatility as the unit figure Black-Scholes wants.

    ``None`` becomes ``0.0``, which every greek above reads as "not priceable"
    and answers with a zero rather than a fabricated sensitivity.
    """
    if iv_percent is None or iv_percent <= 0.0:
        return 0.0
    return iv_percent / IV_PERCENT


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)
