"""Retention policy for the option-chain archive.

The whole point of these tests is the cutoff arithmetic. A prune that deletes
one day too many is an annoyance; a prune that computes a cutoff of today or
later erases the entire archive including the session being captured, and there
is no undo.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from chartnexus.contexts.market_ingestion.application.retention import (
    PruneSnapshots,
    RetentionError,
)

_IST = timezone(timedelta(hours=5, minutes=30))


class _FrozenClock:
    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


class _RecordingPruner:
    def __init__(self, deleted: int = 0) -> None:
        self._deleted = deleted
        self.calls: list[date] = []

    async def delete_sessions_before(self, cutoff: date) -> int:
        self.calls.append(cutoff)
        return self._deleted


def _use_case(*, now: datetime, days: int = 30, deleted: int = 0) -> tuple:
    pruner = _RecordingPruner(deleted)
    return PruneSnapshots(pruner=pruner, clock=_FrozenClock(now), retention_days=days), pruner


async def test_cutoff_is_the_retention_window_before_today() -> None:
    use_case, pruner = _use_case(now=datetime(2026, 8, 5, 6, 0, tzinfo=UTC))

    result = await use_case()

    assert result.cutoff == date(2026, 7, 6)
    assert pruner.calls == [date(2026, 7, 6)]


async def test_the_cutoff_is_an_ist_date_not_a_utc_one() -> None:
    # 20:00 UTC on the 5th is 01:30 IST on the 6th. Deriving the cutoff from the
    # UTC date would keep an extra day for five and a half hours every evening,
    # against a `session_date` column that is an IST date.
    use_case, _ = _use_case(now=datetime(2026, 8, 5, 20, 0, tzinfo=UTC))

    assert use_case.cutoff() == date(2026, 7, 7)
    assert datetime(2026, 8, 5, 20, 0, tzinfo=UTC).astimezone(_IST).date() == date(2026, 8, 6)


async def test_a_no_op_pass_is_reported_honestly() -> None:
    use_case, _ = _use_case(now=datetime(2026, 8, 5, 6, 0, tzinfo=UTC), deleted=0)

    assert (await use_case()).deleted == 0


async def test_the_deleted_count_is_passed_through() -> None:
    use_case, _ = _use_case(now=datetime(2026, 8, 5, 6, 0, tzinfo=UTC), deleted=378)

    assert (await use_case()).deleted == 378


@pytest.mark.parametrize("days", [0, -1, -365])
def test_a_non_positive_window_is_refused_at_construction(days: int) -> None:
    # A window of 0 would put the cutoff on today and delete the live session.
    with pytest.raises(RetentionError, match="retention_days"):
        PruneSnapshots(
            pruner=_RecordingPruner(),
            clock=_FrozenClock(datetime(2026, 8, 5, 6, 0, tzinfo=UTC)),
            retention_days=days,
        )


async def test_one_day_of_retention_still_keeps_today() -> None:
    # The tightest legal window. The cutoff must remain strictly in the past.
    use_case, _ = _use_case(now=datetime(2026, 8, 5, 6, 0, tzinfo=UTC), days=1)

    assert use_case.cutoff() == date(2026, 8, 4)
