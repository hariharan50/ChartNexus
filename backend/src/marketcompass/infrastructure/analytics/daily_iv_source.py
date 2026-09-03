"""Read adapter for the per-session implied-volatility archive.

Serves ``options_analytics``'s ``DailyIvReader`` port — the daily IV history
behind the IV/HV/IVP Chart.

The **write** half lives in ``infrastructure.ingestion.daily_iv_rollup``, not
here. import-linter's independence contract sees through this package's
``__init__``, so a module here importing ``market_ingestion`` would create a
transitive path between two contexts that may not know about each other — the
same reason ``oi_chain_source`` keeps the live-chain bridge out of this package.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.options_analytics.application.ports import DailyIv
from marketcompass.infrastructure.persistence.postgresql.repositories.market_data.daily_iv_history_repository import (
    SqlAlchemyDailyIvHistoryRepository,
)
from marketcompass.shared_kernel.types.identifiers import TenantId


class SqlAlchemyDailyIvReader:
    """Implements ``options_analytics``'s ``DailyIvReader`` port."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = SqlAlchemyDailyIvHistoryRepository(session)

    async def daily_iv(
        self,
        tenant_id: TenantId,  # noqa: ARG002
        symbol: str,
        *,
        start: date,
        end: date,
    ) -> list[DailyIv]:
        records = await self._repo.between(symbol, start=start, end=end)
        return [
            DailyIv(
                session_date=record.session_date,
                atm_iv=float(record.atm_iv),
                future_close=None if record.future_close is None else float(record.future_close),
                captures=record.captures,
            )
            for record in records
        ]
