"""Ports the AI-settings use cases depend on."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from chartnexus.contexts.ai_settings.domain.aggregate import AiSettings
from chartnexus.shared_kernel.types.identifiers import UserId


@runtime_checkable
class AiSettingsRepository(Protocol):
    async def find(self, user_id: UserId) -> AiSettings | None:
        """The user's stored AI settings, or ``None`` if they have none."""
        ...

    async def upsert(self, settings: AiSettings) -> None:
        """Insert or update the single row for this user."""
        ...


@runtime_checkable
class SecretCipher(Protocol):
    """Authenticated encryption for the API key at rest.

    ``aad`` is authenticated but not encrypted. Callers pass the location a value
    belongs to — user, provider, column — so a ciphertext copied into a different
    row fails to decrypt instead of being accepted. It must match between encrypt
    and decrypt. Satisfied structurally by ``AesGcmCipher``.
    """

    def encrypt(self, plaintext: str, *, aad: str | None = None) -> str: ...

    def decrypt(self, ciphertext: str, *, aad: str | None = None) -> str: ...


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...


@runtime_checkable
class UnitOfWork(Protocol):
    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
