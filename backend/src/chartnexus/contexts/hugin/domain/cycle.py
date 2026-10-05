"""Value objects binding one tick together.

``ReflectInput`` / ``ReflectOutput`` are the contract for the single LLM call that
both judges the prior read and produces this hour's read + lessons. ``CycleResult``
is what one ``RunHuginCycle`` invocation reports back to the worker.

Pure: no I/O, no framework. The reflect adapter and the use case exchange these.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from chartnexus.contexts.hugin.domain.grade import GradeOutcome
from chartnexus.contexts.hugin.domain.lesson import Lesson
from chartnexus.contexts.hugin.domain.observation import Bias, Observation


@dataclass(frozen=True, slots=True)
class ReflectInput:
    """Everything the single LLM call needs: the read to judge and the read to make."""

    instrument: str
    snapshot: dict[str, Any]
    #: The most recent observation, whose expectation is now judged. ``None`` on
    #: the day's first tick (nothing prior to grade).
    prior: Observation | None
    #: The top lessons, fed back so the read is sharpened by what HUGIN has learned.
    lessons: tuple[Lesson, ...]


@dataclass(frozen=True, slots=True)
class ReflectOutput:
    """The combined result: a grade for the prior read, this hour's read, lessons."""

    bias: Bias
    expectation: str
    call_wall: Decimal | None
    put_wall: Decimal | None
    key_level: Decimal | None
    lessons: tuple[Lesson, ...]
    #: ``None`` when there was no prior observation to grade.
    prior_grade: GradeOutcome | None


class CycleStatus(StrEnum):
    PERSISTED = "PERSISTED"
    SKIPPED_UNAVAILABLE = "SKIPPED_UNAVAILABLE"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class CycleResult:
    """What one tenant x instrument cycle produced."""

    status: CycleStatus
    observation: Observation | None = None
    graded_prior: bool = False
