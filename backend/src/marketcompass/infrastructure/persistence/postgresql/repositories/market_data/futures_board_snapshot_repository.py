"""Futures-board history repository.

The single place futures-board frames are written and read, satisfying both
``futures_analytics``' writer and reader ports. Both sides live here so the
table's shape is known in exactly one module, matching
``SqlAlchemyOptionChainSnapshotRepository`` next door.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import CursorResult, Delete, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.futures_analytics.application.ports import BoardFrame
from marketcompass.infrastructure.persistence.postgresql.models.market.futures_board_snapshot import (
    FuturesBoardSnapshotRecord,
)


class SqlAlchemyFuturesBoardSnapshotRepository:
    """Writes and reads captured futures-board frames."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- writer side --------------------------------------------------------

    async def save_frames(self, frames: list[BoardFrame]) -> int:
        """Append a sweep, skipping instants already stored.

        ``ON CONFLICT DO NOTHING`` rather than a read-then-write: the worker is
        restartable and two sweeps can overlap, and letting the unique index
        arbitrate is both cheaper and free of the race a check-first would
        leave open.
        """
        if not frames:
            return 0

        statement = (
            insert(FuturesBoardSnapshotRecord)
            .values(
                [
                    {
                        "symbol": frame.symbol,
                        "session_date": frame.session_date,
                        "captured_at": frame.captured_at,
                        "price": frame.price,
                        "open_interest": frame.open_interest,
                        "volume": frame.volume,
                        "expiry": frame.expiry,
                        "source": frame.source,
                    }
                    for frame in frames
                ]
            )
            .on_conflict_do_nothing(constraint="futures_board_snapshots_symbol_instant")
        )
        result = cast("CursorResult[Any]", await self._session.execute(statement))
        await self._session.flush()
        return result.rowcount or 0

    # -- reader side --------------------------------------------------------

    async def frames_for(self, symbol: str, session_date: date) -> list[BoardFrame]:
        result = await self._session.execute(
            select(FuturesBoardSnapshotRecord)
            .where(
                FuturesBoardSnapshotRecord.symbol == symbol,
                FuturesBoardSnapshotRecord.session_date == session_date,
            )
            .order_by(FuturesBoardSnapshotRecord.captured_at)
        )
        return [_to_frame(record) for record in result.scalars().all()]

    async def frames_for_session(
        self, session_date: date, symbols: Sequence[str]
    ) -> list[BoardFrame]:
        """Every frame for a set of contracts on one session, oldest first.

        The whole scope in one query. Breadth counts across fifty contracts at
        once, and fifty single-symbol reads to draw one line would cost fifty
        round trips for a chart that has to redraw whenever the reader clicks
        a different sector.
        """
        if not symbols:
            return []
        result = await self._session.execute(
            select(FuturesBoardSnapshotRecord)
            .where(
                FuturesBoardSnapshotRecord.session_date == session_date,
                FuturesBoardSnapshotRecord.symbol.in_(list(symbols)),
            )
            .order_by(FuturesBoardSnapshotRecord.captured_at)
        )
        return [_to_frame(record) for record in result.scalars().all()]

    async def last_price_before(
        self, session_date: date, symbols: Sequence[str]
    ) -> dict[str, Decimal]:
        """Each contract's final archived price on the session before this one.

        The baseline an archived day is measured against. ``DISTINCT ON`` takes
        the newest row per symbol in one pass rather than a query per contract;
        it is Postgres-specific, which this repository already is.
        """
        if not symbols:
            return {}
        newest = (
            select(FuturesBoardSnapshotRecord.symbol, FuturesBoardSnapshotRecord.price)
            .where(
                FuturesBoardSnapshotRecord.session_date < session_date,
                FuturesBoardSnapshotRecord.symbol.in_(list(symbols)),
            )
            .order_by(
                FuturesBoardSnapshotRecord.symbol,
                FuturesBoardSnapshotRecord.captured_at.desc(),
            )
            .distinct(FuturesBoardSnapshotRecord.symbol)
        )
        result = await self._session.execute(newest)
        return {row.symbol: row.price for row in result.all()}

    async def archived_sessions(self, limit: int) -> list[date]:
        """Sessions the archive holds, newest first."""
        result = await self._session.execute(
            select(FuturesBoardSnapshotRecord.session_date)
            .distinct()
            .order_by(FuturesBoardSnapshotRecord.session_date.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def has_source(self, symbol: str, session_date: date, source: str) -> bool:
        """Whether this day already holds frames of a given provenance.

        The seeder asks before fabricating: a day the real worker has touched
        must never gain synthetic frames alongside the real ones.
        """
        result = await self._session.execute(
            select(FuturesBoardSnapshotRecord.id)
            .where(
                FuturesBoardSnapshotRecord.symbol == symbol,
                FuturesBoardSnapshotRecord.session_date == session_date,
                FuturesBoardSnapshotRecord.source == source,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def delete_session(self, symbol: str, session_date: date, source: str) -> int:
        """Drop one day's frames of one provenance — the seeder's ``--replace``."""
        return await self._execute_delete(
            delete(FuturesBoardSnapshotRecord).where(
                FuturesBoardSnapshotRecord.symbol == symbol,
                FuturesBoardSnapshotRecord.session_date == session_date,
                FuturesBoardSnapshotRecord.source == source,
            )
        )

    async def delete_sessions_before(self, cutoff: date) -> int:
        """Prune everything older than the retention window."""
        return await self._execute_delete(
            delete(FuturesBoardSnapshotRecord).where(
                FuturesBoardSnapshotRecord.session_date < cutoff
            )
        )

    async def _execute_delete(self, statement: Delete) -> int:
        result = cast("CursorResult[Any]", await self._session.execute(statement))
        await self._session.flush()
        return result.rowcount or 0


def _to_frame(record: FuturesBoardSnapshotRecord) -> BoardFrame:
    return BoardFrame(
        symbol=record.symbol,
        session_date=record.session_date,
        captured_at=record.captured_at,
        price=record.price,
        open_interest=record.open_interest,
        volume=record.volume,
        expiry=record.expiry,
        source=record.source,
    )
