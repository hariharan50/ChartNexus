"""The grade contract — how last hour's expectation is judged.

HUGIN's evaluation is LLM-judged (the tenant owner's model), not a deterministic
scorer. To stay trustworthy despite self-grading, the judgment is *grounded*: the
model is handed the prior expectation and this hour's real snapshot and must return
its verdict together with the numeric ``evidence`` it rested on (expected vs actual
move, whether the walls held, whether the level was respected). That evidence is
persisted so any HIT/MISS can be audited after the fact.

This module holds only the value object — no scoring logic lives here; the reflect
adapter fills it in.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from marketcompass.contexts.hugin.domain.observation import Grade


@dataclass(frozen=True, slots=True)
class GradeOutcome:
    """A grounded verdict on a prior observation's expectation."""

    grade: Grade
    #: A normalised 0..1 score; HIT trends high, MISS low. Kept numeric so the
    #: scoreboard and any later backtest have a continuous signal, not just a label.
    score: Decimal
    #: The cited actual-vs-expected numbers behind the verdict, for audit.
    evidence: dict[str, Any]
