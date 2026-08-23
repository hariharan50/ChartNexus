"""MME100 repositories against real Postgres.

Pins the enrollment opt-in (unknown tenant off; set/toggle upserts on one row) and
the briefing store (save then read-today round-trips; re-saving the same day
replaces rather than duplicates).

Requires the compose stack + migrations applied.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta, timezone

import pytest

from marketcompass.bootstrap.settings import DatabaseSettings
from marketcompass.contexts.mme100.domain.briefing import Briefing
from marketcompass.infrastructure.persistence.postgresql.repositories.mme100.briefing_repository import (
    SqlAlchemyMme100BriefingRepository,
)
from marketcompass.infrastructure.persistence.postgresql.repositories.mme100.enrollment_repository import (
    SqlAlchemyMme100EnrollmentRepository,
)
from marketcompass.infrastructure.persistence.postgresql.session import Database
from marketcompass.shared_kernel.types.identifiers import TenantId

pytestmark = pytest.mark.integration

ASYNC_DSN = "postgresql+asyncpg://marketcompass:marketcompass@localhost:5433/marketcompass"
_IST = timezone(timedelta(hours=5, minutes=30))


@pytest.fixture
async def database() -> AsyncIterator[Database]:
    db = Database.create(DatabaseSettings(url=ASYNC_DSN), use_pool=False)  # type: ignore[arg-type]
    yield db
    await db.dispose()


async def test_enrollment_unknown_tenant_is_off_by_default(database: Database) -> None:
    repo = SqlAlchemyMme100EnrollmentRepository(database)
    assert await repo.is_enabled(TenantId(uuid.uuid4())) is False


async def test_enrollment_set_on_then_off_upserts(database: Database) -> None:
    repo = SqlAlchemyMme100EnrollmentRepository(database)
    tenant = TenantId(uuid.uuid4())

    await repo.set_enabled(tenant, True)
    assert await repo.is_enabled(tenant) is True

    await repo.set_enabled(tenant, False)
    assert await repo.is_enabled(tenant) is False  # same row


async def test_briefing_save_and_read_today_round_trips(database: Database) -> None:
    repo = SqlAlchemyMme100BriefingRepository(database)
    tenant = TenantId(uuid.uuid4())
    today = datetime.now(UTC).astimezone(_IST).date()

    await repo.save(
        tenant,
        Briefing(
            trading_day=today,
            instruments=("NIFTY", "BANKNIFTY"),
            markdown="## NIFTY\n\nConstructive.",
            source="live",
        ),
    )

    got = await repo.today(tenant)
    assert got is not None
    assert got.instruments == ("NIFTY", "BANKNIFTY")
    assert "Constructive." in got.markdown
    assert got.source == "live"
    assert got.created_at is not None


async def test_briefing_resave_same_day_replaces(database: Database) -> None:
    repo = SqlAlchemyMme100BriefingRepository(database)
    tenant = TenantId(uuid.uuid4())
    today = datetime.now(UTC).astimezone(_IST).date()

    await repo.save(
        tenant,
        Briefing(trading_day=today, instruments=("NIFTY",), markdown="first", source="live"),
    )
    await repo.save(
        tenant,
        Briefing(trading_day=today, instruments=("NIFTY",), markdown="second", source="mock"),
    )

    got = await repo.today(tenant)
    assert got is not None
    assert got.markdown == "second"  # replaced, not duplicated
    assert got.source == "mock"
