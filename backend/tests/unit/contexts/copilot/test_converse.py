"""The copilot conversation layer: grounded answers with and without an LLM.

Fakes stand in for the guidance bridge and the LLM provider, pinning the two
paths the design turns on: with no generative model, the deterministic answerer
is the answer; with one, its output is used but the deterministic facts are
handed over as a guardrail.
"""

from __future__ import annotations

import uuid

from marketcompass.contexts.copilot.application.converse import Converse
from marketcompass.contexts.copilot.application.ports import LLMMessage, LLMResponse
from marketcompass.contexts.copilot.domain.models import GuidanceSnapshot, SkillSnapshot
from marketcompass.shared_kernel.types.identifiers import TenantId

TENANT = TenantId(uuid.uuid4())


def _snapshot(provenance: str = "live", actionable: bool = True) -> GuidanceSnapshot:
    return GuidanceSnapshot(
        symbol="NIFTY",
        decision="BUY",
        confidence=72,
        provenance=provenance,
        is_actionable=actionable,
        rationale="NIFTY leans bullish (72% confidence).",
        skills=(
            SkillSnapshot(label="OI Analysis", score=0.47, headline="PCR put-heavy."),
            SkillSnapshot(label="Risk Management", score=None, headline="stop 24,800 · R:R 1.8"),
        ),
        support=24_800.0,
        resistance=25_000.0,
        entry=24_850.0,
        stop=24_800.0,
        target=25_000.0,
        suggested_contract="NIFTY 24800CE (nearest ATM, illustrative)",
    )


class _FakeGuidance:
    def __init__(self, snapshot: GuidanceSnapshot) -> None:
        self._snapshot = snapshot

    async def current(self, tenant_id: TenantId, symbol: str) -> GuidanceSnapshot:
        return self._snapshot


class _RuleBased:
    name = "rule_based"
    is_generative = False

    async def complete(self, *, system: str, messages: list[LLMMessage]) -> LLMResponse:
        raise AssertionError("rule-based provider must not be asked to complete")


class _CapturingLLM:
    name = "anthropic"
    is_generative = True

    def __init__(self) -> None:
        self.system = ""
        self.user = ""

    async def complete(self, *, system: str, messages: list[LLMMessage]) -> LLMResponse:
        self.system = system
        self.user = messages[-1].content
        return LLMResponse(text="Buy bias — dealers pinned above spot.", provider=self.name)


async def test_keyless_uses_deterministic_answer_with_disclaimer() -> None:
    converse = Converse(guidance=_FakeGuidance(_snapshot()), llm=_RuleBased())

    answer = await converse(TENANT, "NIFTY", "where is my stop?")

    assert "24,800" in answer.text
    assert "not investment advice" in answer.text.lower()
    assert answer.source == "rule_based"
    assert answer.decision == "BUY"


async def test_generative_llm_is_grounded_in_the_facts() -> None:
    llm = _CapturingLLM()
    converse = Converse(guidance=_FakeGuidance(_snapshot()), llm=llm)

    answer = await converse(TENANT, "NIFTY", "why buy here?")

    assert answer.text == "Buy bias — dealers pinned above spot."
    assert answer.source == "anthropic"
    # The model was handed the structured state and the deterministic facts.
    assert "Call: BUY at 72% confidence" in llm.user
    assert "Grounded facts you must not contradict" in llm.user


async def test_keyless_answers_identity_not_the_market_summary() -> None:
    converse = Converse(guidance=_FakeGuidance(_snapshot()), llm=_RuleBased())

    answer = await converse(TENANT, "NIFTY", "hi what's your name?")

    # She introduces herself and does NOT fall through to the trading disclaimer.
    assert "hella" in answer.text.lower()
    assert "confidence" not in answer.text.lower()
    assert "investment advice" not in answer.text.lower()


async def test_mock_provenance_is_flagged_in_the_answer() -> None:
    converse = Converse(
        guidance=_FakeGuidance(_snapshot(provenance="mock", actionable=False)),
        llm=_RuleBased(),
    )

    answer = await converse(TENANT, "NIFTY", "what's the call?")

    assert "simulated" in answer.text.lower()
    assert answer.provenance == "mock"
