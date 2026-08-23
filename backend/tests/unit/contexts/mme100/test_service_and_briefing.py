"""MME100's chat service and the pre-market briefing use case, over fakes.

Fakes stand in for the LangGraph adapter and the Postgres briefing store, pinning
what the use cases own: the service just relays the stream and assembles the final
answer; the briefing runs the agent once per instrument, stitches the markdown, and
persists one briefing (skipping entirely when the agent is unavailable).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

from marketcompass.contexts.mme100.application.mme100_service import Mme100Service
from marketcompass.contexts.mme100.application.ports import (
    AgentDone,
    AgentEvent,
    Briefing,
    SkillsConsidered,
    TextDelta,
    Turn,
)
from marketcompass.contexts.mme100.application.run_briefing import RunMme100Briefing
from marketcompass.shared_kernel.types.identifiers import TenantId

TENANT = TenantId(uuid.uuid4())
TICK = datetime(2026, 8, 24, 3, 0, tzinfo=UTC)  # 08:30 IST Monday


class _FakeAgent:
    def __init__(self, *, answer: str = "NIFTY looks constructive.", available: bool = True) -> None:
        self.available = available
        self._answer = answer
        self.calls: list[tuple[str, str]] = []

    async def run(
        self,
        tenant_id: TenantId,
        symbol: str,
        question: str,
        history: list[Turn],
    ) -> AsyncIterator[AgentEvent]:
        _ = (tenant_id, history)
        self.calls.append((symbol, question))
        yield SkillsConsidered(titles=("Global Cues",))
        yield TextDelta(text=self._answer)
        yield AgentDone(text=self._answer)


class _FakeStore:
    def __init__(self) -> None:
        self.saved: dict[TenantId, Briefing] = {}

    async def save(self, tenant_id: TenantId, briefing: Briefing) -> None:
        self.saved[tenant_id] = briefing

    async def today(self, tenant_id: TenantId) -> Briefing | None:
        return self.saved.get(tenant_id)


async def test_service_collects_stream_into_answer() -> None:
    service = Mme100Service(agent=_FakeAgent(answer="Flat open likely."))
    answer = await service(TENANT, "NIFTY", "outlook?")
    assert answer.text == "Flat open likely."
    assert answer.symbol == "NIFTY"


async def test_service_available_reflects_the_agent() -> None:
    assert Mme100Service(agent=_FakeAgent(available=False)).available is False


async def test_briefing_runs_each_instrument_and_persists_one_document() -> None:
    agent = _FakeAgent(answer="Constructive read.")
    store = _FakeStore()
    run = RunMme100Briefing(agent=agent, store=store, instruments=("NIFTY", "BANKNIFTY"))

    briefing = await run(TENANT, tick_at=TICK)

    assert briefing is not None
    assert [symbol for symbol, _ in agent.calls] == ["NIFTY", "BANKNIFTY"]
    # One stored document covering both instruments, headed per instrument.
    assert store.saved[TENANT] is not None
    assert "## NIFTY" in briefing.markdown
    assert "## BANKNIFTY" in briefing.markdown
    assert briefing.instruments == ("NIFTY", "BANKNIFTY")
    assert briefing.trading_day == date(2026, 8, 24)


async def test_briefing_skipped_when_agent_unavailable() -> None:
    store = _FakeStore()
    run = RunMme100Briefing(
        agent=_FakeAgent(available=False), store=store, instruments=("NIFTY",)
    )
    assert await run(TENANT, tick_at=TICK) is None
    assert store.saved == {}


async def test_briefing_source_flags_simulated_reads() -> None:
    agent = _FakeAgent(answer="Note: data is mock/simulated today.")
    store = _FakeStore()
    run = RunMme100Briefing(agent=agent, store=store, instruments=("NIFTY",))
    briefing = await run(TENANT, tick_at=TICK)
    assert briefing is not None
    assert briefing.source == "mock"
