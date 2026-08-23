"""HUGIN call repository against real Postgres — append + recent round-trip."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest

from marketcompass.bootstrap.settings import DatabaseSettings
from marketcompass.contexts.hugin.domain.call import HuginCall
from marketcompass.contexts.hugin.domain.observation import Bias
from marketcompass.infrastructure.persistence.postgresql.repositories.hugin.call_repository import (
    SqlAlchemyHuginCallRepository,
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


def _call(zone: str) -> HuginCall:
    return HuginCall(
        instrument="NIFTY",
        bias=Bias.BULLISH,
        target_zone=zone,
        conviction=Decimal("0.7"),
        track_hit_rate=Decimal("0.55"),
        rationale="VWAP reclaim + PCR flip",
        entry="23,050",
        stop="22,950",
        target1="23,200",
    )


async def test_append_then_recent_newest_first(database: Database) -> None:
    repo = SqlAlchemyHuginCallRepository(database)
    tenant = TenantId(uuid.uuid4())

    await repo.append(tenant, _call("23,600-23,650"))
    await repo.append(tenant, _call("23,700-23,750"))

    recent = await repo.recent(tenant, "NIFTY", limit=10)
    assert len(recent) == 2
    assert recent[0].target_zone == "23,700-23,750"  # newest first
    assert recent[0].conviction == Decimal("0.7")
    assert recent[0].track_hit_rate == Decimal("0.55")
    assert recent[0].entry == "23,050"
    assert recent[0].id is not None
