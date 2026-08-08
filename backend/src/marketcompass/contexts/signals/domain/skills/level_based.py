"""Level-Based Trading skill — support/resistance and where price sits in it.

Builds the reference map every other panel draws — put wall and call wall from
the gamma profile, max pain, the gamma flip, and the nearest listed strikes —
then reads a directional lean from where spot sits inside that map: hugging
support leans bullish (a bounce), pressed against resistance leans bearish (a
rejection), mid-range says little.

``build_levels`` is separate from ``analyse`` because the trade scaffold and the
Risk-Management skill need the same levels; deriving them once keeps support and
resistance identical everywhere they appear.

Weight 1.5.
"""

from __future__ import annotations

from marketcompass.contexts.signals.domain.indicators import clamp
from marketcompass.contexts.signals.domain.inputs import MarketSnapshot
from marketcompass.contexts.signals.domain.models import Levels, SkillRead

WEIGHT = 1.5
_LABEL = "Level-Based Trading"
_SKILL = "level_based"

# How close (as a fraction of the support-resistance span) spot must sit to a
# level before it reads as "at" that level rather than mid-range.
_HUGGING = 0.25


def build_levels(snap: MarketSnapshot) -> Levels:
    """Nearest support below spot and resistance above, from the OI structure."""
    spot = snap.spot
    below: list[float] = []
    above: list[float] = []

    for level in (snap.put_wall, snap.call_wall, snap.gamma_flip, snap.max_pain):
        if level is None or level <= 0.0:
            continue
        if level < spot:
            below.append(level)
        elif level > spot:
            above.append(level)

    # Fall back to the nearest listed strike on a side with no OI level.
    for strike in snap.strikes:
        if strike < spot:
            below.append(strike)
        elif strike > spot:
            above.append(strike)

    support = max(below) if below else None
    resistance = min(above) if above else None
    return Levels(
        spot=spot,
        support=support,
        resistance=resistance,
        max_pain=snap.max_pain,
        gamma_flip=snap.gamma_flip,
        call_wall=snap.call_wall,
        put_wall=snap.put_wall,
    )


def analyse(snap: MarketSnapshot, levels: Levels) -> SkillRead:
    if levels.support is None or levels.resistance is None:
        return SkillRead(
            skill=_SKILL,
            label=_LABEL,
            weight=WEIGHT,
            score=None,
            headline="No bracketing levels around spot.",
            details=(),
        )

    dist_support = snap.spot - levels.support
    dist_resistance = levels.resistance - snap.spot
    span = dist_support + dist_resistance
    if span <= 0.0:
        return SkillRead(
            skill=_SKILL,
            label=_LABEL,
            weight=WEIGHT,
            score=None,
            headline="Levels collapsed onto spot.",
            details=(),
        )

    # Closer to support → bullish (bounce room up); closer to resistance →
    # bearish. Normalised so mid-range is ~0.
    score = clamp((dist_resistance - dist_support) / span)
    details = [
        f"Support {levels.support:,.0f} · resistance {levels.resistance:,.0f}.",
        _location_note(dist_support, dist_resistance, span),
    ]
    return SkillRead(
        skill=_SKILL,
        label=_LABEL,
        weight=WEIGHT,
        score=score,
        headline=_location_note(dist_support, dist_resistance, span),
        details=tuple(details),
    )


def _location_note(dist_support: float, dist_resistance: float, span: float) -> str:
    if dist_support / span < _HUGGING:
        return "Spot is hugging support — bounce setup."
    if dist_resistance / span < _HUGGING:
        return "Spot is pressed to resistance — rejection risk."
    return "Spot is mid-range between levels."
