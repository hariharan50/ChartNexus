"""Report enrollment repository against real Postgres.

Requires the compose stack + migrations applied.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest

from marketcompass.bootstrap.settings import DatabaseSettings
from marketcompass.infrastructure.persistence.postgresql.repositories.report.enrollment_repository import (
    SqlAlchemyReportEnrollmentRepository,
)
from marketcompass.infrastructure.persistence.postgresql.session import Database
from marketcompass.shared_kernel.types.identifiers import TenantId

pytestmark = pytest.mark.integration

ASYNC_DSN = "postgresql+asyncpg://marketcompass:marketcompass@localhost:5433/marketcompass"


@pytest.fixture
async def database() -> AsyncIterator[Database]:
    db = Database.create(DatabaseSettings(url=ASYNC_DSN), use_pool=False)  # type: ignore[arg-type]
    yield db
    await db.dispose()


async def test_unknown_tenant_is_off(database: Database) -> None:
    repo = SqlAlchemyReportEnrollmentRepository(database)
    assert await repo.is_enabled(TenantId(uuid.uuid4())) is False


async def test_set_on_then_off_upserts(database: Database) -> None:
    repo = SqlAlchemyReportEnrollmentRepository(database)
    tenant = TenantId(uuid.uuid4())
    await repo.set_enabled(tenant, True)
    assert await repo.is_enabled(tenant) is True
    await repo.set_enabled(tenant, False)
    assert await repo.is_enabled(tenant) is False
