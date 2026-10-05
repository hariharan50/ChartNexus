"""The ChannelConnection aggregate — one user's link to one messaging channel.

One row per (user, channel). Holds the channel secret (bot token) as plaintext in
memory only for as long as an operation needs it; encryption is the repository's
job. The lifecycle is: save the secret (``configured``) → verify it and record the
bot's label → link a delivery target (``ready``) → deliver.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from chartnexus.shared_kernel.types.identifiers import (
    MessagingChannelId,
    TenantId,
    UserId,
    new_id,
)

_MASK_KEEP = 4


class Channel(StrEnum):
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"


# Only Telegram is wired to a sender today; WhatsApp is reserved for phase 2 and
# rejected before it can be stored, so a user can't connect a channel we can't send on.
SUPPORTED_CHANNELS = frozenset({Channel.TELEGRAM})


@dataclass(slots=True)
class ChannelConnection:
    id: MessagingChannelId
    user_id: UserId
    tenant_id: TenantId
    channel: Channel
    #: The channel secret (e.g. Telegram bot token). Plaintext in memory only.
    secret: str
    #: Where messages are delivered (e.g. Telegram chat id). None until linked.
    target: str | None = None
    #: A human label for the connection (e.g. the bot's @username). Display only.
    label: str | None = None
    #: True once a delivery target has been resolved and confirmed.
    verified: bool = False
    #: The user's on/off switch for this channel.
    enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # -- construction -------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        user_id: UserId,
        tenant_id: TenantId,
        channel: Channel,
        secret: str,
        label: str | None,
        now: datetime,
    ) -> ChannelConnection:
        return cls(
            id=MessagingChannelId(new_id()),
            user_id=user_id,
            tenant_id=tenant_id,
            channel=channel,
            secret=secret,
            label=label,
            verified=False,
            enabled=True,
            created_at=now,
            updated_at=now,
        )

    # -- behaviour ----------------------------------------------------------

    def update_credentials(self, *, secret: str, label: str | None, now: datetime) -> None:
        """Replace the secret (e.g. a new bot token). Re-verification is required:
        a new token may point at a different bot, so the linked target is dropped."""
        self.secret = secret
        self.label = label
        self.target = None
        self.verified = False
        self.updated_at = now

    def link_target(self, target: str, now: datetime) -> None:
        """Record the resolved delivery target; the connection is now ready."""
        self.target = target
        self.verified = True
        self.updated_at = now

    def set_enabled(self, enabled: bool, now: datetime) -> None:
        self.enabled = enabled
        self.updated_at = now

    # -- queries ------------------------------------------------------------

    @property
    def configured(self) -> bool:
        """A secret is stored, so verification/linking can proceed."""
        return bool(self.secret)

    @property
    def ready(self) -> bool:
        """Enabled, verified, and has both a secret and a delivery target — a
        message can actually be sent right now."""
        return self.enabled and self.verified and bool(self.secret) and bool(self.target)

    @property
    def masked_secret(self) -> str | None:
        if not self.secret:
            return None
        return _mask(self.secret)


def _mask(value: str, *, keep: int = _MASK_KEEP) -> str:
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}{'*' * 6}{value[-keep:]}"
