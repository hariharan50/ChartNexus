"""Pure gamma-exposure math.

No framework, no I/O, no timezone handling — the derivations that turn option
chain rows into the per-strike dealer-gamma profile the Gamma Exposure tool
renders, and the four reference levels read off it.

Black-Scholes gamma is re-derived here rather than imported from
``market_data.domain.implied_volatility``. Contexts may not import each other,
and a gamma helper is a handful of lines: the alternative is a bridging adapter
in ``infrastructure`` for two arithmetic functions, which buys nothing. That
module remains the reference for the formulas and for the 0.07 risk-free
convention used across the codebase.

**Units.** ``leg_gex`` returns *rupee gamma per 1% move in spot* — the figure
market participants mean by "GEX". Gamma alone is per unit of spot and is
unreadable at index levels; scaling by ``spot^2 * 0.01`` puts it in money.
Open interest enters in *underlying units*, the way the feed and the rest of
this context carry it — not in lots. There is no separate lot multiplier: a
100k-unit OI is already 100k shares of exposure, and multiplying by the lot
size on top would inflate every figure by one contract's worth of shares.

**Sign.** The dealer convention: dealers are assumed long calls and short puts,
so call exposure is positive and put exposure negative. Net exposure is
therefore positive above spot (where call open interest concentrates) and
negative below it, which is the shape the profile is read for.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from itertools import pairwise

from marketcompass.contexts.options_analytics.domain.oi_math import ChainRow

# Same rate the implied-volatility solver assumes. Index gamma is barely
# sensitive to it — a 200bp error moves d1 by well under a tick of gamma — but
# the two must not disagree, or a chain's IV and its gamma describe different
# worlds.
DEFAULT_RISK_FREE_RATE = 0.07

# Brokers quote implied volatility in percent (``12.0`` meaning 12%). The
# conversion happens once, here, so no caller has to remember which convention
# it is holding.
_IV_PERCENT = 100.0

# Below this a quote is noise rather than a volatility, and d1 explodes.
_MIN_VOL = 1e-6

# The zero-gamma scan needs at least two axis points to have an interval to
# bracket a crossing in.
_MIN_FLIP_STRIKES = 2
# Bisection stops when the bracket is finer than this in points, or after this
# many halvings — either is far below a tick of the strike ladder.
_FLIP_TOLERANCE = 1e-3
_BISECT_STEPS = 60


def bs_gamma(*, spot: float, strike: float, years: float, rate: float, vol: float) -> float:
    """Black-Scholes gamma: ``pdf(d1) / (spot * vol * sqrt(years))``.

    Returns ``0.0`` for a degenerate input rather than raising or returning a
    NaN. Expiry day (``years <= 0``) and a missing volatility are both ordinary
    states of a live chain, and one bad leg must not take out the profile.
    """
    if vol <= _MIN_VOL or years <= 0.0 or spot <= 0.0 or strike <= 0.0:
        return 0.0
    sqrt_t = math.sqrt(years)
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * years) / (vol * sqrt_t)
    return _norm_pdf(d1) / (spot * vol * sqrt_t)


def leg_gex(*, gamma: float, oi: int, spot: float) -> float:
    """One leg's exposure in rupees per 1% move in spot.

    ``gamma * oi * spot^2 * 0.01``: gamma is the change in delta per unit of
    spot, so multiplying by open interest — already in underlying units, not
    lots — and by one percent of spot gives the delta in shares that a 1% move
    forces, and by spot again gives it in money.
    """
    if spot <= 0.0:
        return 0.0
    return gamma * oi * spot * spot * 0.01


@dataclass(frozen=True, slots=True)
class StrikeGex:
    """One strike's two-sided exposure, already signed for the dealer view."""

    strike: float
    #: Positive — dealers long calls.
    call_gex: float
    #: Negative — dealers short puts.
    put_gex: float

    @property
    def net(self) -> float:
        """What the dealer book is net long or short at this strike."""
        return self.call_gex + self.put_gex

    @property
    def abs(self) -> float:
        """Total gamma parked here regardless of side — how *busy* the strike is.

        A strike with 10 crore of calls and 10 crore of puts nets to zero but is
        not a quiet strike; this is the figure that says so.
        """
        return abs(self.call_gex) + abs(self.put_gex)


