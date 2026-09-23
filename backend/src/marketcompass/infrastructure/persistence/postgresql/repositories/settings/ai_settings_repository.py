"""User AI-settings repository.

The encryption boundary: the aggregate holds the plaintext API key in memory, the
row holds only ciphertext, and this class is the only place that converts between
them.

Each ciphertext is bound to where it lives — user, provider, column — as
authenticated data. Someone who can write to ``user_ai_settings`` therefore cannot
lift one user's key into another user's row, because the GCM tag stops verifying.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.ai_settings.application.ports import SecretCipher
from marketcompass.contexts.ai_settings.domain.aggregate import AiSettings
from marketcompass.contexts.ai_settings.domain.value_objects import LlmProvider
from marketcompass.infrastructure.persistence.postgresql.models.settings.user_ai_settings import (
    UserAiSettingsRecord,
)
from marketcompass.infrastructure.security.encryption import DecryptionError
from marketcompass.shared_kernel.types.identifiers import (
    AiSettingsId,
    TenantId,
    UserId,
)


class SqlAlchemyAiSettingsRepository:
    """Implements the ``AiSettingsRepository`` port."""

    def __init__(self, session: AsyncSession, cipher: SecretCipher) -> None:
        self._session = session
        self._cipher = cipher

    async def find(self, user_id: UserId) -> AiSettings | None:
        result = await self._session.execute(
            select(UserAiSettingsRecord).where(UserAiSettingsRecord.user_id == user_id)
        )
        record = result.scalar_one_or_none()
        return self._to_domain(record) if record else None

    async def upsert(self, settings: AiSettings) -> None:
        record = await self._session.get(UserAiSettingsRecord, settings.id)
        if record is None:
            self._session.add(
                UserAiSettingsRecord(
                    id=settings.id,
                    user_id=settings.user_id,
                    tenant_id=settings.tenant_id,
                    provider=settings.provider.value,
                    model=settings.model,
                    api_key_enc=self._encrypt(settings),
                )
            )
        else:
            record.provider = settings.provider.value
            record.model = settings.model
            record.api_key_enc = self._encrypt(settings)
        await self._session.flush()

    # -- mapping ------------------------------------------------------------

    def _encrypt(self, settings: AiSettings) -> str | None:
        if not settings.api_key:
            return None
        return self._cipher.encrypt(settings.api_key, aad=_aad(settings.user_id, settings.provider))

    def _decrypt(self, record: UserAiSettingsRecord) -> str | None:
        """Decrypt, treating an undecryptable value as absent.

        A rotated encryption key must not make the whole settings row unreadable —
        the user should see "not configured" and be able to re-enter their key,
        rather than a 500. A failed tag check on a value moved between rows lands
        here too, and is treated the same way: the key is simply not there.
        """
        if not record.api_key_enc:
            return None
        try:
            return self._cipher.decrypt(
                record.api_key_enc,
                aad=_aad(UserId(record.user_id), LlmProvider(record.provider)),
            )
        except DecryptionError:
            return None

    def _to_domain(self, record: UserAiSettingsRecord) -> AiSettings:
        return AiSettings(
            id=AiSettingsId(record.id),
            user_id=UserId(record.user_id),
            tenant_id=TenantId(record.tenant_id),
            provider=LlmProvider(record.provider),
            model=record.model,
            api_key=self._decrypt(record),
            created_at=_aware(record.created_at),
            updated_at=_aware(record.updated_at),
        )


def _aad(user_id: UserId, provider: LlmProvider) -> str:
    """The location a ciphertext is valid in.

    Bound to ``(user, provider)`` so a key stored for one user can never decrypt
    under another user's row, and a key saved under one provider is not accepted
    after the provider is switched.
    """
    return f"ai_settings:{user_id}:{provider.value}:api_key"


def _aware(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)
