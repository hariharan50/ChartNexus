"""Rollup adapters for the per-session implied-volatility archive.

The **write** half of ``daily_iv_history``: it derives one closing at-the-money
IV per archived session and stores it, satisfying ``market_ingestion``'s
``SessionIvSource`` and ``DailyIvWriter`` ports.

It lives here rather than beside the read adapter in ``infrastructure.analytics``
for the reason that package's own docstring gives: import-linter's independence
contract sees through a package's ``__init__``, so an analytics module importing
``market_ingestion`` would put a transitive path between two contexts that must
not know about each other. The read half stays there; this half stays here.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.market_ingestion.application.rollup import SessionIv
from marketcompass.infrastructure.persistence.postgresql.models.market.option_chain_row import (
    OptionChainRowRecord,
)
from marketcompass.infrastructure.persistence.postgresql.models.market.option_chain_snapshot import (
    OptionChainSnapshotRecord,
)
from marketcompass.infrastructure.persistence.postgresql.repositories.market_data.daily_iv_history_repository import (
    SqlAlchemyDailyIvHistoryRepository,
)


class SqlAlchemySessionIvSource:
    """Derives one closing ATM IV per session from the intraday archive."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def session_ivs(self, symbol: str, *, since: date) -> list[SessionIv]:
        # The last capture of each session, and how many captures backed it.
        # One query rather than one per day: the retained window is ~30 days
        # per symbol, and thirty round trips for thirty numbers is thirty too
        # many.
        result = await self._session.execute(
            select(
                OptionChainSnapshotRecord.session_date,
                OptionChainSnapshotRecord.id,
                OptionChainSnapshotRecord.atm_strike,
                OptionChainSnapshotRecord.future_price,
                OptionChainSnapshotRecord.source,
                OptionChainSnapshotRecord.captured_at,
            )
            .where(
                OptionChainSnapshotRecord.symbol == symbol,
                OptionChainSnapshotRecord.session_date >= since,
            )
            .order_by(
                OptionChainSnapshotRecord.session_date.asc(),
                OptionChainSnapshotRecord.captured_at.asc(),
            )
        )
        rows = result.all()
        if not rows:
            return []

        last: dict[date, tuple[uuid.UUID, Decimal | None, Decimal | None, str]] = {}
        counts: dict[date, int] = {}
        for session_date, snap_id, atm_strike, future_price, source, _captured in rows:
            last[session_date] = (snap_id, atm_strike, future_price, source)
            counts[session_date] = counts.get(session_date, 0) + 1

        out: list[SessionIv] = []
        for session_date, (snap_id, atm_strike, future_price, source) in last.items():
            if atm_strike is None:
                continue
            atm_iv = await self._atm_iv(snap_id, atm_strike)
            if atm_iv is None:
                # A session whose closing capture quoted no volatility at the
                # money contributes no row at all. Writing a zero, or borrowing
                # a neighbouring strike's, would be inventing the one number
                # this table exists to remember.
                continue
            out.append(
                SessionIv(
                    symbol=symbol,
                    session_date=session_date,
                    atm_iv=atm_iv,
                    future_close=future_price,
                    captures=counts[session_date],
                    source=source,
                )
            )
        return out

    async def _atm_iv(self, snapshot_id: uuid.UUID, atm_strike: Decimal) -> Decimal | None:
        """Mean of the call and put IV at the money, ignoring an unquoted side.

        The same rule ``market_data``'s ``atm_implied_volatility`` applies to a
        live chain, so the stored history and the live reading mean the same
        thing.
        """
        result = await self._session.execute(
            select(OptionChainRowRecord.iv).where(
                OptionChainRowRecord.snapshot_id == snapshot_id,
                OptionChainRowRecord.strike == atm_strike,
            )
        )
        quoted = [iv for (iv,) in result.all() if iv is not None and iv > 0]
        if not quoted:
            return None
        return sum(quoted, Decimal("0")) / Decimal(len(quoted))


class SqlAlchemyDailyIvWriter:
    """Implements ``market_ingestion``'s ``DailyIvWriter`` port."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = SqlAlchemyDailyIvHistoryRepository(session)

    async def upsert_daily_iv(self, rows: list[SessionIv]) -> int:
        return await self._repo.upsert(
            [
                {
                    "symbol": row.symbol,
                    "session_date": row.session_date,
                    "atm_iv": row.atm_iv,
                    "future_close": row.future_close,
                    "captures": row.captures,
                    "source": row.source,
                }
                for row in rows
            ],
            now=datetime.now(UTC),
        )
