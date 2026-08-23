"""The Lesson value object — HUGIN's accumulating, weighted knowledge.

A ``Lesson`` is one distilled learning ("PCR velocity flip led the reversal my EMA
read missed"). It is keyed by ``dedup_key`` so re-observing the same pattern
upserts rather than duplicates, and it carries a hit/miss tally that later grades
accrue onto. The reflect step reads the top-K lessons by weight back into its
prompt, so a lesson that keeps proving true is consulted more; one that keeps
failing fades.

``reliability`` derives a 0..1 weight from the tally with a Laplace-smoothed
success rate, so a single lucky hit does not outrank a long track record.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Lesson:
    """One weighted learning, upserted per ``(tenant, dedup_key)``."""

    dedup_key: str
    text: str
    instrument: str | None = None
    hits: int = 0
    misses: int = 0
    last_seen_at: datetime | None = None

    @property
    def reliability(self) -> float:
        """Laplace-smoothed success rate in ``[0, 1]``.

        The +1/+2 smoothing starts a brand-new lesson at 0.5 and needs repeated
        confirmation to climb, so one lucky hit cannot outrank a proven lesson.
        """
        return (self.hits + 1) / (self.hits + self.misses + 2)
