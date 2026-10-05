"""AskHugin — the memory-grounded chat use case.

Builds HUGIN's memory digest (today's reads + the track record + lessons) from the
store, then streams the model's answer over it. HUGIN chats only about what it has
observed and learned; it never touches the live market tools. Session load/save is
the transport's job (it owns the SSE frame that returns the session id).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from chartnexus.contexts.hugin.application.ports import ChatPort, MemoryStorePort
from chartnexus.contexts.hugin.domain.conversation import ChatEvent, Turn
from chartnexus.contexts.hugin.domain.memory_digest import build_digest
from chartnexus.contexts.hugin.domain.observation import Grade, Observation
from chartnexus.shared_kernel.types.identifiers import TenantId


class AskHugin:
    def __init__(
        self,
        *,
        agent: ChatPort,
        store: MemoryStorePort,
        lessons_top_k: int,
        history_days: int,
    ) -> None:
        self._agent = agent
        self._store = store
        self._lessons_top_k = lessons_top_k
        self._history_days = history_days

    @property
    def available(self) -> bool:
        return self._agent.available

    async def stream(
        self, tenant_id: TenantId, instrument: str, question: str, history: list[Turn]
    ) -> AsyncIterator[ChatEvent]:
        today = await self._store.today(tenant_id, instrument)
        window = await self._store.history(tenant_id, instrument, self._history_days)
        lessons = await self._store.lessons_for(tenant_id, instrument, self._lessons_top_k)

        digest = build_digest(
            instrument=instrument,
            today=today,
            lessons=lessons,
            hit_rate_today=_hit_rate(today),
            overall_hit_rate=_hit_rate(window),
        )
        async for event in self._agent.stream(digest, question, history):
            yield event


def _hit_rate(observations: tuple[Observation, ...]) -> float | None:
    graded = [o for o in observations if o.grade is not None]
    if not graded:
        return None
    return sum(1 for o in graded if o.grade is Grade.HIT) / len(graded)
