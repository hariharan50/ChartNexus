"""The HuginCall value object — a memory-driven, actionable call.

Two parts, per the owner's spec: an *analytical* read (bias + target zone +
conviction) and a concrete *trade structure* (entry/stop/targets). Conviction is
kept honest by carrying HUGIN's own measured track record alongside the model's
stated confidence — the UI shows both, so a confident model with a weak record
reads as such. Grade fields are reserved for a later auto-grading phase.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from chartnexus.contexts.hugin.domain.observation import Bias


@dataclass(frozen=True, slots=True)
class HuginCall:
    instrument: str
    bias: Bias
    target_zone: str
    #: The model's stated confidence, 0..1.
    conviction: Decimal
    #: HUGIN's measured hit-rate at the time of the call (its honesty anchor), or
    #: ``None`` when there is no graded history yet.
    track_hit_rate: Decimal | None
    rationale: str
    entry: str | None = None
    stop: str | None = None
    target1: str | None = None
    target2: str | None = None
    # Present once persisted/read back.
    id: Any | None = None
    created_at: datetime | None = None
