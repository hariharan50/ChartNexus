"""The weighted vote — where the directional skills become one call.

A straight extension of the legacy synthesizer (see
``docupdateimp/CALCULATIONS_ARCHITECTURE.md`` §4.3), minus the FII and news legs:
a weight-averaged score over the skills that had data, banded into BUY / SELL /
HOLD, with a confidence that is deliberately penalised when the vote rested on
only some of the skills.
"""

from __future__ import annotations

from dataclasses import dataclass

from marketcompass.contexts.signals.domain.models import Decision, SkillRead

# The full directional weight on the table, whether or not every skill had data.
# Confidence is scaled by how much of this actually voted, so a strong score
# built from one skill reports less certainty than the same score from three.
_TOTAL_DIRECTIONAL_WEIGHT = 6.5  # 3.0 OI + 2.0 price + 1.5 levels

# Starting bands (the design doc flags these for calibration, not as final).
_BUY_ABOVE = 0.20
_SELL_BELOW = -0.20


@dataclass(frozen=True, slots=True)
class FusionResult:
    decision: Decision
    score: float
    confidence: int
    weight_used: float
    weight_total: float


def fuse(reads: list[SkillRead] | tuple[SkillRead, ...]) -> FusionResult:
    """Combine the directional reads into a decision, score and confidence."""
    voting = [read for read in reads if read.votes]
    weight_used = sum(read.weight for read in voting)

    if not voting or weight_used <= 0.0:
        # Nothing voted — HOLD at zero confidence is the honest answer, not a
        # coin-flip dressed as neutral.
        return FusionResult(
            decision=Decision.HOLD,
            score=0.0,
            confidence=0,
            weight_used=0.0,
            weight_total=_TOTAL_DIRECTIONAL_WEIGHT,
        )

    score = sum(read.weight * (read.score or 0.0) for read in voting) / weight_used
    decision = _band(score)
    coverage = weight_used / _TOTAL_DIRECTIONAL_WEIGHT
    confidence = min(100, round(abs(score) * 100.0 * coverage))

    return FusionResult(
        decision=decision,
        score=round(score, 4),
        confidence=confidence,
        weight_used=weight_used,
        weight_total=_TOTAL_DIRECTIONAL_WEIGHT,
    )


def _band(score: float) -> Decision:
    if score > _BUY_ABOVE:
        return Decision.BUY
    if score < _SELL_BELOW:
        return Decision.SELL
    return Decision.HOLD
