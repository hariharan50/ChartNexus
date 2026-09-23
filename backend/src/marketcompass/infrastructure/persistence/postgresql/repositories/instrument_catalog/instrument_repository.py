"""Instrument catalog repository.

Implements the ``InstrumentRepository`` port. The catalog is global reference
data, so — unusually for this codebase — none of these queries filter by tenant.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.instrument_catalog.application.ports import CatalogSyncResult
from marketcompass.contexts.instrument_catalog.domain.instrument import (
    Instrument,
    InstrumentKind,
)
from marketcompass.infrastructure.persistence.postgresql.models.catalog.instrument import (
    InstrumentRecord,
)


class SqlAlchemyInstrumentRepository:
    """Implements the ``InstrumentRepository`` port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, symbol: str) -> Instrument | None:
        result = await self._session.execute(
            select(InstrumentRecord).where(InstrumentRecord.symbol == symbol.strip().upper())
        )
        record = result.scalar_one_or_none()
        return _to_domain(record) if record else None

    async def search(
        self,
        *,
        kind: InstrumentKind | None = None,
        search: str | None = None,
        active_only: bool = True,
        limit: int | None = None,
    ) -> list[Instrument]:
        stmt = select(InstrumentRecord)
        if active_only:
            stmt = stmt.where(InstrumentRecord.is_active.is_(True))
        if kind is not None:
            stmt = stmt.where(InstrumentRecord.kind == kind.value)

        if search and search.strip():
            needle = f"%{search.strip().upper()}%"
            # Match the ticker or the company name: a user looking for Reliance
            # may type either "RELI" or "reliance industries".
            stmt = stmt.where(
                InstrumentRecord.symbol.like(needle) | InstrumentRecord.name.ilike(needle)
            )

        # Indices before stocks, then alphabetically. 'index' sorts before
        # 'stock' lexicographically, so the kind column orders itself.
        stmt = stmt.order_by(InstrumentRecord.kind.asc(), InstrumentRecord.symbol.asc())
        if limit is not None:
            stmt = stmt.limit(limit)

        result = await self._session.execute(stmt)
        return [_to_domain(record) for record in result.scalars()]

    async def symbols(self, *, active_only: bool = True) -> frozenset[str]:
        stmt = select(InstrumentRecord.symbol)
        if active_only:
            stmt = stmt.where(InstrumentRecord.is_active.is_(True))
        result = await self._session.execute(stmt)
        return frozenset(result.scalars())

    async def replace_all(self, instruments: list[Instrument]) -> CatalogSyncResult:
        existing = {record.symbol: record for record in (await self._all_records())}
        incoming = {instrument.symbol: instrument for instrument in instruments}

        added = updated = 0
        for symbol, instrument in incoming.items():
            record = existing.get(symbol)
            if record is None:
                self._session.add(_to_record(instrument))
                added += 1
            else:
                _apply(record, instrument)
                updated += 1

        # Anything the master no longer lists is retired, not removed.
        deactivated = 0
        for symbol, record in existing.items():
            if symbol not in incoming and record.is_active:
                record.is_active = False
                deactivated += 1

        await self._session.flush()
        return CatalogSyncResult(added=added, updated=updated, deactivated=deactivated)

    # -- helpers ------------------------------------------------------------

    async def _all_records(self) -> list[InstrumentRecord]:
        result = await self._session.execute(select(InstrumentRecord))
        return list(result.scalars())


# -- mapping ----------------------------------------------------------------


def _expiries(stored: str | None) -> tuple[date, ...]:
    """The stored expiry list, skipping anything unreadable.

    Sorted and de-duplicated on the way out rather than trusted: the domain
    rejects a list that is neither, and one bad row should cost that row its
    back months, not the whole catalog load.
    """
    if not stored:
        return ()
    days: set[date] = set()
    for part in stored.split(","):
        try:
            days.add(date.fromisoformat(part.strip()))
        except ValueError:
            continue
    return tuple(sorted(days))


def _to_domain(record: InstrumentRecord) -> Instrument:
    return Instrument(
        symbol=record.symbol,
        kind=InstrumentKind(record.kind),
        name=record.name,
        exchange=record.exchange,
        lot_size=record.lot_size,
        tick_size=record.tick_size,
        spot_symbol=record.spot_symbol,
        futures_root=record.futures_root,
        isin=record.isin,
        strike_step=record.strike_step,
        underlying_token=record.underlying_token,
        front_expiry=record.front_expiry,
        futures_expiries=_expiries(record.futures_expiries),
        reference_price=record.reference_price,
        sector=record.sector,
        indices=tuple(record.indices.split(",")) if record.indices else (),
        is_active=record.is_active,
    )


def _to_record(instrument: Instrument) -> InstrumentRecord:
    record = InstrumentRecord(symbol=instrument.symbol)
    _apply(record, instrument)
    return record


def _apply(record: InstrumentRecord, instrument: Instrument) -> None:
    """Copy every mutable field. Deliberately exhaustive: a lot-size revision
    arrives as an update to an existing row, so a field missed here silently
    keeps a stale value."""
    record.kind = instrument.kind.value
    record.name = instrument.name
    record.exchange = instrument.exchange
    record.lot_size = instrument.lot_size
    record.tick_size = instrument.tick_size
    record.strike_step = instrument.strike_step
    record.spot_symbol = instrument.spot_symbol
    record.futures_root = instrument.futures_root
    record.isin = instrument.isin
    record.underlying_token = instrument.underlying_token
    record.front_expiry = instrument.front_expiry
    # Written even when empty, unlike sector and index membership below: this
    # comes from the same symbol master as every other field here, so an empty
    # list means the exchange delisted the series, not that a curated table was
    # missing.
    record.futures_expiries = (
        ",".join(day.isoformat() for day in instrument.futures_expiries) or None
    )
    record.reference_price = instrument.reference_price
    # Sector and index membership come from the curated table rather than the
    # symbol master. Preserve whatever is stored rather than blanking it if a
    # sync ever runs without that table loaded.
    if instrument.sector is not None:
        record.sector = instrument.sector
    if instrument.indices:
        record.indices = ",".join(instrument.indices)
    record.is_active = instrument.is_active
