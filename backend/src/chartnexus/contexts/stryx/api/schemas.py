"""Wire contract for the STRYX endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from chartnexus.contexts.stryx.application.ports import JournalEntry
from chartnexus.contexts.stryx.application.stryx_service import Answer
from chartnexus.contexts.stryx.domain.discipline import MAX_LIVE_CALLS_PER_DAY


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AskRequest(_Schema):
    question: str = Field(min_length=1, max_length=500)
    #: The conversation to continue. Absent on the first message — the server
    #: mints one and returns it on the stream so follow-ups carry context.
    session_id: str | None = Field(default=None, max_length=64)


class AskResponse(_Schema):
    answer: str
    symbol: str

    @classmethod
    def of(cls, answer: Answer) -> AskResponse:
        return cls(answer=answer.text, symbol=answer.symbol)


class AvailabilityResponse(_Schema):
    #: False when no model is configured — the STRYX tab shows a notice instead of
    #: the chat. STRYX is LLM-only; there is no keyless fallback.
    available: bool


class JournalCall(_Schema):
    created_at: str
    instrument: str | None
    entry_style: str | None
    status: str
    entry: str | None
    stop: str | None
    target1: str | None
    target2: str | None
    confidence: str | None
    reasoning: str | None

    @classmethod
    def of(cls, entry: JournalEntry) -> JournalCall:
        return cls(
            created_at=entry.created_at.isoformat(),
            instrument=entry.instrument,
            entry_style=entry.entry_style,
            status=entry.status,
            entry=entry.entry,
            stop=entry.stop,
            target1=entry.target1,
            target2=entry.target2,
            confidence=entry.confidence,
            reasoning=entry.reasoning,
        )


class JournalTodayResponse(_Schema):
    #: LIVE calls issued today, the daily cap, and how many LIVE calls remain —
    #: drives the "calls left today" chip in the UI.
    live_count: int
    cap: int = MAX_LIVE_CALLS_PER_DAY
    remaining: int
    calls: tuple[JournalCall, ...]

    @classmethod
    def of(cls, entries: tuple[JournalEntry, ...]) -> JournalTodayResponse:
        live = sum(1 for e in entries if e.status == "LIVE")
        return cls(
            live_count=live,
            remaining=max(0, MAX_LIVE_CALLS_PER_DAY - live),
            calls=tuple(JournalCall.of(e) for e in entries),
        )
