"""Daily implied-volatility history repository.

The single place the per-session IV archive is written and read. The writer side
serves ``market_ingestion``'s rollup; the read side serves the analytics adapter
that ``options_analytics`` talks to.

It is the first repository in the codebase with a **range read**. Every other
market query is keyed to one ``session_date``, because every other page reads one
session. This one exists precisely to span them.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.infrastructure.persistence.postgresql.models.market.daily_iv_history import (
    DailyIvHistoryRecord,
)


class SqlAlchemyDailyIvHistoryRepository:
    """Writes and reads one IV reading per instrument per session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- writer side --------------------------------------------------------

    async def upsert(self, rows: Sequence[dict[str, object]], *, now: datetime) -> int:
        """Write a batch of daily readings, replacing any day already stored.

        Upsert rather than insert because the rollup re-runs over the whole
        retained window every time: today's row is rewritten as the session
        fills out, and re-running the backfill must not duplicate a day.
        """
        if not rows:
            return 0

        statement = pg_insert(DailyIvHistoryRecord).values(list(rows))
        statement = statement.on_conflict_do_update(
            constraint="uq_daily_iv_history_session",
            set_={
                "atm_iv": statement.excluded.atm_iv,
                "future_close": statement.excluded.future_close,
                "captures": statement.excluded.captures,
                "source": statement.excluded.source,
                "updated_at": now,
            },
        )
        await self._session.execute(statement)
        return len(rows)

    # -- reader side --------------------------------------------------------

    async def between(
        self, symbol: str, *, start: date, end: date
    ) -> Sequence[DailyIvHistoryRecord]:
        """Every stored reading in an inclusive date range, oldest first."""
        result = await self._session.execute(
            select(DailyIvHistoryRecord)
            .where(
                DailyIvHistoryRecord.symbol == symbol,
                DailyIvHistoryRecord.session_date >= start,
                DailyIvHistoryRecord.session_date <= end,
            )
            .order_by(DailyIvHistoryRecord.session_date.asc())
        )
        return result.scalars().all()
