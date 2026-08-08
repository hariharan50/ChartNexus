"""Answer a free-form question about the current setup, grounded in the guidance.

Always computes a deterministic, rule-based answer from the structured snapshot
first — that alone makes the AI Console work with no API key. When a generative
provider is configured, it rewrites/expands that answer, given the same structured
state plus the deterministic facts as a guardrail it must not contradict.
"""

from __future__ import annotations

from dataclasses import dataclass

from marketcompass.contexts.copilot.application.ports import (
    GuidancePort,
    LLMMessage,
    LLMPort,
)
from marketcompass.contexts.copilot.domain import answerer, prompt
from marketcompass.contexts.copilot.domain.models import GuidanceSnapshot
from marketcompass.shared_kernel.types.identifiers import TenantId


@dataclass(frozen=True, slots=True)
class Answer:
    text: str
    symbol: str
    decision: str
    provenance: str
    source: str  # which provider produced the text: "rule_based" / "anthropic" / ...


class Converse:
    def __init__(self, *, guidance: GuidancePort, llm: LLMPort) -> None:
        self._guidance = guidance
        self._llm = llm

    async def __call__(self, tenant_id: TenantId, symbol: str, question: str) -> Answer:
        snapshot = await self._guidance.current(tenant_id, symbol)
        facts = answerer.answer(snapshot, question)

        if not self._llm.is_generative:
            return _answer(facts, snapshot, source=self._llm.name)

        user = (
            f"{prompt.context_block(snapshot)}\n\n"
            f"User question: {question}\n\n"
            "Grounded facts you must not contradict:\n"
            f"{facts}"
        )
        response = await self._llm.complete(
            system=prompt.system_prompt(), messages=[LLMMessage(role="user", content=user)]
        )
        text = response.text.strip() or facts
        return _answer(text, snapshot, source=self._llm.name)


def _answer(text: str, snapshot: GuidanceSnapshot, *, source: str) -> Answer:
    return Answer(
        text=text,
        symbol=snapshot.symbol,
        decision=snapshot.decision,
        provenance=snapshot.provenance,
        source=source,
    )
