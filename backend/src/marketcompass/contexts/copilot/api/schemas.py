"""Wire contract for the copilot chat endpoint."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from marketcompass.contexts.copilot.application.converse import Answer


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AskRequest(_Schema):
    question: str = Field(min_length=1, max_length=500)


class AskResponse(_Schema):
    answer: str
    symbol: str
    decision: str
    provenance: str
    #: Which provider produced the text — "rule_based" when keyless, else the LLM.
    source: str

    @classmethod
    def of(cls, answer: Answer) -> AskResponse:
        return cls(
            answer=answer.text,
            symbol=answer.symbol,
            decision=answer.decision,
            provenance=answer.provenance,
            source=answer.source,
        )
