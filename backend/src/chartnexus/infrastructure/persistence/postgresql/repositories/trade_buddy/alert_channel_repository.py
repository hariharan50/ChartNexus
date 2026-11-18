"""Alert-channel repository — the encryption boundary for Trade Buddy's channels.

Owns its own sessions, like its messaging counterpart, because it is read from
the request-less watcher as well as from the settings API.

**Both halves of a connection are encrypted.** The secret (Telegram bot token,
CallMeBot API key) and the target (Telegram chat id, WhatsApp phone number) are
AES-256-GCM ciphertext, each bound by AAD to its own (user, channel, column)
slot, so a value cannot be replayed into another user's row or into the other
column. **The AAD is prefixed `trade_buddy:`, not `messaging:`** — that is what
stops a briefing bot's token being lifted into the alerts table and decrypting
there, which is the whole reason the two live in separate tables.

An undecryptable value reads as absent rather than raising: the connection
shows as not-configured (or not-linked) and the user reconnects, which is the
same choice ``messaging`` and ``ai_settings`` make and for the same reason — a
rotated encryption key should cost a reconnect, not a 500 on every page load.

Every read is scoped to one user. There is deliberately no "any user's
connection" query: Trade Buddy is per-user, and the watcher asks for the
channels of the user whose levels it is watching.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import delete as sql_delete, select

from chartnexus.contexts.trade_buddy.application.ports import SecretCipher
from chartnexus.contexts.trade_buddy.domain.channel import AlertChannel, AlertConnection
from chartnexus.infrastructure.persistence.postgresql.models.trade_buddy.alert_channel import (
    AlertChannelRecord,
)
from chartnexus.infrastructure.persistence.postgresql.session import Database
from chartnexus.infrastructure.security.encryption import DecryptionError
from chartnexus.shared_kernel.types.identifiers import TenantId, UserId

_Field = Literal["secret", "target"]


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

    async def find_ready(self, user_id: UserId) -> tuple[AlertConnection, ...]:
        """This user's channels that can deliver right now.

        Filtered after decryption as well as by the flags: a row whose secret or
        target will not decrypt is not ready, whatever the flags say, and
        handing it to a notifier would send with an empty token.
        """
        stmt = (
            select(AlertChannelRecord)
            .where(
                AlertChannelRecord.user_id == user_id,
                AlertChannelRecord.enabled.is_(True),
                AlertChannelRecord.verified.is_(True),
                AlertChannelRecord.target_enc.isnot(None),
            )
            .order_by(AlertChannelRecord.channel.asc())
        )
        async with self._db.read_session() as session:
            records = (await session.execute(stmt)).scalars().all()
            connections = (self._to_domain(r) for r in records)
            return tuple(c for c in connections if c.ready)

    async def upsert(self, connection: AlertConnection) -> None:
        async with self._db.session() as session:
            record = await session.get(AlertChannelRecord, connection.id)
            secret_enc = self._encrypt(connection, "secret", connection.secret)
            target_enc = self._encrypt(connection, "target", connection.target)
            if record is None:
                session.add(
                    AlertChannelRecord(
                        id=connection.id,
                        user_id=connection.user_id,
                        tenant_id=connection.tenant_id,
                        channel=connection.channel.value,
                        secret_enc=secret_enc,
                        target_enc=target_enc,
                        label=connection.label,
                        verified=connection.verified,
                        enabled=connection.enabled,
                    )
                )
            else:
                record.secret_enc = secret_enc
                record.target_enc = target_enc
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

    def _encrypt(self, connection: AlertConnection, field: _Field, value: str | None) -> str | None:
        if not value:
            return None
        return self._cipher.encrypt(value, aad=_aad(connection.user_id, connection.channel, field))

    def _decrypt(self, record: AlertChannelRecord, field: _Field, ciphertext: str | None) -> str:
        if not ciphertext:
            return ""
        try:
            return self._cipher.decrypt(
                ciphertext,
                aad=_aad(UserId(record.user_id), AlertChannel(record.channel), field),
            )
        except DecryptionError:
            return ""

    def _to_domain(self, record: AlertChannelRecord) -> AlertConnection:
        return AlertConnection(
            id=record.id,
            user_id=UserId(record.user_id),
            tenant_id=TenantId(record.tenant_id),
            channel=AlertChannel(record.channel),
            secret=self._decrypt(record, "secret", record.secret_enc),
            # An undecryptable target reads as "not linked", never as a value.
            target=self._decrypt(record, "target", record.target_enc) or None,
            label=record.label,
            verified=record.verified,
            enabled=record.enabled,
            created_at=_aware(record.created_at),
            updated_at=_aware(record.updated_at),
        )


def _aad(user_id: UserId, channel: AlertChannel, field: _Field) -> str:
    """Bind the ciphertext to its slot — user, channel *and* column.

    The `trade_buddy:` prefix is load-bearing: it is what makes a token stored
    for the briefing bot fail to decrypt if it is ever moved into this table.
    The column suffix stops a target being swapped into the secret column.
    The migration that introduced ``target_enc`` writes the same format.
    """
    return f"trade_buddy:{user_id}:{channel.value}:{field}"


def _aware(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)
