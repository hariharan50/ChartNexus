"""Relative Rotation Graph: the JdK RS-Ratio / RS-Momentum plane.

A sector is plotted against a benchmark on two axes, both centred on 100:

* **RS-Ratio** — how strong the sector is relative to the benchmark *now*,
  measured against its own recent range rather than in absolute terms.
* **RS-Momentum** — whether that relative strength is still improving. It is
  the rate of change of RS-Ratio, normalised the same way.

Joined over consecutive periods the pair traces a *tail*, and because momentum
leads ratio the tail tends to rotate clockwise through four quadrants:
``improving`` (top-left) → ``leading`` (top-right) → ``weakening``
(bottom-right) → ``lagging`` (bottom-left) → back round.

**Why normalisation rather than the raw ratio.** A sector trading at 0.4 times the
index and one at 2.1 times are not comparable as numbers, but "two standard
deviations above its own recent relative strength" is the same statement about
either. Centring on 100 is what lets a dozen sectors of wildly different levels
share one grid, and it is why the axes read 97-104 rather than in index points.

**Floats, not Decimal.** Everything above is statistics on a ratio — means,
standard deviations, z-scores — where Decimal buys no accuracy and costs
readability. Prices arrive as Decimal and are converted once, at the boundary
in :func:`relative_strength`; nothing here is money and nothing is summed into
a figure anyone reconciles.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from chartnexus.contexts.market_breadth.domain.rotation import Quadrant

#: Periods the z-score is measured over. Fourteen is the shortest window that
#: still gives a stable standard deviation — below about ten, one outlying
#: period moves the mean and the spread together and every sector lurches.
DEFAULT_WINDOW = 14

#: Periods of smoothing applied to each axis after normalising. Raw z-scores
#: jitter enough that a tail looks like a scribble; this is what makes the
#: rotation legible without hiding a genuine turn.
DEFAULT_SMOOTHING = 3

#: How many periods back the momentum rate-of-change reaches. One period is
#: pure noise at intraday cadence; four is long enough to be a direction.
DEFAULT_MOMENTUM_SPAN = 4

#: Trailing points a tail carries by default — the reference terminals' own
#: setting, and about as many as stay readable with a dozen sectors on one grid.
DEFAULT_TAIL = 8

#: Where both axes cross. Every number on this plane is an offset from it,
#: so it is named rather than repeated as a literal at each comparison.
CENTRE = 100.0

#: The shortest meaningful window or span. One period is not a mean and
#: not a spread, so anything below two is a passthrough rather than an error.
_MIN_SPAN = 2

#: Guards a division by a flat series. A sector that has not moved relative to
#: the benchmark all window has zero spread, and its z-score is 0 by definition
#: rather than an infinity.
_FLAT = 1e-12


@dataclass(frozen=True, slots=True)
class RrgPoint:
    """One sector at one period, on the rotation plane."""

    at: datetime
    rs_ratio: float
    rs_momentum: float

    @property
    def quadrant(self) -> Quadrant:
        return classify(self.rs_ratio, self.rs_momentum)


@dataclass(frozen=True, slots=True)
class RrgTail:
    """One sector's path across the plane, oldest point first."""

    sector: str
    points: tuple[RrgPoint, ...] = ()
    #: Members that priced into the composite. Carried so the page can say a
    #: sector was measured over 4 of 7 names rather than implying all of them.
    measured: int = 0
    members: int = 0

    @property
    def head(self) -> RrgPoint | None:
        """Where the sector stands now — the point the label is drawn at."""
        return self.points[-1] if self.points else None

    @property
    def quadrant(self) -> Quadrant:
        head = self.head
        return head.quadrant if head else Quadrant.LAGGING


def classify(rs_ratio: float, rs_momentum: float) -> Quadrant:
    """Which quadrant a point falls in.

    The axes cross at 100, and the boundary belongs to the stronger reading in
    both directions: exactly 100 is "not yet weakening" rather than "already
    lagging". A point sitting precisely on the cross is vanishingly rare in
    real data, but the rule has to be stated somewhere or two call sites will
    disagree about it.
    """
    if rs_ratio >= CENTRE:
        return Quadrant.LEADING if rs_momentum >= CENTRE else Quadrant.WEAKENING
    return Quadrant.IMPROVING if rs_momentum >= CENTRE else Quadrant.LAGGING


def relative_strength(
    sector: Sequence[Decimal | float],
    benchmark: Sequence[Decimal | float],
) -> list[float]:
    """The sector's level as a percentage of the benchmark's, period by period.

    Both series must already be aligned on the same periods — this cannot tell
    a missing bucket from a flat one, so the caller aligns and this only
    divides. A benchmark period at or below zero yields no point: it is a
    broken capture, not a price, and carrying it forward would plant a spike in
    the middle of every sector's tail at once.
    """
    out: list[float] = []
    for sector_value, benchmark_value in zip(sector, benchmark, strict=False):
        base = float(benchmark_value)
        if base <= 0:
            continue
        out.append(float(sector_value) / base * 100.0)
    return out


