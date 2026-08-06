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

**Sign.** The dealer convention: dealers are assumed long calls and short puts,
so call exposure is positive and put exposure negative. Net exposure is
therefore positive above spot (where call open interest concentrates) and
negative below it, which is the shape the profile is read for.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
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


def leg_gex(*, gamma: float, oi: int, lot_size: int, spot: float) -> float:
    """One leg's exposure in rupees per 1% move in spot.

    ``gamma * oi * lot * spot^2 * 0.01``: gamma is the change in delta per unit
    of spot, so multiplying by contract size and by one percent of spot gives
    the delta in shares that a 1% move forces, and by spot again gives it in
    money.
    """
    if lot_size <= 0 or spot <= 0.0:
        return 0.0
    return gamma * oi * lot_size * spot * spot * 0.01


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
    to tell the two apart, so the fraction of legs that carried a usable IV
    travels with the numbers.
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
    lot_size: int,
    years: float,
    axis: Sequence[float],
    rate: float = DEFAULT_RISK_FREE_RATE,
) -> GexProfile:
    """Per-strike exposure over ``axis``, in rupees per 1% move.

    ``axis`` is passed rather than inferred so every frame of a session shares
    one strike axis — the client indexes bars by position, and an axis that
    shifted between frames would slide the whole chart sideways when scrubbed.

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
    entries: list[StrikeGex] = []

    for strike in axis:
        sides: list[float] = []
        for by, sign in ((call_by, 1.0), (put_by, -1.0)):
            leg = by.get(strike)
            if leg is None:
                sides.append(0.0)
                continue
            total += 1
            if leg.iv is None:
                sides.append(0.0)
                continue
            quoted += 1
            gamma = bs_gamma(
                spot=spot, strike=strike, years=years, rate=rate, vol=leg.iv / _IV_PERCENT
            )
            sides.append(sign * leg_gex(gamma=gamma, oi=leg.oi, lot_size=lot_size, spot=spot))

        entries.append(StrikeGex(strike=strike, call_gex=sides[0], put_gex=sides[1]))

    coverage = (quoted / total) if total else 0.0
    return GexProfile(strikes=tuple(entries), iv_coverage=coverage)


# -- the four reference levels ----------------------------------------------
#
# `gamma_flip` and `net_cross` are different levels and are both drawn. The flip
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


def gamma_flip(entries: Sequence[StrikeGex]) -> float | None:
    """Where *cumulative* net exposure crosses zero, scanned from the low strike.

    Interpolated between the two strikes that bracket the crossing: the flip is
    a price, not a listed strike, and rounding it to the nearest strike would
    move it by up to half a strike interval — enough to put it on the wrong side
    of spot.

    ``None`` when the running total never changes sign, which is the honest
    answer for a one-sided book.
    """
    running = 0.0
    previous: tuple[float, float] | None = None

    for entry in entries:
        running += entry.net
        if previous is not None:
            prior_strike, prior_total = previous
            if _straddles_zero(prior_total, running):
                return _interpolate(prior_strike, prior_total, entry.strike, running)
        previous = (entry.strike, running)

    return None


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


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)
