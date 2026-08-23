"""LangGraph/Claude implementation of HUGIN's ``CallGeneratorPort``.

One structured-output call turns HUGIN's memory digest into a two-part call: an
analytical read (bias + target zone + conviction) and a trade structure
(entry/stop/targets). Memory-grounded — the digest is the only context; no tools.
The caller stamps HUGIN's measured hit-rate onto the result so conviction reads
honestly. Mirrors ``hugin_reflector.py``'s structured-output shape.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from marketcompass.contexts.hugin.domain import persona
from marketcompass.contexts.hugin.domain.call import HuginCall
from marketcompass.contexts.hugin.domain.observation import Bias

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel


class _CallSchema(BaseModel):
    bias: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    target_zone: str = Field(description="The level zone the read targets, e.g. '23,600-23,650'.")
    conviction: float = Field(
        ge=0.0, le=1.0, description="0..1; honest about setup + track record."
    )
    rationale: str = Field(description="Grounded in specific reads and lessons from memory.")
    entry: str | None = Field(default=None, description="Entry price or zone.")
    stop: str | None = Field(default=None, description="Stop price or zone.")
    target1: str | None = Field(default=None)
    target2: str | None = Field(default=None)


class HuginCaller:
    def __init__(self, model: BaseChatModel) -> None:
        self._model = model

    @property
    def available(self) -> bool:
        return True

    async def generate(
        self, digest: str, instrument: str, track_hit_rate: Decimal | None
    ) -> HuginCall:
        structured = self._model.with_structured_output(_CallSchema)
        messages = [
            ("system", persona.compose_call_system()),
            ("human", f"{digest}\n\nGive your call for {instrument} now."),
        ]
        result = await structured.ainvoke(messages)
        if not isinstance(result, _CallSchema):  # pragma: no cover - defensive
            raise RuntimeError("HUGIN caller returned an unexpected shape")

        return HuginCall(
            instrument=instrument,
            bias=Bias(result.bias),
            target_zone=result.target_zone,
            conviction=Decimal(str(result.conviction)),
            track_hit_rate=track_hit_rate,
            rationale=result.rationale,
            entry=result.entry,
            stop=result.stop,
            target1=result.target1,
            target2=result.target2,
        )
