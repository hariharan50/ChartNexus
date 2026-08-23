"""GenerateHuginCall — turn HUGIN's memory into a saved, actionable call.

Builds the same memory digest the chat uses (reads + lessons + track record), asks
the model for a two-part call (analytical read + trade structure), stamps it with
HUGIN's *measured* hit-rate so conviction reads honestly, persists it, and returns
it. Memory-grounded: no live market fetch. A thin ``GetHuginCalls`` reads the
recent list back for the UI.
"""

from __future__ import annotations

from decimal import Decimal

from marketcompass.contexts.hugin.application.ports import (
    CallGeneratorPort,
    CallStorePort,
    MemoryStorePort,
)
from marketcompass.contexts.hugin.domain.call import HuginCall
from marketcompass.contexts.hugin.domain.memory_digest import build_digest
from marketcompass.contexts.hugin.domain.observation import Grade, Observation
from marketcompass.shared_kernel.types.identifiers import TenantId


class GenerateHuginCall:
    def __init__(
        self,
        *,
        generator: CallGeneratorPort,
        store: MemoryStorePort,
        calls: CallStorePort,
        lessons_top_k: int,
        history_days: int,
    ) -> None:
        self._generator = generator
        self._store = store
        self._calls = calls
        self._lessons_top_k = lessons_top_k
        self._history_days = history_days

    @property
    def available(self) -> bool:
        return self._generator.available

    async def __call__(self, tenant_id: TenantId, instrument: str) -> HuginCall:
        today = await self._store.today(tenant_id, instrument)
        window = await self._store.history(tenant_id, instrument, self._history_days)
        lessons = await self._store.lessons_for(tenant_id, instrument, self._lessons_top_k)

        track = _hit_rate(window)
        digest = build_digest(
            instrument=instrument,
            today=today,
            lessons=lessons,
            hit_rate_today=_hit_rate(today),
            overall_hit_rate=track,
        )
        call = await self._generator.generate(
            digest, instrument, Decimal(str(track)) if track is not None else None
        )
        await self._calls.append(tenant_id, call)
        return call


class GetHuginCalls:
    def __init__(self, calls: CallStorePort, *, limit: int) -> None:
        self._calls = calls
        self._limit = limit

    async def __call__(self, tenant_id: TenantId, instrument: str) -> tuple[HuginCall, ...]:
        return await self._calls.recent(tenant_id, instrument, self._limit)


def _hit_rate(observations: tuple[Observation, ...]) -> float | None:
    graded = [o for o in observations if o.grade is not None]
    if not graded:
        return None
    return sum(1 for o in graded if o.grade is Grade.HIT) / len(graded)