@dataclass(frozen=True, slots=True)
class GexProfile:
    """A chain's exposure by strike, plus how much of it is real.

    ``iv_coverage`` is not diagnostics. A chain whose broker quoted no implied
    volatility produces a profile of exact zeros, which renders as a flat line
    indistinguishable from a genuinely balanced book. The page needs to be able
    to tell the two apart, so how much of the book carried a usable IV travels
    with the numbers.

    **Weighted by open interest, not by leg count.** The IV solver fails on
    exactly the legs that do not matter: far-OTM strikes with no bid, no trade
    and no open interest. Counting legs let a wall of dead strikes report "22%
    missing" on a profile whose every meaningful strike had priced — an alarm
    about numbers that were fine, on a caption readers use to decide whether to
    trust the figures. A leg with no open interest contributes no gamma whether
    or not it priced, so it is weightless here too.
    """

    strikes: tuple[StrikeGex, ...]
    iv_coverage: float

    @property
    def net_total(self) -> float:
        return sum(entry.net for entry in self.strikes)

    @property
    def abs_total(self) -> float:
        return sum(entry.abs for entry in self.strikes)


def strike_profile(
    rows: Iterable[ChainRow],
    *,
    spot: float,
    years: float,
    axis: Sequence[float],
    rate: float = DEFAULT_RISK_FREE_RATE,
) -> GexProfile:
    """Per-strike exposure over ``axis``, in rupees per 1% move.

    ``axis`` is passed rather than inferred so every frame of a session shares
    one strike axis — the client indexes bars by position, and an axis that
    shifted between frames would slide the whole chart sideways when scrubbed.

    A leg with no quoted ``iv`` contributes ``0.0`` and is counted against
    coverage, in proportion to the open interest it was carrying. It is never
    assigned a fallback volatility: a made-up 20% would produce a confident bar
    indistinguishable from a real one.
    """
    call_by: dict[float, ChainRow] = {}
    put_by: dict[float, ChainRow] = {}
    for row in rows:
        (call_by if row.is_call else put_by)[row.strike] = row

    quoted_oi = 0
    total_oi = 0
    entries: list[StrikeGex] = []

    for strike in axis:
        sides: list[float] = []
        for by, sign in ((call_by, 1.0), (put_by, -1.0)):
            leg = by.get(strike)
            if leg is None:
                sides.append(0.0)
                continue
            # Negative open interest is not a thing, but a bad feed row must not
            # be able to drag the ratio below zero or above one.
            weight = max(0, leg.oi)
            total_oi += weight
            if leg.iv is None:
                sides.append(0.0)
                continue
            quoted_oi += weight
            gamma = bs_gamma(
                spot=spot, strike=strike, years=years, rate=rate, vol=leg.iv / _IV_PERCENT
            )
            sides.append(sign * leg_gex(gamma=gamma, oi=leg.oi, spot=spot))

        entries.append(StrikeGex(strike=strike, call_gex=sides[0], put_gex=sides[1]))

    # A chain with no open interest anywhere has no exposure to have covered.
    # Reporting 0.0 keeps the "we cannot vouch for this" reading, which is the
    # right one for an axis of empty strikes.
    coverage = (quoted_oi / total_oi) if total_oi else 0.0
    return GexProfile(strikes=tuple(entries), iv_coverage=coverage)


# -- the four reference levels ----------------------------------------------
#
# `zero_gamma` and `net_cross` are different levels and are both drawn. The flip
# is where the *book as a whole* turns from net short to net long gamma — the
# level below which dealer hedging amplifies moves instead of damping them. The
# cross is where the *per-strike* profile changes sign, which is roughly where
# put open interest stops outweighing call open interest. They coincide only on
# a symmetric chain; on a real one they are tens of points apart, and collapsing
# one into the other loses the distinction the page exists to show.


def call_wall(entries: Sequence[StrikeGex]) -> float | None:
    """The strike holding the most call gamma — where hedging caps a rally."""
    candidates = [entry for entry in entries if entry.call_gex > 0.0]
    if not candidates:
        return None
    return max(candidates, key=lambda entry: entry.call_gex).strike


def put_wall(entries: Sequence[StrikeGex]) -> float | None:
    """The strike holding the most put gamma — where hedging cushions a fall."""
    candidates = [entry for entry in entries if entry.put_gex < 0.0]
    if not candidates:
        return None
    return min(candidates, key=lambda entry: entry.put_gex).strike


