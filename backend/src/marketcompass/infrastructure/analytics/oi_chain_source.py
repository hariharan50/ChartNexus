"""Snapshot storage adapters that feed the Open Interest use case.

``NullSnapshotReader`` is the placeholder snapshot source: there is no intraday
snapshot writer yet, so it reports none and the service serves the live tier.

The live-chain bridge (``BrokerChainProvider`` / ``build_oi_chain_provider``,
which must reach into ``market_data``) lives in
``infrastructure.brokers.oi_chain_provider`` instead of here — this package has
an ``__init__.py`` that import-linter's independence contract can see into, and
``options_analytics`` may not import ``market_data`` even transitively.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.options_analytics.application.ports import ChainSnapshot
from marketcompass.contexts.options_analytics.domain.oi_math import ChainRow
from marketcompass.infrastructure.persistence.postgresql.models.market.option_chain_snapshot import (
    OptionChainSnapshotRecord,
)
from marketcompass.infrastructure.persistence.postgresql.repositories.market_data.option_chain_snapshot_repository import (
    SqlAlchemyOptionChainSnapshotRepository,
)
from marketcompass.shared_kernel.types.identifiers import TenantId

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
    return ChainSnapshot(captured_at=record.captured_at, rows=rows)
