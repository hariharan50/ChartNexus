"""Messaging channel repository against real Postgres.

Pins the encryption boundary (round-trip, undecryptable-⇒-absent) and the
one-row-per-(user, channel) upsert. Requires the compose stack + migrations.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from marketcompass.bootstrap.settings import DatabaseSettings
from marketcompass.contexts.messaging.domain.channel import Channel, ChannelConnection
from marketcompass.infrastructure.persistence.postgresql.repositories.messaging.channel_repository import (
    SqlAlchemyChannelConnectionRepository,
)
from marketcompass.infrastructure.persistence.postgresql.session import Database
from marketcompass.infrastructure.security.encryption import AesGcmCipher
from marketcompass.shared_kernel.types.identifiers import TenantId, UserId

pytestmark = pytest.mark.integration

ASYNC_DSN = "postgresql+asyncpg://marketcompass:marketcompass@localhost:5433/marketcompass"
_SECRET = "unit-test-encryption-secret-value-at-least-32-bytes-long!!"
_TOKEN = "123456789:AAqwertyuiopasdfghjklzxcvbnm12345678"


def _cipher(secret: str = _SECRET) -> AesGcmCipher:
    return AesGcmCipher.derive(secret, purpose="messaging-credentials")


@pytest.fixture
async def database() -> AsyncIterator[Database]:
    db = Database.create(DatabaseSettings(url=ASYNC_DSN), use_pool=False)  # type: ignore[arg-type]
    yield db
    await db.dispose()


def _conn(user_id: UserId) -> ChannelConnection:
    now = datetime(2026, 8, 23, tzinfo=UTC)
    conn = ChannelConnection.create(
        user_id=user_id,
        tenant_id=TenantId(uuid.uuid4()),
        channel=Channel.TELEGRAM,
        secret=_TOKEN,
        label="@bot",
        now=now,
    )
    conn.link_target("555", now)
    return conn


async def test_round_trip_decrypts_the_secret(database: Database) -> None:
    repo = SqlAlchemyChannelConnectionRepository(database, _cipher())
    user = UserId(uuid.uuid4())
    await repo.upsert(_conn(user))

    got = await repo.find(user, Channel.TELEGRAM)
    assert got is not None
    assert got.secret == _TOKEN  # decrypted
    assert got.target == "555"
    assert got.label == "@bot"
    assert got.ready is True


async def test_upsert_is_one_row_per_user_channel(database: Database) -> None:
    repo = SqlAlchemyChannelConnectionRepository(database, _cipher())
    user = UserId(uuid.uuid4())
    conn = _conn(user)
    await repo.upsert(conn)
    conn.set_enabled(False, conn.updated_at)  # type: ignore[arg-type]
    await repo.upsert(conn)

    rows = await repo.find_all(user)
    assert len(rows) == 1
    assert rows[0].enabled is False


async def test_undecryptable_secret_reads_as_absent(database: Database) -> None:
    user = UserId(uuid.uuid4())
    await SqlAlchemyChannelConnectionRepository(database, _cipher()).upsert(_conn(user))

    # A different secret ⇒ the GCM tag won't verify ⇒ the secret is treated as
    # absent (the user reconnects), never a crash.
    other = SqlAlchemyChannelConnectionRepository(
        database, _cipher("a-different-secret-value-32-bytes-minimum!!")
    )
    got = await other.find(user, Channel.TELEGRAM)
    assert got is not None
    assert got.secret == ""
    assert got.configured is False


async def test_delete_removes_the_row(database: Database) -> None:
    repo = SqlAlchemyChannelConnectionRepository(database, _cipher())
    user = UserId(uuid.uuid4())
    await repo.upsert(_conn(user))
    await repo.delete(user, Channel.TELEGRAM)
    assert await repo.find(user, Channel.TELEGRAM) is None
