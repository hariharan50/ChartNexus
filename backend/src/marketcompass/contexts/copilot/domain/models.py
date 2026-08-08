"""The structured guidance copilot reasons and answers over.

A copilot-owned view of a signals decision — copilot never imports ``signals``,
so an infrastructure bridge translates the signals ``Guidance`` into this shape.
Pure value objects, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SkillSnapshot:
    label: str
    score: float | None
    headline: str


@dataclass(frozen=True, slots=True)
class GuidanceSnapshot:
    symbol: str
    decision: str
    confidence: int
    provenance: str
    is_actionable: bool
    rationale: str
    skills: tuple[SkillSnapshot, ...]
    support: float | None
    resistance: float | None
    entry: float | None
    stop: float | None
    target: float | None
    suggested_contract: str | None
    warnings: tuple[str, ...] = field(default_factory=tuple)
