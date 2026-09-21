"""Futures-board history repository.

The single place futures-board frames are written and read, satisfying both
``futures_analytics``' writer and reader ports. Both sides live here so the
table's shape is known in exactly one module, matching
``SqlAlchemyOptionChainSnapshotRepository`` next door.
"""

from __future__ import annotations

from datetime import date
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
