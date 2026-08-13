"""Wire contract for the AI Console endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from marketcompass.contexts.copilot.application.agent_service import Answer


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
    #: False when no model is configured — the console tab shows a notice instead
    #: of the chat. The AI Console is LLM-only; there is no keyless fallback.
    available: bool