def normalise(values: Sequence[float], *, window: int = DEFAULT_WINDOW) -> list[float]:
    """Centre a series on 100 by its own rolling z-score.

    The first ``window - 1`` periods have no full lookback and are dropped
    rather than measured against a partial one: a z-score over three samples
    is not a weaker version of a z-score over fourteen, it is a different and
    much noisier statistic, and splicing the two makes the start of every tail
    swing wildly for a reason the reader cannot see.
    """
    if window < _MIN_SPAN or len(values) < window:
        return []

    out: list[float] = []
    for end in range(window, len(values) + 1):
        sample = values[end - window : end]
        spread = statistics.pstdev(sample)
        if spread < _FLAT:
            # Flat against the benchmark all window: dead centre, by definition.
            out.append(CENTRE)
            continue
        out.append(CENTRE + (values[end - 1] - statistics.fmean(sample)) / spread)
    return out


def smooth(values: Sequence[float], *, span: int = DEFAULT_SMOOTHING) -> list[float]:
    """Trailing simple mean. Shortens the series by ``span - 1`` periods."""
    if span < _MIN_SPAN or len(values) < span:
        return list(values)
    return [statistics.fmean(values[end - span : end]) for end in range(span, len(values) + 1)]


def momentum(values: Sequence[float], *, span: int = DEFAULT_MOMENTUM_SPAN) -> list[float]:
    """Rate of change of RS-Ratio, as a percentage of where it stood.

    Expressed as a ratio rather than a difference so it normalises on the same
    footing as the strength axis: RS-Ratio is already a z-score, and the
    *change* in a z-score has no natural scale of its own.
    """
    if span < 1 or len(values) <= span:
        return []
    out: list[float] = []
    for index in range(span, len(values)):
        previous = values[index - span]
        if abs(previous) < _FLAT:
            out.append(CENTRE)
            continue
        out.append(values[index] / previous * CENTRE)
    return out


def rotation(
    sector: Sequence[Decimal | float],
    benchmark: Sequence[Decimal | float],
    stamps: Sequence[datetime],
    *,
    window: int = DEFAULT_WINDOW,
    smoothing: int = DEFAULT_SMOOTHING,
    momentum_span: int = DEFAULT_MOMENTUM_SPAN,
    tail: int = DEFAULT_TAIL,
) -> tuple[RrgPoint, ...]:
    """The full pipeline: two price series in, one tail out.

    Every stage shortens the series, and the stamps are re-aligned from the
    *right* at the end rather than tracked through each step. Taking the last
    ``n`` stamps for the last ``n`` points is correct because every operation
    here is trailing — each output period is the one its last input fell in —
    and doing it once at the end is far easier to verify than threading an
    offset through four functions.

    Returns empty when the inputs cannot fill the window, which is the normal
    answer for a thin sector or a shallow archive rather than an error.
    """
    rs = relative_strength(sector, benchmark)
    ratio = smooth(normalise(rs, window=window), span=smoothing)
    if not ratio:
        return ()

    raw_momentum = momentum(ratio, span=momentum_span)
    if not raw_momentum:
        return ()
    # Normalised over the same window so both axes are the same kind of number.
    # A shorter window here would make momentum the jumpier of the two, which
    # inverts the whole point: momentum is supposed to *lead* ratio, not
    # outrun it.
    momentum_axis = smooth(normalise(raw_momentum, window=window), span=smoothing)
    if not momentum_axis:
        return ()

    # Both axes are trailing, so they end on the same period and align from the
    # right. Ratio is the longer of the two and is trimmed back to match.
    span = min(len(ratio), len(momentum_axis), len(stamps))
    if span <= 0:
        return ()

    points = [
        RrgPoint(at=at, rs_ratio=x, rs_momentum=y)
        for at, x, y in zip(stamps[-span:], ratio[-span:], momentum_axis[-span:], strict=True)
    ]
    return tuple(points[-tail:]) if tail > 0 else tuple(points)


def composite(
    members: Sequence[Sequence[Decimal | float]],
) -> list[float]:
    """An equal-weighted index from member price series, rebased to 100.

    **Equal-weighted on purpose.** ``BreadthScope`` carries no weights for a
    sector — the F&O universe publishes none outside the two tracked indices —
    so the alternative to an equal weight is a made-up one. Each member is
    rebased to its own first period before averaging, which is what stops a
    4,000-rupee name from drowning out a 200-rupee one and makes the result a
    percentage move rather than a meaningless sum of prices.

    Members whose first price is zero or negative are dropped: there is nothing
    to rebase against, and including them at a nominal 100 would mute the
    sector's real move toward the flat line.
    """
    rebased: list[list[float]] = []
    for series in members:
        if not series:
            continue
        base = float(series[0])
        if base <= 0:
            continue
        rebased.append([float(value) / base * 100.0 for value in series])

    if not rebased:
        return []

    # Truncate to the shortest member rather than padding: a name that stopped
    # printing mid-window should shorten the composite, not flat-line it.
    span = min(len(series) for series in rebased)
    return [statistics.fmean([series[index] for series in rebased]) for index in range(span)]
