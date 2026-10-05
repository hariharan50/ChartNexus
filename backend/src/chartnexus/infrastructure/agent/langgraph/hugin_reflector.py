"""LangGraph/Claude implementation of HUGIN's ``ReflectorPort``.

One structured-output call does both jobs — judge the prior expectation and
produce this hour's read + lessons — on the tenant owner's model
(``build_user_chat_model``). No tool loop and no streaming: HUGIN's snapshot is
pre-computed by the market reader and handed in as text, so this is a single
grounded reasoning pass with a strict output contract.

Deliberately separate from HELLA/STRYX adapters (the contexts stay isolated); the
only shared infra is the chat-model builder. The structured schema lives here in
the adapter — the domain owns the value objects, the adapter owns the LLM wire
shape and maps one to the other.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from chartnexus.contexts.hugin.domain import persona
from chartnexus.contexts.hugin.domain.cycle import ReflectInput, ReflectOutput
from chartnexus.contexts.hugin.domain.grade import GradeOutcome
from chartnexus.contexts.hugin.domain.lesson import Lesson
from chartnexus.contexts.hugin.domain.observation import Bias, Grade

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel


# --------------------------------------------------------------------------- #
# The LLM wire contract (what the model must return).
# --------------------------------------------------------------------------- #
class _Evidence(BaseModel):
    expected_move: str = Field(description="What the prior read expected to happen.")
    actual_move: str = Field(description="What the snapshot shows actually happened.")
    wall_status: str = Field(description="Whether the call/put wall held or broke, or n/a.")
    level_status: str = Field(
        description="Whether the key level was respected or violated, or n/a."
    )
    note: str = Field(default="", description="One-line rationale for the verdict.")


class _PriorGrade(BaseModel):
    grade: Literal["HIT", "PARTIAL", "MISS"]
    score: float = Field(ge=0.0, le=1.0, description="0..1; HIT trends high, MISS low.")
    evidence: _Evidence


class _NewLesson(BaseModel):
    dedup_key: str = Field(description="Short stable snake_case key so repeats fold together.")
    text: str = Field(description="The durable, reusable lesson in one sentence.")


class _ReflectSchema(BaseModel):
    bias: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    expectation: str = Field(description="A falsifiable next-hour claim about direction and level.")
    call_wall: float | None = Field(default=None)
    put_wall: float | None = Field(default=None)
    key_level: float | None = Field(default=None)
    new_lessons: list[_NewLesson] = Field(default_factory=list, max_length=3)
    confirmed_lessons: list[str] = Field(
        default_factory=list, description="dedup_keys of existing lessons this outcome confirmed."
    )
    refuted_lessons: list[str] = Field(
        default_factory=list, description="dedup_keys of existing lessons this outcome refuted."
    )
    prior_grade: _PriorGrade | None = Field(
        default=None, description="Omit entirely when there is no prior read to judge."
    )


class HuginReflector:
    """A ``ReflectorPort`` backed by a structured Claude call."""

    def __init__(self, model: BaseChatModel) -> None:
        self._model = model

    @property
    def available(self) -> bool:
        return True

    async def reflect(self, request: ReflectInput) -> ReflectOutput:
        structured = self._model.with_structured_output(_ReflectSchema)
        messages = [
            ("system", persona.compose_reflection_system()),
            ("human", persona.compose_reflection_user(request)),
        ]
        result = await structured.ainvoke(messages)
        if not isinstance(result, _ReflectSchema):  # pragma: no cover - defensive
            raise RuntimeError("HUGIN reflector returned an unexpected shape")
        return self._to_output(result, request)

    def _to_output(self, result: _ReflectSchema, request: ReflectInput) -> ReflectOutput:
        existing = {lesson.dedup_key: lesson for lesson in request.lessons}

        lessons: list[Lesson] = [
            Lesson(dedup_key=item.dedup_key, text=item.text, instrument=request.instrument)
            for item in result.new_lessons
        ]
        # Confirmed/refuted existing lessons accrue a hit/miss so reliability moves;
        # unknown keys (a model slip) are ignored.
        for key in result.confirmed_lessons:
            prior = existing.get(key)
            if prior is not None:
                lessons.append(
                    Lesson(dedup_key=key, text=prior.text, instrument=prior.instrument, hits=1)
                )
        for key in result.refuted_lessons:
            prior = existing.get(key)
            if prior is not None:
                lessons.append(
                    Lesson(dedup_key=key, text=prior.text, instrument=prior.instrument, misses=1)
                )

        # A grade only counts when there was actually a prior read to judge.
        prior_grade: GradeOutcome | None = None
        if request.prior is not None and result.prior_grade is not None:
            prior_grade = GradeOutcome(
                grade=Grade(result.prior_grade.grade),
                score=Decimal(str(result.prior_grade.score)),
                evidence=result.prior_grade.evidence.model_dump(),
            )

        return ReflectOutput(
            bias=Bias(result.bias),
            expectation=result.expectation,
            call_wall=_dec(result.call_wall),
            put_wall=_dec(result.put_wall),
            key_level=_dec(result.key_level),
            lessons=tuple(lessons),
            prior_grade=prior_grade,
        )


def _dec(value: float | None) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None
