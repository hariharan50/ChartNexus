"""Channel-connection repository — the encryption boundary for channel secrets.

Owns its own sessions (like the HUGIN stores) because it is read from the
request-less delivery worker as well as the settings API. The channel secret (a
bot token) is AES-256-GCM ciphertext at rest, bound by AAD to its (user, channel,
column) slot so it cannot be replayed into another row. An undecryptable secret is
treated as absent — the connection reads as not-configured and the user reconnects,
never a 500 (mirrors ``ai_settings``).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete as sql_delete, select

from marketcompass.contexts.messaging.application.ports import (
    ChannelConnectionRepository,
    SecretCipher,
)
from marketcompass.contexts.messaging.domain.channel import Channel, ChannelConnection
from marketcompass.infrastructure.persistence.postgresql.models.messaging.channel_connection import (
    ChannelConnectionRecord,
)
from marketcompass.infrastructure.persistence.postgresql.session import Database
from marketcompass.infrastructure.security.encryption import DecryptionError
from marketcompass.shared_kernel.types.identifiers import MessagingChannelId, TenantId, UserId


class SqlAlchemyChannelConnectionRepository:
    """Implements the ``ChannelConnectionRepository`` port."""

    def __init__(self, database: Database, cipher: SecretCipher) -> None:
        self._db = database
        self._cipher = cipher

    async def find(self, user_id: UserId, channel: Channel) -> ChannelConnection | None:
        stmt = select(ChannelConnectionRecord).where(
            ChannelConnectionRecord.user_id == user_id,
            ChannelConnectionRecord.channel == channel.value,
        )
        async with self._db.read_session() as session:
            record = (await session.execute(stmt)).scalar_one_or_none()
            return self._to_domain(record) if record else None

    async def find_all(self, user_id: UserId) -> tuple[ChannelConnection, ...]:
        stmt = (
            select(ChannelConnectionRecord)
            .where(ChannelConnectionRecord.user_id == user_id)
            .order_by(ChannelConnectionRecord.channel.asc())
        )
        async with self._db.read_session() as session:
            records = (await session.execute(stmt)).scalars().all()
            return tuple(self._to_domain(r) for r in records)

    async def upsert(self, connection: ChannelConnection) -> None:
        async with self._db.session() as session:
            record = await session.get(ChannelConnectionRecord, connection.id)
            secret_enc = self._encrypt(connection)
            if record is None:
                session.add(
                    ChannelConnectionRecord(
                        id=connection.id,
                        user_id=connection.user_id,
                        tenant_id=connection.tenant_id,
                        channel=connection.channel.value,
                        secret_enc=secret_enc,
                        target=connection.target,
                        label=connection.label,
                        verified=connection.verified,
                        enabled=connection.enabled,
                    )
                )
            else:
                record.secret_enc = secret_enc
                record.target = connection.target
                record.label = connection.label
                record.verified = connection.verified
                record.enabled = connection.enabled

    async def delete(self, user_id: UserId, channel: Channel) -> None:
        stmt = sql_delete(ChannelConnectionRecord).where(
            ChannelConnectionRecord.user_id == user_id,
            ChannelConnectionRecord.channel == channel.value,
        )
        async with self._db.session() as session:
            await session.execute(stmt)

    # -- mapping ------------------------------------------------------------

    def _encrypt(self, connection: ChannelConnection) -> str | None:
        if not connection.secret:
            return None
        return self._cipher.encrypt(
            connection.secret, aad=_aad(connection.user_id, connection.channel)
        )

    def _decrypt(self, record: ChannelConnectionRecord) -> str:
        if not record.secret_enc:
            return ""
        try:
            return self._cipher.decrypt(
                record.secret_enc,
                aad=_aad(UserId(record.user_id), Channel(record.channel)),
            )
        except DecryptionError:
            return ""

    def _to_domain(self, record: ChannelConnectionRecord) -> ChannelConnection:
        return ChannelConnection(
            id=MessagingChannelId(record.id),
            user_id=UserId(record.user_id),
            tenant_id=TenantId(record.tenant_id),
            channel=Channel(record.channel),
            secret=self._decrypt(record),
            target=record.target,
            label=record.label,
            verified=record.verified,
            enabled=record.enabled,
            created_at=_aware(record.created_at),
            updated_at=_aware(record.updated_at),
        )


def _aad(user_id: UserId, channel: Channel) -> str:
    return f"messaging:{user_id}:{channel.value}:secret"


def _aware(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


# Structural check: the repository satisfies the port.
_: type[ChannelConnectionRepository] = SqlAlchemyChannelConnectionRepository
