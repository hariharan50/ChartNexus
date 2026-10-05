"""The price-candle cache repository — satisfies ``market_data.HistoryCachePort``.

Writes freshly-fetched real candles, reads the recent window back, and prunes
anything past the retention window on every write so the table never grows
unbounded. Bars are keyed by ``(symbol, interval, bucket_start)`` and upserted, so
re-fetching a session that is still forming simply refreshes its latest bars
rather than duplicating them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from chartnexus.contexts.market_data.domain.instruments import InstrumentSymbol
from chartnexus.contexts.market_data.domain.market_data import (
    Candle,
    CandleInterval,
    CandleSeries,
    DataSource,
    Provenance,
)
from chartnexus.infrastructure.persistence.postgresql.models.market.price_candle import (
    PriceCandleRecord,
)


class SqlAlchemyPriceCandleRepository:
    """Bounded write-through cache of price candles."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def store(self, series: CandleSeries, *, retain_days: int, now: datetime) -> None:
        if not series.candles:
            return
        symbol = series.instrument.value
        interval = series.interval.value
        source = series.provenance.source.value

        rows = [
            {
                "symbol": symbol,
                "interval": interval,
                "bucket_start": candle.opened_at,
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
                "source": source,
            }
            for candle in series.candles
        ]
        statement = pg_insert(PriceCandleRecord).values(rows)
        # A bar that is still forming (today's last) is re-fetched with new
        # high/low/close/volume, so the natural key upserts rather than collides.
        statement = statement.on_conflict_do_update(
            constraint="uq_price_candles_bar",
            set_={
                "open": statement.excluded.open,
                "high": statement.excluded.high,
                "low": statement.excluded.low,
                "close": statement.excluded.close,
                "volume": statement.excluded.volume,
                "source": statement.excluded.source,
                "updated_at": now,
            },
        )
        # A SAVEPOINT, so a cache-write failure (e.g. the table not yet migrated)
        # rolls back only this write and leaves the request's own transaction
        # usable. The cache shares the caller's session — without this a failed
        # insert would abort the whole transaction and take the live read down
        # with it. The caller still swallows the raised error; this just keeps the
        # session healthy for the work that follows the history fetch.
        async with self._session.begin_nested():
            await self._session.execute(statement)
            await self._prune(symbol, interval, before=now - timedelta(days=retain_days))

    async def recent(
        self,
        instrument: InstrumentSymbol,
        interval: CandleInterval,
        *,
        days: int,
        now: datetime,
    ) -> CandleSeries | None:
        since = now - timedelta(days=days)
        result = await self._session.execute(
            select(PriceCandleRecord)
            .where(
                PriceCandleRecord.symbol == instrument.value,
                PriceCandleRecord.interval == interval.value,
                PriceCandleRecord.bucket_start >= since,
            )
            .order_by(PriceCandleRecord.bucket_start.asc())
        )
        records = result.scalars().all()
        if not records:
            return None

        candles = tuple(
            Candle(
                opened_at=_as_utc(record.bucket_start),
                open=record.open,
                high=record.high,
                low=record.low,
                close=record.close,
                volume=record.volume,
            )
            for record in records
        )
        # The cache only ever holds real data, but it is by definition not live
        # now — mark it cached so the badge tells the truth.
        return CandleSeries(
            instrument=instrument,
            interval=interval,
            candles=candles,
            provenance=Provenance(source=DataSource.CACHED, fetched_at=now),
        )

    async def _prune(self, symbol: str, interval: str, *, before: datetime) -> int:
        result = cast(
            "CursorResult[Any]",
            await self._session.execute(
                delete(PriceCandleRecord).where(
                    PriceCandleRecord.symbol == symbol,
                    PriceCandleRecord.interval == interval,
                    PriceCandleRecord.bucket_start < before,
                )
            ),
        )
        return result.rowcount or 0


def _as_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
