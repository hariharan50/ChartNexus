"""The weighted vote — the math a wrong call would hide in.

Pins the three things easy to get quietly wrong: a missing skill drops from the
denominator instead of voting neutral, confidence is scaled by how much weight
actually voted, and an empty book is HOLD-at-zero rather than a coin flip.
"""

from __future__ import annotations

from chartnexus.contexts.signals.domain.fusion import fuse
from chartnexus.contexts.signals.domain.models import Decision, SkillRead


def _read(skill: str, weight: float, score: float | None) -> SkillRead:
    return SkillRead(skill=skill, label=skill, weight=weight, score=score, headline="")


def test_all_bullish_is_a_confident_buy() -> None:
    result = fuse(
        [
            _read("oi", 3.0, 0.8),
            _read("price", 2.0, 0.6),
            _read("level", 1.5, 0.7),
        ]
    )
    assert result.decision is Decision.BUY
    assert result.score > 0.6
    # All weight voted, so confidence tracks the raw score closely.
    assert result.confidence >= 70


def test_all_bearish_is_a_sell() -> None:
    result = fuse([_read("oi", 3.0, -0.5), _read("price", 2.0, -0.4)])
    assert result.decision is Decision.SELL
    assert result.score < 0


def test_mixed_within_band_holds() -> None:
    result = fuse([_read("oi", 3.0, 0.3), _read("price", 2.0, -0.4)])
    assert result.decision is Decision.HOLD


def test_missing_skill_drops_out_and_shrinks_confidence() -> None:
    full = fuse([_read("oi", 3.0, 0.9), _read("price", 2.0, 0.9), _read("level", 1.5, 0.9)])
    partial = fuse([_read("oi", 3.0, 0.9), _read("price", 2.0, None), _read("level", 1.5, None)])

    # Same directional score, but the partial vote rested on less weight.
    assert partial.score == full.score
    assert partial.confidence < full.confidence
    assert partial.weight_used == 3.0
    assert full.weight_used == 6.5


def test_no_data_is_hold_at_zero() -> None:
    result = fuse([_read("oi", 3.0, None), _read("price", 2.0, None)])
    assert result.decision is Decision.HOLD
    assert result.confidence == 0
    assert result.score == 0.0


def test_non_voting_skill_is_ignored() -> None:
    # A weight-0 skill (Risk Management) never moves the vote even with a score.
    result = fuse([_read("oi", 3.0, 0.5), _read("risk", 0.0, 1.0)])
    assert result.weight_used == 3.0
