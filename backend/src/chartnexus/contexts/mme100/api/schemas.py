"""Wire contract for the MME100 endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from chartnexus.contexts.mme100.application.mme100_service import Answer
from chartnexus.contexts.mme100.application.ports import Briefing


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
    #: False when no model is configured — the MME100 tab shows a notice instead of
    #: the chat. MME100 is LLM-only; there is no keyless fallback.
    available: bool


class EnrollmentResponse(_Schema):
    #: Whether this tenant has opted the autonomous pre-market briefing on. Off by
    #: default: it spends the owner's LLM tokens each morning.
    enabled: bool


class SetEnrollmentRequest(_Schema):
    enabled: bool


class BriefingResponse(_Schema):
    trading_day: str
    instruments: tuple[str, ...]
    markdown: str
    source: str
    created_at: str | None

    @classmethod
    def of(cls, briefing: Briefing) -> BriefingResponse:
        return cls(
            trading_day=briefing.trading_day.isoformat(),
            instruments=briefing.instruments,
            markdown=briefing.markdown,
            source=briefing.source,
            created_at=briefing.created_at.isoformat() if briefing.created_at else None,
        )
