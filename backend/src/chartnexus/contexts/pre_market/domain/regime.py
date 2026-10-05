"""The market-regime read: six axes, every input visible.

Built the way ``GapPressureGauge`` is built rather than the way a signal is
built, and the difference is the point. This does not emit BUY or SELL. It
emits six independent readings — trend, momentum, volatility, participation,
global, derivatives — each with the raw number that produced it, and a
composite that can always be decomposed back into them.

**Why every factor carries its ``reading``.** A composite whose inputs cannot
be inspected is a horoscope with a decimal point (GIA's gauge says the same
thing about itself, for the same reason). If the score says 68 and a reader
cannot see that it got there on a strong EMA stack and a weak breadth, the
number is worth nothing to them and they cannot disagree with it.

**Why ``inputs_present`` is on the result.** A score built from four of eleven
factors is a different claim from one built from all eleven, and rendering them
identically is the quiet way a screener lies. The confidence is derived from
coverage, not from conviction.

**Why the weights are unfitted, and said so.** They are judgement, not a
regression. The disclaimer the page carries is not boilerplate — it is
accurate, and this module is why.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

#: The neutral start. Every factor moves the score off this, so a page with no
#: inputs at all reads as "no opinion" rather than as bearish.
_START = 50.0

#: Coverage below this and the score is presented as indicative only.
_THIN_COVERAGE = 0.5

#: Band edges, symmetric about the neutral 50. Named so the bands can be
#: retuned in one place rather than hunted through a chain of comparisons.
_STRONGLY_BEARISH_AT = 25.0
_BEARISH_AT = 42.0
_BULLISH_AT = 58.0
_STRONGLY_BULLISH_AT = 75.0


class Stance(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class RegimeBand(StrEnum):
    STRONGLY_BEARISH = "strongly_bearish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    BULLISH = "bullish"
    STRONGLY_BULLISH = "strongly_bullish"


class Axis(StrEnum):
    """The six independent reads the scorecard is made of."""

    TREND = "trend"
    MOMENTUM = "momentum"
    VOLATILITY = "volatility"
    BREADTH = "breadth"
    GLOBAL = "global"
    DERIVATIVES = "derivatives"


AXIS_LABELS: dict[Axis, str] = {
    Axis.TREND: "Trend",
    Axis.MOMENTUM: "Momentum",
    Axis.VOLATILITY: "Volatility",
    Axis.BREADTH: "Breadth",
    Axis.GLOBAL: "Global",
    Axis.DERIVATIVES: "Derivatives",
}


@dataclass(frozen=True, slots=True)
class Factor:
    """One input, its weight, and the number it was read from."""

    key: str
    label: str
    axis: Axis
    stance: Stance
    #: Signed contribution to the composite, already weighted.
    points: float
    #: The raw input, formatted for display. Non-negotiable: without it the
    #: score cannot be argued with.
    reading: str
    note: str | None = None


@dataclass(frozen=True, slots=True)
class AxisRead:
    """One axis's own verdict, independent of the composite."""

    axis: Axis
    label: str
    stance: Stance
    points: float
    factors: tuple[Factor, ...]

    @property
    def resolved(self) -> bool:
        return bool(self.factors)


@dataclass(frozen=True, slots=True)
class Regime:
    """The composite, and everything that produced it."""

    score: float
    band: RegimeBand
    axes: tuple[AxisRead, ...]
    factors: tuple[Factor, ...]
    inputs_present: int
    inputs_total: int

    @property
    def coverage(self) -> float:
        """0-1. How much of the intended input set actually answered."""
        if self.inputs_total <= 0:
            return 0.0
        return self.inputs_present / self.inputs_total

    @property
    def confidence(self) -> str:
        """Derived from coverage alone — never from how extreme the score is.

        A lopsided score off three inputs is not a confident reading, it is a
        thin one, and the two must not be allowed to look alike.
        """
        if self.coverage >= _THIN_COVERAGE * 1.6:
            return "high"
        if self.coverage >= _THIN_COVERAGE:
            return "moderate"
        return "thin"


def _stance_of(points: float) -> Stance:
    if points > 0:
        return Stance.BULLISH
    if points < 0:
        return Stance.BEARISH
    return Stance.NEUTRAL


def band_of(score: float) -> RegimeBand:
    """Five bands, symmetric about the neutral 50."""
    if score <= _STRONGLY_BEARISH_AT:
        return RegimeBand.STRONGLY_BEARISH
    if score <= _BEARISH_AT:
        return RegimeBand.BEARISH
    if score >= _STRONGLY_BULLISH_AT:
        return RegimeBand.STRONGLY_BULLISH
    if score >= _BULLISH_AT:
        return RegimeBand.BULLISH
    return RegimeBand.NEUTRAL


def compose(factors: tuple[Factor, ...], *, expected: int) -> Regime:
    """Roll resolved factors into a 0-100 composite and its six axes.

    ``expected`` is how many factors the caller *tried* to build, not how many
    it managed — the difference is what ``inputs_present`` reports, and the
    caller is the only one that knows it.
    """
    total = _START + sum(factor.points for factor in factors)
    score = max(0.0, min(100.0, total))

    axes: list[AxisRead] = []
    for axis in Axis:
        members = tuple(factor for factor in factors if factor.axis is axis)
        points = sum(factor.points for factor in members)
        axes.append(
            AxisRead(
                axis=axis,
                label=AXIS_LABELS[axis],
                stance=_stance_of(points) if members else Stance.NEUTRAL,
                points=points,
                factors=members,
            )
        )

    # Loudest first: the scorecard should lead with whatever actually drove the
    # number, not with whichever axis happens to sort first.
    ordered = tuple(sorted(factors, key=lambda item: abs(item.points), reverse=True))

    return Regime(
        score=score,
        band=band_of(score),
        axes=tuple(axes),
        factors=ordered,
        inputs_present=len(factors),
        inputs_total=max(expected, len(factors)),
    )


def factor(
    key: str,
    label: str,
    axis: Axis,
    *,
    points: float,
    reading: str,
    note: str | None = None,
) -> Factor:
    """Build one factor, with its stance derived from its own sign."""
    return Factor(
        key=key,
        label=label,
        axis=axis,
        stance=_stance_of(points),
        points=points,
        reading=reading,
        note=note,
    )