def zero_gamma(
    rows: Iterable[ChainRow],
    *,
    spot: float,
    years: float,
    axis: Sequence[float],
    rate: float = DEFAULT_RISK_FREE_RATE,
) -> float | None:
    """The spot level at which the book's net dealer gamma is zero — the flip.

    Not a strike read off the current profile: gamma depends on where spot is,
    so the flip is the *price at which the whole book would be gamma-neutral*,
    and finding it means re-pricing every strike's gamma at candidate levels.
    Below the flip dealers are net short gamma and hedging amplifies moves;
    above it they are long and damp them.

    The book's net gamma is scanned across ``axis`` and bisected on the sign
    change nearest ``spot`` — the money is where the flip is traded, and a noisy
    chain can also cross far out in the wings. Money scaling (the lot and
    ``level^2 * 0.01`` that turn gamma into rupees) is common to every strike at
    a given level and so cannot move the crossing, and is left out.

    ``None`` when net gamma keeps one sign across the whole range — a book that
    never flips, which is the honest answer for a one-sided chain and for an
    expired one whose gamma is zero everywhere.
    """
    call_by: dict[float, ChainRow] = {}
    put_by: dict[float, ChainRow] = {}
    for row in rows:
        (call_by if row.is_call else put_by)[row.strike] = row

    strikes = list(axis)
    if len(strikes) < _MIN_FLIP_STRIKES:
        return None

    def net_gamma(level: float) -> float:
        total = 0.0
        for strike in strikes:
            call = call_by.get(strike)
            if call is not None and call.iv is not None:
                total += (
                    bs_gamma(
                        spot=level, strike=strike, years=years, rate=rate, vol=call.iv / _IV_PERCENT
                    )
                    * call.oi
                )
            put = put_by.get(strike)
            if put is not None and put.iv is not None:
                total -= (
                    bs_gamma(
                        spot=level, strike=strike, years=years, rate=rate, vol=put.iv / _IV_PERCENT
                    )
                    * put.oi
                )
        return total

    samples = [(strike, net_gamma(strike)) for strike in strikes]
    brackets = [(k0, g0, k1) for (k0, g0), (k1, g1) in pairwise(samples) if _straddles_zero(g0, g1)]
    if not brackets:
        return None

    k0, g0, k1 = min(brackets, key=lambda b: abs(0.5 * (b[0] + b[2]) - spot))
    return _bisect(net_gamma, k0, g0, k1)


def net_cross(entries: Sequence[StrikeGex], spot: float) -> float | None:
    """Where the *per-strike* net profile changes sign, nearest ``spot``.

    Nearest to spot rather than the first found: a noisy chain crosses zero
    several times out in the wings, and only the crossing next to the money is
    a level anyone trades against.
    """
    crossings: list[float] = []
    for prior, entry in pairwise(entries):
        if _straddles_zero(prior.net, entry.net):
            crossings.append(_interpolate(prior.strike, prior.net, entry.strike, entry.net))

    if not crossings:
        return None
    return min(crossings, key=lambda level: abs(level - spot))


# -- helpers ----------------------------------------------------------------


def _straddles_zero(before: float, after: float) -> bool:
    """True when the value changed sign between two samples.

    An exact ``0.0`` on the later sample counts: that is a crossing landing
    precisely on a listed strike, and ignoring it would drop the level entirely
    rather than report it at the strike itself.
    """
    if before == 0.0 and after == 0.0:
        return False
    return (before <= 0.0 <= after) or (before >= 0.0 >= after)


def _interpolate(x0: float, y0: float, x1: float, y1: float) -> float:
    """The x where the segment ``(x0,y0)-(x1,y1)`` meets zero."""
    span = y1 - y0
    if span == 0.0:
        return x1
    return x0 + (x1 - x0) * (-y0 / span)


def _bisect(f: Callable[[float], float], lo: float, f_lo: float, hi: float) -> float:
    """The root of ``f`` in ``[lo, hi]``, given ``f(lo) = f_lo`` brackets zero.

    A linear interpolant would place the flip well if ``f`` were straight, but
    net gamma bows between strikes, so the level is bisected — halving the
    bracket to sub-point precision the axis grid could never resolve on its own.
    """
    for _ in range(_BISECT_STEPS):
        mid = 0.5 * (lo + hi)
        f_mid = f(mid)
        if f_mid == 0.0 or hi - lo < _FLIP_TOLERANCE:
            return mid
        if _straddles_zero(f_lo, f_mid):
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return 0.5 * (lo + hi)


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)
