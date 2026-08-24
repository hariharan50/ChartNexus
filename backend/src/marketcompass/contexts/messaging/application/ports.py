"""Ports the messaging use cases depend on.

* ``ChannelConnectionRepository`` — persistence for the per-(user, channel) row.
* ``SecretCipher`` — authenticated encryption of the channel secret at rest (same
  Protocol shape as ai_settings; satisfied by ``AesGcmCipher``).
* ``MessageSenderPort`` — one per channel. Verifies credentials, resolves a
  delivery target, and sends text. Satisfied by ``TelegramSender`` (and later
  ``WhatsAppSender``) in ``infrastructure/notifications``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from marketcompass.contexts.messaging.domain.channel import Channel, ChannelConnection
from marketcompass.shared_kernel.types.identifiers import UserId


@dataclass(frozen=True, slots=True)
class ChannelIdentity:
    """What a channel reports about itself when credentials are verified — e.g. the
    Telegram bot's @username. Display only."""

    label: str


@runtime_checkable
class ChannelConnectionRepository(Protocol):
    """Persistence for the per-(user, channel) row.

    Owns its own sessions and commits on writes — the same shape as the HUGIN
    stores — because it is read from the request-less delivery worker as well as
    the request-scoped settings API.
    """

    async def find(self, user_id: UserId, channel: Channel) -> ChannelConnection | None:
        """The user's connection for one channel, or ``None``."""
        ...

    async def find_all(self, user_id: UserId) -> tuple[ChannelConnection, ...]:
        """Every channel the user has a row for, in a stable order."""
        ...

    async def upsert(self, connection: ChannelConnection) -> None:
        """Insert or update the single row for this (user, channel); commits."""
        ...

    async def delete(self, user_id: UserId, channel: Channel) -> None:
        """Remove the user's connection for a channel; commits. Idempotent."""
        ...


@runtime_checkable
class SecretCipher(Protocol):
    def encrypt(self, plaintext: str, *, aad: str | None = None) -> str: ...

    def decrypt(self, ciphertext: str, *, aad: str | None = None) -> str: ...


@runtime_checkable
class MessageSenderPort(Protocol):
    @property
    def channel(self) -> Channel:
        """Which channel this sender speaks."""
        ...

    async def verify(self, secret: str) -> ChannelIdentity:
        """Confirm the credentials with the provider; return its self-description.

        Raises ``ChannelVerificationError`` when the provider rejects them.
        """
        ...

    async def detect_target(self, secret: str) -> str | None:
        """Resolve a delivery target from recent activity (e.g. the chat id of the
        last person who messaged the bot), or ``None`` if none is found yet."""
        ...

    async def send(self, secret: str, target: str, text: str) -> None:
        """Deliver ``text`` to ``target``. Raises ``MessageSendError`` on failure."""
        ...

    async def send_document(
        self, secret: str, target: str, *, filename: str, content: bytes, caption: str
    ) -> None:
        """Deliver a file (e.g. a PDF report) to ``target``. Raises ``MessageSendError``."""
        ...


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...
