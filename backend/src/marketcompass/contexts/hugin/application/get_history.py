"""GetHuginHistory — HUGIN's multi-day track record, the "watch it sharpen" read.

Buckets the last N days of observations by IST trading day, computes each day's
hit-rate (over its *graded* reads), and the overall hit-rate across the window.
Pure aggregation over ``MemoryStorePort.history``; no I/O of its own.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from marketcompass.contexts.hugin.application.ports import (
    DayView,
    HistoryView,
    MemoryStorePort,
    ObservationView,
)
from marketcompass.contexts.hugin.domain.observation import Grade, Observation
from marketcompass.shared_kernel.types.identifiers import TenantId


class GetHuginHistory:
    def __init__(self, store: MemoryStorePort) -> None:
        self._store = store

    async def __call__(self, tenant_id: TenantId, instrument: str, days: int) -> HistoryView:
        observations = await self._store.history(tenant_id, instrument, days)

        by_day: dict[date, list[Observation]] = defaultdict(list)
        for obs in observations:
            by_day[obs.trading_day].append(obs)

        day_views: list[DayView] = []
        overall_graded = 0
        overall_hits = 0
        # Newest day first — the track record reads top-down as "most recent".
        for day in sorted(by_day, reverse=True):
            rows = by_day[day]
            graded = [o for o in rows if o.grade is not None]
            hits = sum(1 for o in graded if o.grade is Grade.HIT)
            overall_graded += len(graded)
            overall_hits += hits
            day_views.append(
                DayView(
                    trading_day=day,
                    observations=tuple(ObservationView.of(o) for o in rows),
                    hit_rate=(hits / len(graded)) if graded else None,
                    graded_count=len(graded),
                    hit_count=hits,
                )
            )

        return HistoryView(
            instrument=instrument,
            days=tuple(day_views),
            overall_hit_rate=(overall_hits / overall_graded) if overall_graded else None,
            overall_graded=overall_graded,
            overall_hits=overall_hits,
        )
