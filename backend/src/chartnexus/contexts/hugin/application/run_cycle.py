"""RunHuginCycle — one tenant x instrument tick: SNAPSHOT -> GRADE -> REFLECT -> PERSIST.

The single LLM call does GRADE and REFLECT together (judge the prior expectation,
produce this hour's read + lessons), so the sequence here is:

1. SNAPSHOT  read the market once for this tenant x instrument.
2. LOAD      fetch the prior observation (the one being judged).
3. REFLECT   one LLM call over {snapshot, prior, top lessons} -> grade + new read.
4. PERSIST   write the prior row's grade, append the new observation, upsert lessons.

Stateless per call and **swallow-and-survive**: any failure is logged and turned
into a ``FAILED`` result, never raised, so one bad cycle can't kill the worker's
tick (the same rule the ingest loop follows).
"""

from __future__ import annotations

import logging
from datetime import datetime

from chartnexus.contexts.hugin.application.ports import (
    MarketReaderPort,
    MemoryStorePort,
    ReflectorPort,
)
from chartnexus.contexts.hugin.domain.cycle import (
    CycleResult,
    CycleStatus,
    ReflectInput,
    ReflectOutput,
)
from chartnexus.contexts.hugin.domain.observation import Observation
from chartnexus.contexts.hugin.domain.schedule import to_ist
from chartnexus.shared_kernel.types.identifiers import TenantId

log = logging.getLogger(__name__)


class RunHuginCycle:
    """Runs one hourly cycle for a single tenant x instrument."""

    def __init__(
        self,
        *,
        market: MarketReaderPort,
        reflector: ReflectorPort,
        store: MemoryStorePort,
        lessons_top_k: int,
    ) -> None:
        self._market = market
        self._reflector = reflector
        self._store = store
        self._lessons_top_k = lessons_top_k

    async def __call__(
        self, tenant_id: TenantId, instrument: str, *, tick_at: datetime
    ) -> CycleResult:
        # No model, no cycle: judging and reflecting both need the LLM, so a tenant
        # whose owner has no key accrues no memory (the tab reads as unavailable).
        if not self._reflector.available:
            return CycleResult(status=CycleStatus.SKIPPED_UNAVAILABLE)

        try:
            return await self._run(tenant_id, instrument, tick_at=tick_at)
        except Exception:
            log.exception("hugin cycle failed for tenant=%s instrument=%s", tenant_id, instrument)
            return CycleResult(status=CycleStatus.FAILED)

    async def _run(self, tenant_id: TenantId, instrument: str, *, tick_at: datetime) -> CycleResult:
        snapshot = await self._market.snapshot(tenant_id, instrument)
        prior = await self._store.latest_observation(tenant_id, instrument)
        lessons = await self._store.lessons_for(tenant_id, instrument, self._lessons_top_k)

        result = await self._reflector.reflect(
            ReflectInput(
                instrument=instrument,
                snapshot=snapshot,
                prior=prior,
                lessons=lessons,
            )
        )

        graded = await self._maybe_grade(prior, result)

        observation = Observation(
            tenant_id=tenant_id,
            instrument=instrument,
            tick_at=tick_at,
            trading_day=to_ist(tick_at).date(),
            readings=snapshot,
            bias=result.bias,
            expectation=result.expectation,
            call_wall=result.call_wall,
            put_wall=result.put_wall,
            key_level=result.key_level,
        )
        await self._store.append_observation(observation)

        if result.lessons:
            await self._store.upsert_lessons(tenant_id, result.lessons)

        return CycleResult(
            status=CycleStatus.PERSISTED,
            observation=observation,
            graded_prior=graded,
        )

    async def _maybe_grade(self, prior: Observation | None, result: ReflectOutput) -> bool:
        """Write the grade onto the prior row, if there is one and it was judged."""
        if prior is None or prior.id is None or result.prior_grade is None:
            return False
        await self._store.grade_previous(
            prior.id,
            grade=result.prior_grade.grade.value,
            score=result.prior_grade.score,
            evidence=result.prior_grade.evidence,
        )
        return True
