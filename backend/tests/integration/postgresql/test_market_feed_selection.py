"""Which broker connection the market-wide jobs run on.

Ingest, the futures OI sweep, the futures board and Trade Buddy all resolve
their feed through ``find_market_feed``. It prefers Kite, but a Kite token dies
at 06:00 IST while its row stays ``active`` until someone reconnects — so the
selection has to skip a connection past its known expiry, or a dead Kite row
shadows a working FYERS one and every shared job sits on mock data until the
morning reconnect.

The query spans every tenant, and a developer database holds real
connections, so the rows here are stamped decades ahead: they outrank anything
real on ``connected_at``, and ``now`` is pinned past them. Everything runs in
one transaction that is rolled back.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from chartnexus.contexts.broker_connections.domain.value_objects import BrokerName
from chartnexus.infrastructure.persistence.postgresql.repositories.integration.broker_connection_repository import (
    SqlAlchemyBrokerConnectionRepository,
)
from chartnexus.infrastructure.security.encryption import AesGcmCipher

pytestmark = pytest.mark.integration

ASYNC_DSN = "postgresql+asyncpg://chartnexus:chartnexus@localhost:5433/chartnexus"

# Far enough ahead that no real connection is newer, or unexpired, at NOW.
CONNECTED = datetime(2099, 1, 1, 9, 0, tzinfo=UTC)
NOW = datetime(2099, 1, 2, 10, 0, tzinfo=UTC)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(ASYNC_DSN)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
        await db_session.rollback()
    await engine.dispose()


async def _connect(
    session: AsyncSession,
    broker: BrokerName,
    *,
    expires_at: datetime | None,
    connected_at: datetime = CONNECTED,
) -> uuid.UUID:
    """An active connection for a fresh tenant (one active broker per tenant)."""
    row_id = uuid.uuid4()
    await session.execute(
        sa.text(
            "insert into broker_connections "
            "(id, tenant_id, broker, status, access_token_enc, connected_at, expires_at) "
            "values (:id, :tenant, :broker, 'active', 'placeholder', :connected, :expires)"
        ),
        {
            "id": row_id,
            "tenant": uuid.uuid4(),
            "broker": broker.value,
            "connected": connected_at,
            "expires": expires_at,
        },
    )
    return row_id


def _repo(session: AsyncSession) -> SqlAlchemyBrokerConnectionRepository:
    # The tokens are placeholders; an undecryptable value reads as absent,
    # which is all this test needs — it asserts on which row, not its secrets.
    return SqlAlchemyBrokerConnectionRepository(session, AesGcmCipher.derive("x" * 48))


async def test_an_unexpired_kite_connection_is_preferred_over_fyers(
    session: AsyncSession,
) -> None:
    kite = await _connect(session, BrokerName.KITE, expires_at=NOW + timedelta(hours=1))
    await _connect(
        session, BrokerName.FYERS, expires_at=None, connected_at=CONNECTED + timedelta(minutes=5)
    )

    chosen = await _repo(session).find_market_feed(now=NOW)

    assert chosen is not None
    assert chosen.id == kite


async def test_a_lapsed_kite_token_gives_way_to_a_working_fyers_connection(
    session: AsyncSession,
) -> None:
    # The 06:00 IST case: Kite's row is still `active`, its token is not.
    await _connect(session, BrokerName.KITE, expires_at=NOW - timedelta(hours=4))
    fyers = await _connect(session, BrokerName.FYERS, expires_at=None)

    chosen = await _repo(session).find_market_feed(now=NOW)

    assert chosen is not None
    assert chosen.id == fyers
    assert chosen.broker is BrokerName.FYERS


async def test_a_kite_connection_expiring_exactly_now_is_skipped(session: AsyncSession) -> None:
    # Same boundary as BrokerConnection.is_expired: `now >= expires_at`.
    await _connect(session, BrokerName.KITE, expires_at=NOW)
    fyers = await _connect(session, BrokerName.FYERS, expires_at=None)

    chosen = await _repo(session).find_market_feed(now=NOW)

    assert chosen is not None
    assert chosen.id == fyers
