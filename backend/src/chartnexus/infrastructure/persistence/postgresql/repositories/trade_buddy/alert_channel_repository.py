"""Alert-channel repository — the encryption boundary for Trade Buddy's bot token.

Owns its own sessions, like its messaging counterpart, because it is read from
the request-less watcher as well as from the settings API.

The secret is AES-256-GCM ciphertext at rest, bound by AAD to its (user,
channel, column) slot so a row cannot be replayed into another. **The AAD is
prefixed `trade_buddy:`, not `messaging:`** — that is what stops a briefing
bot's token being lifted into the alerts table and decrypting there, which is
the whole reason the two live in separate tables.

An undecryptable secret reads as absent rather than raising: the connection
shows as not-configured and the user reconnects, which is the same choice
``messaging`` and ``ai_settings`` make and for the same reason — a rotated
encryption key should cost a reconnect, not a 500 on every page load.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete as sql_delete, select

from chartnexus.contexts.trade_buddy.application.ports import SecretCipher
from chartnexus.contexts.trade_buddy.domain.channel import AlertChannel, AlertConnection
from chartnexus.infrastructure.persistence.postgresql.models.trade_buddy.alert_channel import (
    AlertChannelRecord,
)
from chartnexus.infrastructure.persistence.postgresql.session import Database
from chartnexus.infrastructure.security.encryption import DecryptionError
from chartnexus.shared_kernel.types.identifiers import TenantId, UserId


class SqlAlchemyAlertChannelRepository:
    """Implements the ``AlertChannelRepository`` port."""

    def __init__(self, database: Database, cipher: SecretCipher) -> None:
        self._db = database
        self._cipher = cipher

    async def find(self, user_id: UserId, channel: AlertChannel) -> AlertConnection | None:
        stmt = select(AlertChannelRecord).where(
            AlertChannelRecord.user_id == user_id,
            AlertChannelRecord.channel == channel.value,
        )
        async with self._db.read_session() as session:
            record = (await session.execute(stmt)).scalar_one_or_none()
            return self._to_domain(record) if record else None

    async def find_all(self, user_id: UserId) -> tuple[AlertConnection, ...]:
        stmt = (
            select(AlertChannelRecord)
            .where(AlertChannelRecord.user_id == user_id)
            .order_by(AlertChannelRecord.channel.asc())
        )
        async with self._db.read_session() as session:
            records = (await session.execute(stmt)).scalars().all()
            return tuple(self._to_domain(r) for r in records)

    async def find_any_ready(self, channel: AlertChannel) -> AlertConnection | None:
        """Any one user's ready connection for a channel.

        The watcher has no request and therefore no user. This is a
        single-operator tool, so one ready connection is the answer — the same
        shape as ``find_any_active`` on the broker repository, and for the same
        reason: the thing being delivered is not about a particular tenant.
        """
        stmt = (
            select(AlertChannelRecord)
            .where(
                AlertChannelRecord.channel == channel.value,
                AlertChannelRecord.enabled.is_(True),
                AlertChannelRecord.verified.is_(True),
                AlertChannelRecord.target.isnot(None),
            )
            .order_by(AlertChannelRecord.created_at.asc())
            .limit(1)
        )
        async with self._db.read_session() as session:
            record = (await session.execute(stmt)).scalar_one_or_none()
            if record is None:
                return None
            connection = self._to_domain(record)
            # A row whose secret will not decrypt is not ready, whatever the
            # flags say. Returning it would send with an empty token.
            return connection if connection.ready else None

    async def upsert(self, connection: AlertConnection) -> None:
        async with self._db.session() as session:
            record = await session.get(AlertChannelRecord, connection.id)
            secret_enc = self._encrypt(connection)
            if record is None:
                session.add(
                    AlertChannelRecord(
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

    async def delete(self, user_id: UserId, channel: AlertChannel) -> None:
        stmt = sql_delete(AlertChannelRecord).where(
            AlertChannelRecord.user_id == user_id,
            AlertChannelRecord.channel == channel.value,
        )
        async with self._db.session() as session:
            await session.execute(stmt)

    # -- mapping ------------------------------------------------------------

    def _encrypt(self, connection: AlertConnection) -> str | None:
        if not connection.secret:
            return None
        return self._cipher.encrypt(
            connection.secret, aad=_aad(connection.user_id, connection.channel)
        )

    def _decrypt(self, record: AlertChannelRecord) -> str:
        if not record.secret_enc:
            return ""
        try:
            return self._cipher.decrypt(
                record.secret_enc,
                aad=_aad(UserId(record.user_id), AlertChannel(record.channel)),
            )
        except DecryptionError:
            return ""

    def _to_domain(self, record: AlertChannelRecord) -> AlertConnection:
        return AlertConnection(
            id=record.id,
            user_id=UserId(record.user_id),
            tenant_id=TenantId(record.tenant_id),
            channel=AlertChannel(record.channel),
            secret=self._decrypt(record),
            target=record.target,
            label=record.label,
            verified=record.verified,
            enabled=record.enabled,
            created_at=_aware(record.created_at),
            updated_at=_aware(record.updated_at),
        )


def _aad(user_id: UserId, channel: AlertChannel) -> str:
    """Bind the ciphertext to its slot.

    The `trade_buddy:` prefix is load-bearing: it is what makes a token stored
    for the briefing bot fail to decrypt if it is ever moved into this table.
    """
    return f"trade_buddy:{user_id}:{channel.value}:secret"


def _aware(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)
