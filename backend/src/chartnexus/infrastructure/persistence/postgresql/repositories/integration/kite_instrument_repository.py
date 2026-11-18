"""Reads and the daily wholesale replace of ``kite_instruments``."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chartnexus.infrastructure.brokers.kite.instruments import KiteInstrument
from chartnexus.infrastructure.persistence.postgresql.models.integration.kite_instrument import (
    KiteInstrumentRecord,
)

#: Rows per INSERT statement. Postgres caps bind parameters at 65 535 and each
#: row binds eleven, so this stays comfortably under it.
_INSERT_CHUNK = 4_000


class SqlAlchemyKiteInstrumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_all(self, rows: Sequence[KiteInstrument], *, synced_at: datetime) -> int:
        """Swap the whole catalog in one transaction.

        The caller validates first and commits after. Because the delete and
        the inserts share the transaction, a failure part-way rolls the delete
        back too, and yesterday's catalog is still there.
        """
        await self._session.execute(delete(KiteInstrumentRecord))
        for start in range(0, len(rows), _INSERT_CHUNK):
            chunk = rows[start : start + _INSERT_CHUNK]
            self._session.add_all(
                KiteInstrumentRecord(
                    instrument_token=row.instrument_token,
                    exchange=row.exchange,
                    segment=row.segment,
                    tradingsymbol=row.tradingsymbol,
                    name=row.name,
                    instrument_type=row.instrument_type,
                    expiry=row.expiry,
                    strike=row.strike,
                    lot_size=row.lot_size,
                    tick_size=row.tick_size,
                    synced_at=synced_at,
                )
                for row in chunk
            )
            await self._session.flush()
        return len(rows)

    async def last_synced_at(self) -> datetime | None:
        result = await self._session.execute(select(func.max(KiteInstrumentRecord.synced_at)))
        return result.scalar_one_or_none()

    async def by_symbol(self, exchange: str, tradingsymbol: str) -> KiteInstrument | None:
        result = await self._session.execute(
            select(KiteInstrumentRecord)
            .where(
                KiteInstrumentRecord.exchange == exchange,
                KiteInstrumentRecord.tradingsymbol == tradingsymbol,
            )
            .limit(1)
        )
        record = result.scalar_one_or_none()
        return _to_domain(record) if record else None

    async def futures(self, name: str, exchange: str, *, today: date) -> list[KiteInstrument]:
        """Unexpired futures on ``name``, nearest expiry first."""
        result = await self._session.execute(
            select(KiteInstrumentRecord)
            .where(
                KiteInstrumentRecord.name == name,
                KiteInstrumentRecord.exchange == exchange,
                KiteInstrumentRecord.instrument_type == "FUT",
                KiteInstrumentRecord.expiry >= today,
            )
            .order_by(KiteInstrumentRecord.expiry)
        )
        return [_to_domain(record) for record in result.scalars()]

    async def option_expiries(self, name: str, exchange: str, *, today: date) -> list[date]:
        result = await self._session.execute(
            select(KiteInstrumentRecord.expiry)
            .where(
                KiteInstrumentRecord.name == name,
                KiteInstrumentRecord.exchange == exchange,
                KiteInstrumentRecord.instrument_type.in_(("CE", "PE")),
                KiteInstrumentRecord.expiry >= today,
            )
            .distinct()
            .order_by(KiteInstrumentRecord.expiry)
        )
        return [expiry for expiry in result.scalars() if expiry is not None]

    async def options(self, name: str, exchange: str, expiry: date) -> list[KiteInstrument]:
        result = await self._session.execute(
            select(KiteInstrumentRecord)
            .where(
                KiteInstrumentRecord.name == name,
                KiteInstrumentRecord.exchange == exchange,
                KiteInstrumentRecord.instrument_type.in_(("CE", "PE")),
                KiteInstrumentRecord.expiry == expiry,
            )
            .order_by(KiteInstrumentRecord.strike)
        )
        return [_to_domain(record) for record in result.scalars()]


def _to_domain(record: KiteInstrumentRecord) -> KiteInstrument:
    return KiteInstrument(
        instrument_token=record.instrument_token,
        exchange=record.exchange,
        segment=record.segment,
        tradingsymbol=record.tradingsymbol,
        name=record.name,
        instrument_type=record.instrument_type,
        expiry=record.expiry,
        strike=record.strike,
        lot_size=record.lot_size,
        tick_size=record.tick_size,
    )
