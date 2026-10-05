"""The STRYX use case sequences the discipline around the agent.

Fakes stand in for the LangGraph adapter and the Postgres journal, pinning the
two things the service owns that HELLA's has no equivalent of: it tells the agent
when the daily LIVE-call cap is already reached, and it journals every completed
call (parsed from the answer, with the raw text) after the stream.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from chartnexus.contexts.stryx.application.ports import (
    AgentDone,
    AgentEvent,
    JournalEntry,
    StylesConsidered,
    TextDelta,
    Turn,
)
from chartnexus.contexts.stryx.application.stryx_service import StryxService
from chartnexus.contexts.stryx.domain.call_template import StryxCall
from chartnexus.shared_kernel.types.identifiers import TenantId

TENANT = TenantId(uuid.uuid4())

_LIVE_ANSWER = (
    "[STRYX CALL]\nInstrument: NIFTY 23100 CE\nEntry Style: Breakout\nEntry: 23,050\n"
    "SL: 22,950\nTarget 1: 23,200\nConfidence: High\nReasoning: OI unwind.\nStatus: LIVE"
)


class _FakeAgent:
    def __init__(self, *, answer: str = _LIVE_ANSWER, available: bool = True) -> None:
        self.available = available
        self._answer = answer
        self.seen_cap_reached: bool | None = None

    async def run(
        self,
        tenant_id: TenantId,
        symbol: str,
        question: str,
        history: list[Turn],
        *,
        cap_reached: bool,
    ) -> AsyncIterator[AgentEvent]:
        _ = (tenant_id, symbol, question, history)
        self.seen_cap_reached = cap_reached
        yield StylesConsidered(titles=("Breakout Entry",))
        yield TextDelta(text=self._answer)
        yield AgentDone(text=self._answer)


class _FakeJournal:
    def __init__(self, *, live_today: int = 0) -> None:
        self._live_today = live_today
        self.appended: list[tuple[StryxCall, str, str]] = []

    async def append(
        self,
        tenant_id: TenantId,
        call: StryxCall,
        *,
        question: str,
        raw_answer: str,
        source: str,
    ) -> None:
        _ = (tenant_id, question)
        self.appended.append((call, raw_answer, source))

    async def live_call_count_today(self, tenant_id: TenantId) -> int:
        _ = tenant_id
        return self._live_today

    async def today(self, tenant_id: TenantId) -> tuple[JournalEntry, ...]:
        _ = tenant_id
        return ()


async def _drain(stream: AsyncIterator[AgentEvent]) -> None:
    async for _ in stream:
        pass


async def test_available_reflects_the_agent() -> None:
    assert StryxService(agent=_FakeAgent(available=True), journal=_FakeJournal()).available is True
    assert (
        StryxService(agent=_FakeAgent(available=False), journal=_FakeJournal()).available is False
    )


async def test_cap_not_reached_under_limit() -> None:
    agent = _FakeAgent()
    service = StryxService(agent=agent, journal=_FakeJournal(live_today=1))
    await _drain(service.stream(TENANT, "NIFTY", "any setup?"))
    assert agent.seen_cap_reached is False


async def test_cap_reached_at_limit() -> None:
    agent = _FakeAgent()
    service = StryxService(agent=agent, journal=_FakeJournal(live_today=2))
    await _drain(service.stream(TENANT, "NIFTY", "any setup?"))
    assert agent.seen_cap_reached is True


async def test_journals_the_parsed_call_after_the_stream() -> None:
    journal = _FakeJournal()
    service = StryxService(agent=_FakeAgent(), journal=journal)

    await _drain(service.stream(TENANT, "NIFTY", "any setup?"))

    assert len(journal.appended) == 1
    call, raw_answer, source = journal.appended[0]
    assert call.status.value == "LIVE"
    assert call.instrument == "NIFTY 23100 CE"
    assert raw_answer == _LIVE_ANSWER
    assert source == "live"


async def test_mock_source_detected_from_answer() -> None:
    answer = "[STRYX CALL]\nStatus: NO TRADE\nReasoning: data is mock, illustrative only."
    journal = _FakeJournal()
    service = StryxService(agent=_FakeAgent(answer=answer), journal=journal)

    await _drain(service.stream(TENANT, "NIFTY", "any setup?"))

    _, _, source = journal.appended[0]
    assert source == "mock"


async def test_collects_stream_into_one_answer() -> None:
    service = StryxService(agent=_FakeAgent(), journal=_FakeJournal())
    answer = await service(TENANT, "NIFTY", "any setup?")
    assert answer.text == _LIVE_ANSWER
    assert answer.symbol == "NIFTY"


async def test_conversational_reply_is_not_journaled() -> None:
    # A greeting reply carries no [STRYX CALL] / Status line, so it must not be
    # logged as a NO TRADE nor touch the daily budget.
    chit_chat = "Hey! I'm STRYX — the aggressive half of the desk. Want me to scan NIFTY?"
    journal = _FakeJournal()
    service = StryxService(agent=_FakeAgent(answer=chit_chat), journal=journal)

    await _drain(service.stream(TENANT, "NIFTY", "hi, what's your name?"))

    assert journal.appended == []
