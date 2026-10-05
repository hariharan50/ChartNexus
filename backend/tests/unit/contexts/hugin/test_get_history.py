"""GetHuginHistory — per-day and overall hit-rate bucketing over a fake store."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from chartnexus.contexts.hugin.application.get_history import GetHuginHistory
from chartnexus.contexts.hugin.domain.observation import Bias, Grade, Observation
from chartnexus.shared_kernel.types.identifiers import TenantId

TENANT = TenantId(uuid.uuid4())


def _obs(day: date, grade: Grade | None) -> Observation:
    return Observation(
        tenant_id=TENANT,
        instrument="NIFTY",
        tick_at=datetime(day.year, day.month, day.day, 10, 15, tzinfo=UTC),
        trading_day=day,
        readings={},
        bias=Bias.BULLISH,
        expectation="x",
        grade=grade,
    )


class _FakeStore:
    def __init__(self, observations: list[Observation]) -> None:
        self._observations = observations

    async def history(self, tenant_id, instrument, days):  # type: ignore[no-untyped-def]
        return tuple(self._observations)

    # Rest of the port is unused here.
    async def latest_observation(self, t, i):  # type: ignore[no-untyped-def]
        return None

    async def append_observation(self, o):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def grade_previous(self, oid, *, grade, score, evidence):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def lessons_for(self, t, i, k):  # type: ignore[no-untyped-def]
        return ()

    async def upsert_lessons(self, t, ls):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def today(self, t, i):  # type: ignore[no-untyped-def]
        return ()

    async def all_lessons(self, t):  # type: ignore[no-untyped-def]
        return ()


async def test_buckets_by_day_newest_first_with_per_day_and_overall_rates() -> None:
    d1 = date(2026, 8, 20)
    d2 = date(2026, 8, 21)
    store = _FakeStore(
        [
            _obs(d1, Grade.HIT),
            _obs(d1, Grade.MISS),  # day1: 1/2
            _obs(d2, Grade.HIT),
            _obs(d2, Grade.HIT),
            _obs(d2, None),  # day2: 2/2 graded, 1 ungraded
        ]
    )
    view = await GetHuginHistory(store)(TENANT, "NIFTY", days=7)

    assert [d.trading_day for d in view.days] == [d2, d1]  # newest first
    assert view.days[0].hit_rate == 1.0
    assert view.days[1].hit_rate == 0.5
    assert view.overall_graded == 4
    assert view.overall_hits == 3
    assert view.overall_hit_rate == 0.75


async def test_empty_history_has_no_overall_rate() -> None:
    view = await GetHuginHistory(_FakeStore([]))(TENANT, "NIFTY", days=7)
    assert view.days == ()
    assert view.overall_hit_rate is None
