"""Reference price levels, derived from OHLC and nothing else.

The companion to ``indicators.py``: that module answers "what is the market
doing", this one answers "at what prices". Both are pure, dependency-free and
live in the shared kernel because more than one context wants them and a
bounded context may not import another's domain — two copies of the R1 formula
would drift, and the drift would be invisible until two pages disagreed.

Same contract as ``indicators.py``: **every function returns ``None`` when the
series is too short to compute honestly.** A thin history must never yield a
fabricated level, because a level is a number people act on.

Three things here are deliberate:

**Floats, not Decimals.** Callers hold ``Decimal`` candles and convert at the
boundary, exactly as they already do for ``indicators.py``. Pivot arithmetic is
division by three; carrying exact decimal semantics through it buys nothing and
would make the two modules disagree about their own input types.

**Confluence is the point.** Any one method's R1 is an opinion. Three
independent methods agreeing within a few points is a finding, and
:func:`cluster` is what turns a list of levels into that finding rather than
into a wall of rows nobody reads.

**Distance is expressed in ATR, not only in points.** "Forty points away" means
nothing without knowing whether the index moves eighty points a day or four
hundred. The ATR multiple is the number that transfers between instruments,
which is what lets one page speak about NIFTY, BANK NIFTY and SENSEX at once.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

#: A pivot set needs one full prior session; a period range needs at least one
#: bar. Stated as constants so the guards read as rules rather than literals.
_MIN_BARS_FOR_PRIOR = 2
_MIN_BARS_FOR_RANGE = 1


class LevelSide(StrEnum):
    """Where a level sits relative to the price being measured from."""

    ABOVE = "above"
    BELOW = "below"
    AT = "at"


class LevelOrigin(StrEnum):
    """Which method produced a level.

    Carried on every level because the origin is what makes confluence
    meaningful: two pivots agreeing is arithmetic, a pivot agreeing with an
    option wall is two different sets of participants arriving at one price.
    """

    PIVOT = "pivot"
    CENTRAL_PIVOT = "central_pivot"
    PRIOR_DAY = "prior_day"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    OPTION_WALL = "option_wall"
    MAX_PAIN = "max_pain"
    GAMMA_FLIP = "gamma_flip"


@dataclass(frozen=True, slots=True)
class Bar:
    """One OHLC bar. The only input shape this module accepts."""

    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True, slots=True)
class PivotSet:
    """Classic floor pivots for one session."""

    pivot: float
    r1: float
    r2: float
    r3: float
    s1: float
    s2: float
    s3: float


@dataclass(frozen=True, slots=True)
class CentralPivot:
    """The central pivot range — pivot, bottom and top of the CPR.

    Worth computing alongside the classic set because its *width* carries
    information the pivot levels themselves do not: a narrow CPR follows a
    coiled session and tends to precede an expansion day, a wide one follows a
    session that already expanded. The width is reported as a percentage of the
    pivot so it compares across instruments.
    """

    pivot: float
    bottom: float
    top: float
    width_percent: float


@dataclass(frozen=True, slots=True)
class PriceRange:
    """A high/low pair over some number of sessions."""

    high: float
    low: float
    #: How many bars actually went into it. A "52-week high" computed from
    #: eleven bars is not one, and the caller needs to be able to say so.
    bars: int


@dataclass(frozen=True, slots=True)
class Distance:
    """How far a level is from a price, three ways."""

    points: float
    percent: float
    #: ``None`` when no ATR was supplied — never 0.0, which would read as
    #: "right here" rather than "unknown".
    atr_multiple: float | None


@dataclass(frozen=True, slots=True)
class Level:
    """One reference price, with everything needed to render and rank it."""

    label: str
    price: float
    origin: LevelOrigin
    side: LevelSide
    distance: Distance
    #: Index into the cluster list, or ``None`` when this level stands alone.
    cluster: int | None = None


@dataclass(frozen=True, slots=True)
class LevelCluster:
    """Levels from independent methods that agree within a tolerance."""

    price: float
    members: tuple[Level, ...]

    @property
    def origins(self) -> tuple[LevelOrigin, ...]:
        """The distinct methods that produced this cluster, in order."""
        seen: list[LevelOrigin] = []
        for member in self.members:
            if member.origin not in seen:
                seen.append(member.origin)
        return tuple(seen)


# -- pivots -------------------------------------------------------------------


def classic_pivots(high: float, low: float, close: float) -> PivotSet | None:
    """Floor-trader pivots from one session's high, low and close.

    ``None`` on a degenerate session — a zero or inverted range means the bar
    is bad data, and pivots derived from it would be confidently meaningless.
    """
    if high < low or high <= 0 or low <= 0:
        return None

    pivot = (high + low + close) / 3
    span = high - low
    return PivotSet(
        pivot=pivot,
        r1=2 * pivot - low,
        r2=pivot + span,
        r3=high + 2 * (pivot - low),
        s1=2 * pivot - high,
        s2=pivot - span,
        s3=low - 2 * (high - pivot),
    )


def central_pivot_range(high: float, low: float, close: float) -> CentralPivot | None:
    """The CPR: pivot, and the band either side of it."""
    if high < low or high <= 0 or low <= 0:
        return None

    pivot = (high + low + close) / 3
    bc = (high + low) / 2
    tc = 2 * pivot - bc
    bottom, top = min(bc, tc), max(bc, tc)
    return CentralPivot(
        pivot=pivot,
        bottom=bottom,
        top=top,
        width_percent=(top - bottom) / pivot * 100 if pivot else 0.0,
    )


# -- ranges -------------------------------------------------------------------


def prior_session(bars: Sequence[Bar]) -> Bar | None:
    """The completed session before the current one.

    ``bars[-2]``, not ``bars[-1]``: the last bar is today, still forming. Every
    level measured "from yesterday" is measured from this one, and taking the
    last bar instead is the single easiest way to make a morning view quote
    levels derived from a session that has not happened yet.
    """
    if len(bars) < _MIN_BARS_FOR_PRIOR:
        return None
    return bars[-2]


def period_range(bars: Sequence[Bar], *, sessions: int) -> PriceRange | None:
    """Highest high and lowest low over the last ``sessions`` completed bars.

    One function for the weekly, monthly and 52-week ranges rather than three
    near-identical ones. Excludes the still-forming last bar for the same
    reason :func:`prior_session` does.

    Reports how many bars it actually used, so a caller asking for a year and
    getting eleven weeks can say which it has rather than mislabelling it.
    """
    if sessions < 1 or len(bars) < _MIN_BARS_FOR_PRIOR:
        return None

    completed = bars[:-1]
    window = completed[-sessions:]
    if len(window) < _MIN_BARS_FOR_RANGE:
        return None

    return PriceRange(
        high=max(bar.high for bar in window),
        low=min(bar.low for bar in window),
        bars=len(window),
    )


# -- distance and clustering --------------------------------------------------


def distance(price: float, level: float, *, atr: float | None = None) -> Distance:
    """How far ``level`` is from ``price``, signed toward the level."""
    points = level - price
    return Distance(
        points=points,
        percent=points / price * 100 if price else 0.0,
        atr_multiple=points / atr if atr else None,
    )


def side_of(price: float, level: float, *, tolerance: float = 0.0) -> LevelSide:
    """Whether ``level`` sits above, below, or effectively at ``price``."""
    if abs(level - price) <= tolerance:
        return LevelSide.AT
    return LevelSide.ABOVE if level > price else LevelSide.BELOW


def build_level(
    label: str,
    price_level: float,
    origin: LevelOrigin,
    *,
    spot: float,
    atr: float | None = None,
) -> Level:
    """One :class:`Level`, with its side and distance already resolved."""
    return Level(
        label=label,
        price=price_level,
        origin=origin,
        side=side_of(spot, price_level),
        distance=distance(spot, price_level, atr=atr),
    )


def cluster(levels: Sequence[Level], *, tolerance: float) -> tuple[LevelCluster, ...]:
    """Group levels that agree within ``tolerance`` points.

    Only groups levels of **different** origins. Two pivots landing close
    together is an artefact of one formula, not a confluence, and presenting it
    as one would manufacture significance out of arithmetic.

    ``tolerance`` is the caller's to choose — a fraction of ATR is the sensible
    basis, since a twenty-point agreement means something different on SENSEX
    than on NIFTY.
    """
    if tolerance <= 0:
        return ()

    ordered = sorted(levels, key=lambda item: item.price)
    groups: list[list[Level]] = []

    for level in ordered:
        if groups and level.price - groups[-1][0].price <= tolerance:
            groups[-1].append(level)
        else:
            groups.append([level])

    clusters: list[LevelCluster] = []
    for group in groups:
        origins = {member.origin for member in group}
        if len(origins) < _MIN_BARS_FOR_PRIOR:
            continue
        clusters.append(
            LevelCluster(
                price=sum(member.price for member in group) / len(group),
                members=tuple(group),
            )
        )
    return tuple(clusters)


def nearest(
    levels: Sequence[Level],
) -> tuple[Level | None, Level | None]:
    """The closest level below and the closest above, by their own ``side``.

    Returns ``(below, above)``. Either may be ``None`` when price sits outside
    the level map entirely — which is itself the reading, and must not be
    papered over by returning the furthest level instead.
    """
    below = [item for item in levels if item.side is LevelSide.BELOW]
    above = [item for item in levels if item.side is LevelSide.ABOVE]
    return (
        max(below, key=lambda item: item.price) if below else None,
        min(above, key=lambda item: item.price) if above else None,
    )
