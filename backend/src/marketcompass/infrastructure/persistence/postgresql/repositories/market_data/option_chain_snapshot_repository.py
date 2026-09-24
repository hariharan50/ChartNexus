"""Option-chain snapshot repository.

The single place option-chain history is written and read. The writer side
satisfies ``market_ingestion``'s ``SnapshotWriter`` port; the read side returns
ORM records that the analytics snapshot-reader adapter maps into its own domain
shapes. Both live here so the table's shape is known in exactly one module.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any, cast

from sqlalchemy import CursorResult, Delete, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.market_ingestion.application.ports import (
    ChainRowToWrite,
    SnapshotToWrite,
)
from marketcompass.infrastructure.persistence.postgresql.models.market.option_chain_row import (
    OptionChainRowRecord,
)
from marketcompass.infrastructure.persistence.postgresql.models.market.option_chain_snapshot import (
    OptionChainSnapshotRecord,
)


class SqlAlchemyOptionChainSnapshotRepository:
    """Writes and reads captured option-chain snapshots."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- writer side (market_ingestion.SnapshotWriter) ----------------------

    async def save(self, snapshot: SnapshotToWrite) -> None:
        record = OptionChainSnapshotRecord(
            symbol=snapshot.symbol,
            session_date=snapshot.session_date,
            captured_at=snapshot.captured_at,
            expiry=snapshot.expiry,
            spot=snapshot.spot,
            future_price=snapshot.future_price,
            lot_size=snapshot.lot_size,
            atm_strike=snapshot.atm_strike,
            total_call_oi=snapshot.total_call_oi,
            total_put_oi=snapshot.total_put_oi,
            pcr_oi=snapshot.pcr_oi,
            max_pain_strike=snapshot.max_pain_strike,
            source=snapshot.source,
            rows=[
                OptionChainRowRecord(
                    strike=row.strike,
                    option_type=row.option_type,
                    oi=row.oi,
                    oi_change=row.oi_change,
                    volume=row.volume,
                    ltp=row.ltp,
                    iv=row.iv,
                    delta=row.delta,
                )
                for row in snapshot.rows
            ],
        )
        self._session.add(record)
        await self._session.flush()

    # -- reader side --------------------------------------------------------

    async def snapshots_for(
        self, symbol: str, session_date: date
    ) -> Sequence[OptionChainSnapshotRecord]:
        """Every snapshot for a symbol on one trading date, earliest first."""
        result = await self._session.execute(
            select(OptionChainSnapshotRecord)
            .where(
                OptionChainSnapshotRecord.symbol == symbol,
                OptionChainSnapshotRecord.session_date == session_date,
            )
            .order_by(OptionChainSnapshotRecord.captured_at.asc())
        )
        return result.scalars().all()

    async def latest(
        self, symbol: str, session_date: date, expiry: str | None = None
    ) -> OptionChainSnapshotRecord | None:
        """The most recent snapshot for a symbol on one trading date.

        Narrowed to one contract when ``expiry`` is given - the archive holds
        several per symbol once the worker captures more than the front month.
        """
        clauses = [
            OptionChainSnapshotRecord.symbol == symbol,
            OptionChainSnapshotRecord.session_date == session_date,
        ]
        if expiry is not None:
            clauses.append(OptionChainSnapshotRecord.expiry == expiry)

        result = await self._session.execute(
            select(OptionChainSnapshotRecord)
            .where(*clauses)
            .order_by(OptionChainSnapshotRecord.captured_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def latest_rows(
        self, symbol: str, session_date: date, expiry: str | None = None
    ) -> tuple[ChainRowToWrite, ...] | None:
        """Satisfies ``market_ingestion``'s ``SnapshotWriter.latest_rows``.

        Mapped back into the context's own DTO rather than handing out ORM
        records, so the caller can compare it against what it is about to write
        with a plain ``==`` on frozen dataclasses.
        """
        record = await self.latest(symbol, session_date, expiry)
        if record is None:
            return None
        return tuple(
            ChainRowToWrite(
                strike=row.strike,
                option_type=row.option_type,
                oi=row.oi,
                oi_change=row.oi_change,
                volume=row.volume,
                ltp=row.ltp,
                iv=row.iv,
                delta=row.delta,
            )
            for row in record.rows
        )

    async def has_source(self, symbol: str, session_date: date, source: str) -> bool:
        """Whether any snapshot of that provenance exists for the symbol-day.

        The seeder asks before writing: overwriting a day that holds real
        captures with fabricated interest is not a mistake you can undo.
        """
        result = await self._session.execute(
            select(OptionChainSnapshotRecord.id)
            .where(
                OptionChainSnapshotRecord.symbol == symbol,
                OptionChainSnapshotRecord.session_date == session_date,
                OptionChainSnapshotRecord.source == source,
            )
            .limit(1)
        )
        return result.first() is not None

    # -- deletion -----------------------------------------------------------

    async def _execute_delete(self, statement: Delete) -> int:
        """Run a DELETE and report the row count.

        ``AsyncSession.execute`` is typed as returning a plain ``Result``, which
        has no ``rowcount``; a DELETE always yields a ``CursorResult``. One cast
        here beats one at each call site.
        """
        result = cast("CursorResult[Any]", await self._session.execute(statement))
        return result.rowcount or 0

    async def delete_session(self, symbol: str, session_date: date, source: str) -> int:
        """Remove one symbol-day of one provenance. Returns snapshots deleted.

        Scoped by ``source`` so re-seeding can be idempotent without ever being
        able to touch a real capture.
        """
        return await self._execute_delete(
            delete(OptionChainSnapshotRecord).where(
                OptionChainSnapshotRecord.symbol == symbol,
                OptionChainSnapshotRecord.session_date == session_date,
                OptionChainSnapshotRecord.source == source,
            )
        )

    async def delete_sessions_before(self, cutoff: date, batch_size: int = 500) -> int:
        """Satisfies ``market_ingestion``'s ``SnapshotPruner``.

        Batched deliberately. A month of retention on three symbols is ~11k
        headers and ~1M child rows; one unbounded statement would hold locks on
        the table the ingest worker is writing to. Children go by the FK's
        ``ON DELETE CASCADE`` — hydrating ORM objects just to delete them would
        pull the whole archive through memory.
        """
        deleted = 0
        while True:
            doomed = (
                select(OptionChainSnapshotRecord.id)
                .where(OptionChainSnapshotRecord.session_date < cutoff)
                .limit(batch_size)
                .scalar_subquery()
            )
            removed = await self._execute_delete(
                delete(OptionChainSnapshotRecord).where(OptionChainSnapshotRecord.id.in_(doomed))
            )
            deleted += removed
            if removed < batch_size:
                return deleted
