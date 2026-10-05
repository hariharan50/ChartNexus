"""Wire contract for the HUGIN read endpoints."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from chartnexus.contexts.hugin.application.ports import (
    DayView,
    HistoryView,
    LessonView,
    MemoryView,
    ObservationView,
)
from chartnexus.contexts.hugin.domain.call import HuginCall


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _num(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


class AskRequest(_Schema):
    question: str = Field(min_length=1, max_length=500)
    #: The conversation to continue. Absent on the first message — the server mints
    #: one and returns it on the stream so follow-ups carry context.
    session_id: str | None = Field(default=None, max_length=64)


class AvailabilityResponse(_Schema):
    #: False when the caller has no LLM key configured — the HUGIN tab shows a
    #: notice instead of the memory panels. HUGIN produces memory only for tenants
    #: whose owner has a key.
    available: bool


class EnrollmentResponse(_Schema):
    #: Whether this tenant has opted HUGIN on. Off by default: HUGIN spends the
    #: owner's LLM tokens hourly, so it runs only when explicitly enabled.
    enabled: bool


class SetEnrollmentRequest(_Schema):
    enabled: bool


class ObservationResponse(_Schema):
    tick_at: str
    instrument: str
    bias: str
    expectation: str
    call_wall: float | None
    put_wall: float | None
    key_level: float | None
    grade: str | None
    score: float | None
    grade_evidence: dict[str, Any] | None

    @classmethod
    def of(cls, view: ObservationView) -> ObservationResponse:
        return cls(
            tick_at=view.tick_at.isoformat(),
            instrument=view.instrument,
            bias=view.bias,
            expectation=view.expectation,
            call_wall=_num(view.call_wall),
            put_wall=_num(view.put_wall),
            key_level=_num(view.key_level),
            grade=view.grade,
            score=_num(view.score),
            grade_evidence=view.grade_evidence,
        )


class LessonResponse(_Schema):
    text: str
    instrument: str | None
    hits: int
    misses: int
    reliability: float
    last_seen_at: str | None

    @classmethod
    def of(cls, view: LessonView) -> LessonResponse:
        return cls(
            text=view.text,
            instrument=view.instrument,
            hits=view.hits,
            misses=view.misses,
            reliability=view.reliability,
            last_seen_at=view.last_seen_at.isoformat() if view.last_seen_at is not None else None,
        )


class MemoryTodayResponse(_Schema):
    instrument: str
    observations: tuple[ObservationResponse, ...]
    lessons: tuple[LessonResponse, ...]
    #: Fraction of graded reads today that hit, or null when nothing is graded yet.
    hit_rate: float | None
    graded_count: int
    hit_count: int

    @classmethod
    def of(cls, view: MemoryView) -> MemoryTodayResponse:
        return cls(
            instrument=view.instrument,
            observations=tuple(ObservationResponse.of(o) for o in view.observations),
            lessons=tuple(LessonResponse.of(lsn) for lsn in view.lessons),
            hit_rate=view.hit_rate,
            graded_count=view.graded_count,
            hit_count=view.hit_count,
        )


class LessonsResponse(_Schema):
    lessons: tuple[LessonResponse, ...]

    @classmethod
    def of(cls, views: tuple[LessonView, ...]) -> LessonsResponse:
        return cls(lessons=tuple(LessonResponse.of(v) for v in views))


class DayResponse(_Schema):
    trading_day: str
    observations: tuple[ObservationResponse, ...]
    hit_rate: float | None
    graded_count: int
    hit_count: int

    @classmethod
    def of(cls, view: DayView) -> DayResponse:
        return cls(
            trading_day=view.trading_day.isoformat(),
            observations=tuple(ObservationResponse.of(o) for o in view.observations),
            hit_rate=view.hit_rate,
            graded_count=view.graded_count,
            hit_count=view.hit_count,
        )


class CallResponse(_Schema):
    created_at: str | None
    instrument: str
    bias: str
    target_zone: str
    conviction: float
    track_hit_rate: float | None
    rationale: str
    entry: str | None
    stop: str | None
    target1: str | None
    target2: str | None

    @classmethod
    def of(cls, call: HuginCall) -> CallResponse:
        return cls(
            created_at=call.created_at.isoformat() if call.created_at is not None else None,
            instrument=call.instrument,
            bias=call.bias.value,
            target_zone=call.target_zone,
            conviction=float(call.conviction),
            track_hit_rate=float(call.track_hit_rate) if call.track_hit_rate is not None else None,
            rationale=call.rationale,
            entry=call.entry,
            stop=call.stop,
            target1=call.target1,
            target2=call.target2,
        )


class CallsResponse(_Schema):
    calls: tuple[CallResponse, ...]

    @classmethod
    def of(cls, calls: tuple[HuginCall, ...]) -> CallsResponse:
        return cls(calls=tuple(CallResponse.of(c) for c in calls))


class HistoryResponse(_Schema):
    instrument: str
    days: tuple[DayResponse, ...]
    overall_hit_rate: float | None
    overall_graded: int
    overall_hits: int

    @classmethod
    def of(cls, view: HistoryView) -> HistoryResponse:
        return cls(
            instrument=view.instrument,
            days=tuple(DayResponse.of(d) for d in view.days),
            overall_hit_rate=view.overall_hit_rate,
            overall_graded=view.overall_graded,
            overall_hits=view.overall_hits,
        )
