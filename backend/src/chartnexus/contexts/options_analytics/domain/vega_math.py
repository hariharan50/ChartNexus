"""Pure vega math for the Vega Analysis tool.

No framework, no I/O, no timezone handling — the derivations that turn option
chain rows into a per-strike aggregate-vega profile, and the synthetic future
read off the money via put-call parity.

Black-Scholes vega is re-derived here rather than imported from
``market_data.domain.implied_volatility``. Contexts may not import each other,
and a vega helper is a handful of lines: the alternative is a bridging adapter
in ``infrastructure`` for two arithmetic functions, which buys nothing. That
module remains the reference for the formula (``_vega``) and for the 0.07
risk-free convention used across the codebase. This mirrors ``gex_math``, which
re-derives gamma for exactly the same reason.

**Units.** ``leg_vega`` returns *rupee vega per one volatility point* — the
change in the position's value for a 1-percentage-point move in implied
volatility. Raw Black-Scholes vega is per unit of vol (1.0 == 100 points), so
the ``* 0.01`` scales it to the one-point step a reader thinks in. Open interest
enters in *underlying units*, the way the feed and the rest of this context
carry it — not in lots — so there is no separate lot multiplier: a 100k-unit OI
is already 100k shares of exposure, and multiplying by the lot size on top would
inflate every figure by one contract's worth of shares.

**Sign.** Both sides are returned *positive* here — a long option always has
positive vega. The Vega Analysis page plots each side's *change since the
session open*, and that delta is what carries the sign the chart reads.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from chartnexus.contexts.options_analytics.domain.oi_math import ChainRow

# Same rate the implied-volatility solver assumes. Vega is only mildly sensitive
# to it, but the two must not disagree, or a chain's IV and its vega describe
# different worlds.
DEFAULT_RISK_FREE_RATE = 0.07

# Brokers quote implied volatility in percent (``12.0`` meaning 12%). The
# conversion happens once, here, so no caller has to remember the convention.
_IV_PERCENT = 100.0

# Below this a quote is noise rather than a volatility, and d1 explodes.
_MIN_VOL = 1e-6

# One volatility point is 1/100 of a unit of vol; raw BS vega is per unit.
_ONE_VOL_POINT = 0.01


def bs_vega(*, spot: float, strike: float, years: float, rate: float, vol: float) -> float:
    """Black-Scholes vega, per one volatility point: ``spot * sqrt(t) * pdf(d1) * 0.01``.

    Returns ``0.0`` for a degenerate input rather than raising or returning a
    NaN. Expiry day (``years <= 0``) and a missing volatility are both ordinary
    states of a live chain, and one bad leg must not take out the profile.
    """
    if vol <= _MIN_VOL or years <= 0.0 or spot <= 0.0 or strike <= 0.0:
        return 0.0
    sqrt_t = math.sqrt(years)
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * years) / (vol * sqrt_t)
    return spot * sqrt_t * _norm_pdf(d1) * _ONE_VOL_POINT


def leg_vega(*, vega: float, oi: int) -> float:
    """One leg's vega exposure in rupees per one-point move in implied vol.

    ``vega * oi``: per-share vega scaled by the open interest, which is already
    in underlying units, not lots. Unlike gamma exposure there is no ``spot^2``
    term — vega is already a rupee change in the option's price, not a per-unit
    sensitivity that needs squaring back into money.
    """
    return vega * oi


@dataclass(frozen=True, slots=True)
class StrikeVega:
    """One strike's two-sided vega exposure, both sides positive."""

    strike: float
    call_vega: float
    put_vega: float

    @property
    def total(self) -> float:
        """Both sides parked at this strike, regardless of side."""
        return self.call_vega + self.put_vega


@dataclass(frozen=True, slots=True)
class VegaProfile:
    """A chain's vega exposure by strike, plus how much of it is real.

    ``iv_coverage`` is not diagnostics. A chain whose broker quoted no implied
    volatility produces a profile of exact zeros, which is indistinguishable
    from a genuinely flat book. The fraction of legs that carried a usable IV
    travels with the numbers so the page can tell the two apart.
    """

    strikes: tuple[StrikeVega, ...]
    iv_coverage: float

    @property
    def call_total(self) -> float:
        return sum(entry.call_vega for entry in self.strikes)

    @property
    def put_total(self) -> float:
        return sum(entry.put_vega for entry in self.strikes)


def vega_profile(
    rows: Iterable[ChainRow],
    *,
    spot: float,
    years: float,
    axis: Sequence[float],
    rate: float = DEFAULT_RISK_FREE_RATE,
) -> VegaProfile:
    """Per-strike aggregate vega over ``axis``, in rupees per vol point.

    ``axis`` is passed rather than inferred so every frame of a session shares
    one strike axis — the client indexes bars by position, and an axis that
    shifted between frames would slide the whole chart sideways when re-windowed.

    A leg with no quoted ``iv`` contributes ``0.0`` and is counted against
    coverage. It is never assigned a fallback volatility: a made-up 20% would
    produce a confident bar indistinguishable from a real one.
    """
    call_by: dict[float, ChainRow] = {}
    put_by: dict[float, ChainRow] = {}
    for row in rows:
        (call_by if row.is_call else put_by)[row.strike] = row

    quoted = 0
    total = 0
    entries: list[StrikeVega] = []

    for strike in axis:
        sides: list[float] = []
        for by in (call_by, put_by):
            leg = by.get(strike)
            if leg is None:
                sides.append(0.0)
                continue
            total += 1
            if leg.iv is None:
                sides.append(0.0)
                continue
            quoted += 1
            vega = bs_vega(
                spot=spot, strike=strike, years=years, rate=rate, vol=leg.iv / _IV_PERCENT
            )
            sides.append(leg_vega(vega=vega, oi=leg.oi))

        entries.append(StrikeVega(strike=strike, call_vega=sides[0], put_vega=sides[1]))

    coverage = (quoted / total) if total else 0.0
    return VegaProfile(strikes=tuple(entries), iv_coverage=coverage)


def synthetic_future(rows: Iterable[ChainRow], atm_strike: float | None) -> float | None:
    """The synthetic future at the money, by put-call parity.

    ``call_ltp - put_ltp + strike`` at the ATM strike: the forward the options
    themselves imply, which is what "Synth Future" names. Returns ``None`` when
    the ATM is unknown or either ATM leg is missing — the caller then falls back
    to the tradable future so the line still has somewhere to sit.

    A leg priced at zero is treated as no leg: an illiquid quote of 0.0 would
    drag the parity forward to the strike itself, a level the market never made.
    """
    if atm_strike is None:
        return None
    call_ltp: float | None = None
    put_ltp: float | None = None
    for row in rows:
        if row.strike != atm_strike:
            continue
        if row.is_call and row.ltp > 0.0:
            call_ltp = row.ltp
        elif row.is_put and row.ltp > 0.0:
            put_ltp = row.ltp
    if call_ltp is None or put_ltp is None:
        return None
    return call_ltp - put_ltp + atm_strike


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)
