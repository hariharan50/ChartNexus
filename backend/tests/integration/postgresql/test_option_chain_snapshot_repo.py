"""Option-chain snapshot repository against real Postgres.

Covers what the unit tests cannot: that a snapshot and its rows round-trip
through the schema, that the reader orders and scopes by session date, and that
deleting a snapshot cascades to its rows.

Requires the compose stack:  docker compose -f deploy/compose/compose.yml up -d
and migrations applied:       uv run alembic upgrade head
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from marketcompass.contexts.market_ingestion.application.ports import (
    ChainRowToWrite,
    SnapshotToWrite,
)
from marketcompass.infrastructure.persistence.postgresql.repositories.market_data.option_chain_snapshot_repository import (
    SqlAlchemyOptionChainSnapshotRepository,
)

pytestmark = pytest.mark.integration

ASYNC_DSN = "postgresql+asyncpg://marketcompass:marketcompass@localhost:5433/marketcompass"
SESSION_DATE = date(2026, 8, 4)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(ASYNC_DSN)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with factory() as db_session:
        yield db_session
        await db_session.rollback()
    await engine.dispose()


def _snapshot(
    symbol: str,
    captured_at: datetime,
    *,
    source: str = "live",
    session_date: date = SESSION_DATE,
) -> SnapshotToWrite:
    return SnapshotToWrite(
        symbol=symbol,
        session_date=session_date,
        captured_at=captured_at,
        spot=Decimal("104.00"),
        source=source,
        rows=(
            ChainRowToWrite(
                Decimal("100"), "CE", oi=200, oi_change=10, volume=5, iv=Decimal("13.2")
            ),
            ChainRowToWrite(Decimal("100"), "PE", oi=400, oi_change=20, volume=7, iv=None),
        ),
        expiry="2026-08-07",
        lot_size=75,
        atm_strike=Decimal("100"),
        total_call_oi=200,
        total_put_oi=400,
        pcr_oi=Decimal("2.0000"),
        max_pain_strike=Decimal("100"),
    )


async def test_save_and_read_round_trip(session: AsyncSession) -> None:
    symbol = f"NIFTY-{uuid.uuid4().hex[:6]}"  # isolate from other runs' rows
    repo = SqlAlchemyOptionChainSnapshotRepository(session)

    await repo.save(_snapshot(symbol, datetime(2026, 8, 4, 4, 0, tzinfo=UTC)))
    await repo.save(_snapshot(symbol, datetime(2026, 8, 4, 4, 30, tzinfo=UTC)))
    await session.commit()

    day = await repo.snapshots_for(symbol, SESSION_DATE)
    assert len(day) == 2
    # Earliest first.
    assert day[0].captured_at < day[1].captured_at
    assert {len(snap.rows) for snap in day} == {2}
    # Nullable IV survives as NULL, not 0.
    ivs = {row.iv for row in day[0].rows}
    assert None in ivs

    latest = await repo.latest(symbol, SESSION_DATE)
    assert latest is not None
    assert latest.captured_at == day[1].captured_at


async def test_delete_cascades_to_rows(session: AsyncSession) -> None:
    symbol = f"BANKNIFTY-{uuid.uuid4().hex[:6]}"
    repo = SqlAlchemyOptionChainSnapshotRepository(session)
    await repo.save(_snapshot(symbol, datetime(2026, 8, 4, 4, 0, tzinfo=UTC)))
    await session.commit()

    snap = await repo.latest(symbol, SESSION_DATE)
    assert snap is not None
    await session.delete(snap)
    await session.commit()

    orphans = await session.execute(
        sa.text("select count(*) from option_chain_rows where snapshot_id = :sid"),
        {"sid": snap.id},
    )
    assert orphans.scalar_one() == 0


async def test_has_source_distinguishes_provenance(session: AsyncSession) -> None:
    # The seeder's guard against overwriting a real capture rests entirely on
    # this: if it cannot tell mock from live, the guard is decorative.
    symbol = f"NIFTY-{uuid.uuid4().hex[:6]}"
    repo = SqlAlchemyOptionChainSnapshotRepository(session)
    await repo.save(_snapshot(symbol, datetime(2026, 8, 4, 4, 0, tzinfo=UTC), source="mock"))
    await session.commit()

    assert await repo.has_source(symbol, SESSION_DATE, "mock") is True
    assert await repo.has_source(symbol, SESSION_DATE, "live") is False
    assert await repo.has_source(symbol, date(2026, 8, 3), "mock") is False


async def test_delete_session_only_touches_its_own_provenance(session: AsyncSession) -> None:
    # What makes `--replace` idempotent *and* safe: re-seeding a day that also
    # holds a real capture must leave the real one standing.
    symbol = f"NIFTY-{uuid.uuid4().hex[:6]}"
    repo = SqlAlchemyOptionChainSnapshotRepository(session)
    await repo.save(_snapshot(symbol, datetime(2026, 8, 4, 4, 0, tzinfo=UTC), source="mock"))
    await repo.save(_snapshot(symbol, datetime(2026, 8, 4, 4, 30, tzinfo=UTC), source="live"))
    await session.commit()

    removed = await repo.delete_session(symbol, SESSION_DATE, "mock")
    await session.commit()

    assert removed == 1
    survivors = await repo.snapshots_for(symbol, SESSION_DATE)
    assert [snap.source for snap in survivors] == ["live"]


async def test_prune_deletes_only_before_the_cutoff(session: AsyncSession) -> None:
    symbol = f"NIFTY-{uuid.uuid4().hex[:6]}"
    repo = SqlAlchemyOptionChainSnapshotRepository(session)
    for day in (date(2026, 8, 2), date(2026, 8, 3), date(2026, 8, 4)):
        await repo.save(
            _snapshot(
                symbol,
                datetime(day.year, day.month, day.day, 4, 0, tzinfo=UTC),
                session_date=day,
            )
        )
    await session.commit()

    deleted = await repo.delete_sessions_before(date(2026, 8, 3))
    await session.commit()

    # Strictly before: the cutoff date itself is kept.
    assert deleted >= 1
    assert await repo.snapshots_for(symbol, date(2026, 8, 2)) == []
    assert len(await repo.snapshots_for(symbol, date(2026, 8, 3))) == 1
    assert len(await repo.snapshots_for(symbol, SESSION_DATE)) == 1


async def test_prune_cascades_to_rows_and_terminates_past_one_batch(
    session: AsyncSession,
) -> None:
    # Two things at once, because they need the same expensive fixture: the
    # batch loop must terminate when there is more than one batch to delete,
    # and the child rows must go with their headers rather than being orphaned.
    symbol = f"NIFTY-{uuid.uuid4().hex[:6]}"
    old = date(2026, 7, 1)
    repo = SqlAlchemyOptionChainSnapshotRepository(session)
    for minute in range(12):
        await repo.save(
            _snapshot(symbol, datetime(2026, 7, 1, 4, minute, tzinfo=UTC), session_date=old)
        )
    await session.commit()

    ids = [snap.id for snap in await repo.snapshots_for(symbol, old)]
    assert len(ids) == 12

    # A batch size below the row count forces at least three passes.
    deleted = await repo.delete_sessions_before(date(2026, 7, 2), batch_size=5)
    await session.commit()

    assert deleted >= 12
    assert await repo.snapshots_for(symbol, old) == []
    orphans = await session.execute(
        sa.text("select count(*) from option_chain_rows where snapshot_id = any(:ids)"),
        {"ids": ids},
    )
    assert orphans.scalar_one() == 0
