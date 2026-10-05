"""Snapshot storage adapters that feed the Open Interest use case.

``SqlAlchemySnapshotReader`` reads the archive the ingest worker writes;
``NullSnapshotReader`` reports none, forcing the service onto its live tier, and
is what a caller wires when it deliberately wants no history.

The live-chain bridge (``BrokerChainProvider`` / ``build_oi_chain_provider``,
which must reach into ``market_data``) lives in
``infrastructure.brokers.oi_chain_provider`` instead of here — this package has
an ``__init__.py`` that import-linter's independence contract can see into, and
``options_analytics`` may not import ``market_data`` even transitively.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from chartnexus.contexts.options_analytics.application.ports import ChainSnapshot
from chartnexus.contexts.options_analytics.domain.oi_math import ChainRow
from chartnexus.infrastructure.persistence.postgresql.models.market.option_chain_snapshot import (
    OptionChainSnapshotRecord,
)
from chartnexus.infrastructure.persistence.postgresql.repositories.market_data.option_chain_snapshot_repository import (
    SqlAlchemyOptionChainSnapshotRepository,
)
from chartnexus.shared_kernel.types.identifiers import TenantId

# India observes no DST; a fixed +05:30 offset matches how the OI service and the
# ingest writer both reason about the trading session.
_IST = timezone(timedelta(hours=5, minutes=30))


class NullSnapshotReader:
    """Implements ``SnapshotReader`` with no stored history (yet).

    The arguments are unused by design — the port shape is what matters, and a
    real reader will use every one.
    """

    async def latest_in_session(
        self,
        tenant_id: TenantId,  # noqa: ARG002
        symbol: str,  # noqa: ARG002
        *,
        now_utc: datetime,  # noqa: ARG002
    ) -> ChainSnapshot | None:
        return None

    async def day_snapshots(
        self,
        tenant_id: TenantId,  # noqa: ARG002
        symbol: str,  # noqa: ARG002
        *,
        trade_date_utc: datetime,  # noqa: ARG002
    ) -> list[ChainSnapshot]:
        return []

    async def recent_session_snapshots(
        self,
        tenant_id: TenantId,  # noqa: ARG002
        symbol: str,  # noqa: ARG002
        *,
        end_utc: datetime,  # noqa: ARG002
        sessions: int,  # noqa: ARG002
    ) -> list[ChainSnapshot]:
        return []


class SqlAlchemySnapshotReader:
    """Implements ``SnapshotReader`` over the captured snapshot tables.

    Snapshots are stored market-wide per symbol, so ``tenant_id`` is accepted to
    satisfy the port but not used to scope the query — the open interest on an
    index is the same fact for every tenant. The trading date is the IST session
    date derived from the passed UTC instant.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._repo = SqlAlchemyOptionChainSnapshotRepository(session)

    async def latest_in_session(
        self,
        tenant_id: TenantId,  # noqa: ARG002 — snapshots are global per symbol
        symbol: str,
        *,
        now_utc: datetime,
    ) -> ChainSnapshot | None:
        record = await self._repo.latest(symbol, _ist_session_date(now_utc))
        return _to_chain_snapshot(record) if record is not None else None

    async def day_snapshots(
        self,
        tenant_id: TenantId,  # noqa: ARG002
        symbol: str,
        *,
        trade_date_utc: datetime,
    ) -> list[ChainSnapshot]:
        records = await self._repo.snapshots_for(symbol, _ist_session_date(trade_date_utc))
        return [_to_chain_snapshot(record) for record in records]

    async def recent_session_snapshots(
        self,
        tenant_id: TenantId,  # noqa: ARG002
        symbol: str,
        *,
        end_utc: datetime,
        sessions: int,
    ) -> list[ChainSnapshot]:
        dates = await self._repo.recent_session_dates(
            symbol, on_or_before=_ist_session_date(end_utc), limit=max(1, sessions)
        )
        if not dates:
            return []
        records = await self._repo.snapshots_between(symbol, dates[0], dates[-1])
        return [_to_chain_snapshot(record) for record in records]


def _ist_session_date(moment: datetime) -> date:
    aware = moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    return aware.astimezone(_IST).date()


def _to_chain_snapshot(record: OptionChainSnapshotRecord) -> ChainSnapshot:
    rows = tuple(
        ChainRow(
            strike=float(row.strike),
            option_type=row.option_type,
            oi=row.oi,
            oi_change=row.oi_change,
            ltp=float(row.ltp) if row.ltp is not None else 0.0,
            volume=row.volume,
            iv=float(row.iv) if row.iv is not None else None,
        )
        for row in record.rows
    )
    # The header metrics are already denormalised onto the snapshot row, so
    # carrying them costs no extra query — and without them a scrubbed frame has
    # no spot or max pain of its own to draw.
    return ChainSnapshot(
        captured_at=record.captured_at,
        rows=rows,
        expiry=record.expiry,
        spot=float(record.spot) if record.spot is not None else None,
        atm_strike=float(record.atm_strike) if record.atm_strike is not None else None,
        max_pain=float(record.max_pain_strike) if record.max_pain_strike is not None else None,
        # Falls back to spot only for rows captured before the column existed.
        future_price=float(record.future_price)
        if record.future_price is not None
        else (float(record.spot) if record.spot is not None else None),
    )
