"""Broker connection repository.

The encryption boundary: the aggregate holds plaintext secrets in memory, the
row holds only ciphertext, and this class is the only place that converts
between them.

Each ciphertext is bound to where it lives — tenant, broker, column — as
authenticated data. Someone who can write to ``broker_connections`` therefore
cannot lift one tenant's token into another tenant's row, or slide a refresh
token into the access-token column, because the tag stops verifying.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chartnexus.contexts.broker_connections.application.ports import TokenCipher
from chartnexus.contexts.broker_connections.domain.connection import BrokerConnection
from chartnexus.contexts.broker_connections.domain.value_objects import (
    BrokerCredentials,
    BrokerName,
    BrokerProfile,
    ConnectionStatus,
)
from chartnexus.infrastructure.persistence.postgresql.models.integration.broker_connection import (
    BrokerConnectionRecord,
)
from chartnexus.infrastructure.security.encryption import DecryptionError
from chartnexus.shared_kernel.types.identifiers import BrokerConnectionId, TenantId


class SqlAlchemyBrokerConnectionRepository:
    """Implements the ``BrokerConnectionRepository`` port."""

    def __init__(self, session: AsyncSession, cipher: TokenCipher) -> None:
        self._session = session
        self._cipher = cipher

    async def find(self, tenant_id: TenantId, broker: BrokerName) -> BrokerConnection | None:
        result = await self._session.execute(
            select(BrokerConnectionRecord).where(
                BrokerConnectionRecord.tenant_id == tenant_id,
                BrokerConnectionRecord.broker == broker.value,
            )
        )
        record = result.scalar_one_or_none()
        return self._to_domain(record) if record else None

    async def find_any_active(self, broker: BrokerName) -> BrokerConnection | None:
        result = await self._session.execute(
            select(BrokerConnectionRecord)
            .where(
                BrokerConnectionRecord.broker == broker.value,
                BrokerConnectionRecord.status == ConnectionStatus.ACTIVE.value,
            )
            .order_by(BrokerConnectionRecord.connected_at.desc().nulls_last())
            .limit(1)
        )
        record = result.scalar_one_or_none()
        return self._to_domain(record) if record else None

    async def add(self, connection: BrokerConnection) -> None:
        self._session.add(
            BrokerConnectionRecord(
                id=connection.id,
                tenant_id=connection.tenant_id,
                broker=connection.broker.value,
                app_id=connection.credentials.app_id if connection.credentials else None,
                app_secret_enc=self._encrypt(
                    connection.credentials.secret if connection.credentials else None,
                    connection=connection,
                    field="app_secret",
                ),
                access_token_enc=self._encrypt(
                    connection.access_token, connection=connection, field="access_token"
                ),
                refresh_token_enc=self._encrypt(
                    connection.refresh_token, connection=connection, field="refresh_token"
                ),
                status=connection.status.value,
                profile=connection.profile.as_dict() if connection.profile else None,
                connected_at=connection.connected_at,
                revoked_at=connection.revoked_at,
                expires_at=connection.expires_at,
                last_validated_at=connection.last_validated_at,
                last_error=connection.last_error,
            )
        )
        await self._session.flush()

    async def update(self, connection: BrokerConnection) -> None:
        record = await self._session.get(BrokerConnectionRecord, connection.id)
        if record is None:
            msg = f"broker connection {connection.id} disappeared between load and save"
            raise LookupError(msg)

        record.app_id = connection.credentials.app_id if connection.credentials else None
        record.app_secret_enc = self._encrypt(
            connection.credentials.secret if connection.credentials else None,
            connection=connection,
            field="app_secret",
        )
        record.access_token_enc = self._encrypt(
            connection.access_token, connection=connection, field="access_token"
        )
        record.refresh_token_enc = self._encrypt(
            connection.refresh_token, connection=connection, field="refresh_token"
        )
        record.status = connection.status.value
        record.profile = connection.profile.as_dict() if connection.profile else None
        record.connected_at = connection.connected_at
        record.revoked_at = connection.revoked_at
        record.expires_at = connection.expires_at
        record.last_validated_at = connection.last_validated_at
        record.last_error = connection.last_error
        await self._session.flush()

    # -- mapping ------------------------------------------------------------

    def _encrypt(
        self, plaintext: str | None, *, connection: BrokerConnection, field: str
    ) -> str | None:
        if not plaintext:
            return None
        return self._cipher.encrypt(
            plaintext, aad=_aad(connection.tenant_id, connection.broker, field)
        )

    def _decrypt(
        self, ciphertext: str | None, *, record: BrokerConnectionRecord, field: str
    ) -> str | None:
        """Decrypt, treating an undecryptable value as absent.

        A rotated encryption key must not make the whole connection unreadable —
        the user should see "not connected" and be able to reconnect, rather
        than a 500 on every market data request. A failed tag check on a value
        that has been moved between rows lands here too, and is treated the
        same way: the credential is simply not there.
        """
        if not ciphertext:
            return None
        try:
            return self._cipher.decrypt(
                ciphertext,
                aad=_aad(TenantId(record.tenant_id), BrokerName(record.broker), field),
            )
        except DecryptionError:
            return None

    def _to_domain(self, record: BrokerConnectionRecord) -> BrokerConnection:
        secret = self._decrypt(record.app_secret_enc, record=record, field="app_secret")
        credentials = (
            BrokerCredentials(app_id=record.app_id, secret=secret)
            if record.app_id and secret
            else None
        )

        access_token = self._decrypt(record.access_token_enc, record=record, field="access_token")
        status = ConnectionStatus(record.status)
        if status is ConnectionStatus.ACTIVE and access_token is None:
            # The row says active but the token cannot be read — an encryption
            # key change. Present it as expired so the UI offers a reconnect.
            status = ConnectionStatus.EXPIRED

        profile = None
        if record.profile:
            profile = BrokerProfile(
                broker_user_id=str(record.profile.get("broker_user_id", "")),
                display_name=str(record.profile.get("display_name", "")),
                email=record.profile.get("email"),
            )

        return BrokerConnection(
            id=BrokerConnectionId(record.id),
            tenant_id=TenantId(record.tenant_id),
            broker=BrokerName(record.broker),
            status=status,
            credentials=credentials,
            access_token=access_token,
            refresh_token=self._decrypt(
                record.refresh_token_enc, record=record, field="refresh_token"
            ),
            profile=profile,
            connected_at=_aware(record.connected_at),
            revoked_at=_aware(record.revoked_at),
            expires_at=_aware(record.expires_at),
            last_validated_at=_aware(record.last_validated_at),
            last_error=record.last_error,
            # Not persisted: who clicked connect is an audit fact and belongs
            # in the audit context, not on this row.
            connected_by=None,
            created_at=_aware(record.created_at),
            updated_at=_aware(record.updated_at),
        )


def _aad(tenant_id: TenantId, broker: BrokerName, field: str) -> str:
    """The location a ciphertext is valid in.

    Row identity is deliberately not the primary key: a connection keeps its
    ``(tenant, broker)`` pair for life, so binding to that survives any
    row-level churn while still pinning the value to one tenant.
    """
    return f"broker_connections:{tenant_id}:{broker.value}:{field}"


def _aware(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)
