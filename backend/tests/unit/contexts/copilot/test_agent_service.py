"""The AI Console use case delegates to the agent and collects its stream.

A fake ``AgentPort`` stands in for the LangGraph adapter, pinning the two things
the use case owns: reporting availability, and turning the event stream into a
single collected answer.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from marketcompass.contexts.copilot.application.agent_service import AgentService
from marketcompass.contexts.copilot.application.ports import (
    AgentDone,
    AgentEvent,
    SkillsSelected,
    TextDelta,
    ToolFinished,
    ToolStarted,
    Turn,
)
from marketcompass.shared_kernel.types.identifiers import TenantId

TENANT = TenantId(uuid.uuid4())


class _FakeAgent:
    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.seen_question = ""
        self.seen_history: list[Turn] = []

    async def run(
        self,
        tenant_id: TenantId,
        symbol: str,
        question: str,
        history: list[Turn],
    ) -> AsyncIterator[AgentEvent]:
        _ = (tenant_id, symbol)
        self.seen_question = question
        self.seen_history = history
        yield SkillsSelected(titles=("OI & Options Flow",))
        yield ToolStarted(name="get_option_chain_summary", title="Reading the option chain")
        yield ToolFinished(name="get_option_chain_summary")
        yield TextDelta(text="NIFTY looks ")
        yield TextDelta(text="rangebound.")
        yield AgentDone(text="NIFTY looks rangebound.")


async def _collect(stream: AsyncIterator[AgentEvent]) -> list[AgentEvent]:
    return [event async for event in stream]


async def test_available_reflects_the_agent() -> None:
    assert AgentService(agent=_FakeAgent(available=True)).available is True
    assert AgentService(agent=_FakeAgent(available=False)).available is False


async def test_collects_stream_into_one_answer() -> None:
    service = AgentService(agent=_FakeAgent())

    answer = await service(TENANT, "NIFTY", "what's the call?")

    assert answer.text == "NIFTY looks rangebound."
    assert answer.symbol == "NIFTY"


async def test_stream_surfaces_skills_tools_then_tokens() -> None:
    service = AgentService(agent=_FakeAgent())

    events = await _collect(service.stream(TENANT, "NIFTY", "why?"))

    assert isinstance(events[0], SkillsSelected)
    assert any(isinstance(e, ToolStarted) for e in events)
    assert any(isinstance(e, TextDelta) for e in events)
    assert isinstance(events[-1], AgentDone)


async def test_history_is_passed_through() -> None:
    agent = _FakeAgent()
    service = AgentService(agent=agent)
    history = [Turn(role="user", text="hi"), Turn(role="assistant", text="Hello!")]

    await _collect(service.stream(TENANT, "NIFTY", "and the stop?", history))

    assert agent.seen_question == "and the stop?"
    assert agent.seen_history == history
