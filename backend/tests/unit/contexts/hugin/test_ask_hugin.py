"""AskHugin — builds the memory digest from the store and streams the answer."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from marketcompass.contexts.hugin.application.ask_hugin import AskHugin
from marketcompass.contexts.hugin.domain.conversation import ChatDone, ChatEvent, TextDelta, Turn
from marketcompass.contexts.hugin.domain.lesson import Lesson
from marketcompass.shared_kernel.types.identifiers import TenantId

TENANT = TenantId(uuid.uuid4())


class _FakeStore:
    def __init__(self, lessons: tuple[Lesson, ...]) -> None:
        self._lessons = lessons

    async def today(self, t, i):  # type: ignore[no-untyped-def]
        return ()

    async def history(self, t, i, d):  # type: ignore[no-untyped-def]
        return ()

    async def lessons_for(self, t, i, k):  # type: ignore[no-untyped-def]
        return self._lessons

    # unused
    async def latest_observation(self, t, i):  # type: ignore[no-untyped-def]
        return None

    async def append_observation(self, o):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def grade_previous(self, oid, *, grade, score, evidence):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def upsert_lessons(self, t, ls):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def all_lessons(self, t):  # type: ignore[no-untyped-def]
        return ()


class _FakeChat:
    available = True

    def __init__(self) -> None:
        self.seen_digest: str | None = None

    async def stream(
        self, digest: str, question: str, history: list[Turn]
    ) -> AsyncIterator[ChatEvent]:
        self.seen_digest = digest
        yield TextDelta(text="Based on memory, ")
        yield TextDelta(text="bullish.")
        yield ChatDone(text="Based on memory, bullish.")


async def test_streams_answer_grounded_in_a_digest_built_from_the_store() -> None:
    agent = _FakeChat()
    store = _FakeStore((Lesson(dedup_key="pcr_flip", text="PCR flip leads", hits=2),))
    ask = AskHugin(agent=agent, store=store, lessons_top_k=8, history_days=7)

    events = [ev async for ev in ask.stream(TENANT, "NIFTY", "what's your read?", history=[])]

    assert ask.available is True
    assert isinstance(events[-1], ChatDone)
    assert events[-1].text == "Based on memory, bullish."
    # The agent was handed HUGIN's memory digest, not raw market data.
    assert agent.seen_digest is not None
    assert "HUGIN MEMORY — NIFTY" in agent.seen_digest
    assert "PCR flip leads" in agent.seen_digest
