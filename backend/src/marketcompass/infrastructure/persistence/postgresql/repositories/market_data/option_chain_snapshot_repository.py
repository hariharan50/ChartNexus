"""Option-chain snapshot repository.

The single place option-chain history is written and read. The writer side
satisfies ``market_ingestion``'s ``SnapshotWriter`` port; the read side returns
ORM records that the analytics snapshot-reader adapter maps into its own domain
shapes. Both live here so the table's shape is known in exactly one module.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.market_ingestion.application.ports import SnapshotToWrite
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
        self, symbol: str, session_date: date
    ) -> OptionChainSnapshotRecord | None:
        """The most recent snapshot for a symbol on one trading date."""
        result = await self._session.execute(
            select(OptionChainSnapshotRecord)
            .where(
                OptionChainSnapshotRecord.symbol == symbol,
                OptionChainSnapshotRecord.session_date == session_date,
            )
            .order_by(OptionChainSnapshotRecord.captured_at.desc())
            .limit(1)
        )
        return result.scalars().first()
