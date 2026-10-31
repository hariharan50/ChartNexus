"""Trade Buddy's own alert channels — a bot of its own, separate from the rest.

The ``messaging`` context already models a user's chat connections, and this
deliberately does not reuse it. Alerts and briefings want *different bots*: the
MME100 briefing arrives once a morning and a level break arrives mid-trade, so
they want different notification settings on the phone, and silencing one must
not silence the other. Modelling that inside ``messaging`` would mean widening
its ``unique(user, channel)`` invariant and changing a context three other
features depend on; keeping it here costs a second connect flow and risks
nothing that already works.

The lifecycle mirrors the one next door because it is the same problem: store
the secret, verify it with the provider, resolve a delivery target, then send.
A connection is only ``ready`` when all four hold, so the watcher can ask one
question before it tries to deliver.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from chartnexus.shared_kernel.types.identifiers import TenantId, UserId, new_id

_MASK_KEEP = 4


class AlertChannel(StrEnum):
    """Where Trade Buddy can deliver.

    WhatsApp is here because the routing policy already distinguishes the two —
    Telegram takes everything, CallMeBot takes only confirmed facts — so the
    storage has to be able to hold both even while only Telegram has a connect
    flow in the UI.
    """

    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"


@dataclass(slots=True)
class AlertConnection:
    """One user's link to one alert channel.

    ``secret`` is plaintext in memory only and for as long as an operation
    needs it; encryption at rest is the repository's job, exactly as in
    ``messaging``.
    """

    id: uuid.UUID
    user_id: UserId
    tenant_id: TenantId
    channel: AlertChannel
    #: Telegram bot token, or the CallMeBot API key.
    secret: str
    #: Telegram chat id, or the WhatsApp phone number. None until linked.
    target: str | None = None
    #: Display only — the bot's @username, so two bots are tellable apart.
    label: str | None = None
    verified: bool = False
    enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        user_id: UserId,
        tenant_id: TenantId,
        channel: AlertChannel,
        secret: str,
        label: str | None,
        now: datetime,
    ) -> AlertConnection:
        return cls(
            id=new_id(),
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
        """Replace the secret. Re-verification is required.

        The target is dropped deliberately: a new token may belong to a
        different bot, and a chat id resolved for the old one would deliver to
        a conversation the new bot is not even in.
        """
        self.secret = secret
        self.label = label
        self.target = None
        self.verified = False
        self.updated_at = now

    def link_target(self, target: str, now: datetime) -> None:
        self.target = target
        self.verified = True
        self.updated_at = now

    def set_enabled(self, enabled: bool, now: datetime) -> None:
        self.enabled = enabled
        self.updated_at = now

    # -- queries ------------------------------------------------------------

    @property
    def configured(self) -> bool:
        """A secret is stored, so verification can proceed."""
        return bool(self.secret)

    @property
    def ready(self) -> bool:
        """Enabled, verified, and holding both halves — a send can happen now."""
        return self.enabled and self.verified and bool(self.secret) and bool(self.target)

    @property
    def masked_secret(self) -> str | None:
        """For display. A bot token is a bearer credential and never goes back
        over the wire in full, not even to the person who typed it."""
        if not self.secret:
            return None
        return _mask(self.secret)


def _mask(value: str, *, keep: int = _MASK_KEEP) -> str:
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}{'*' * 6}{value[-keep:]}"


#: A Telegram chat id is a number — negative for groups and supergroups — or a
#: public `@username`. Anything else cannot be delivered to, and accepting it
#: produces a connection that reads as Ready and fails with "chat not found"
#: on the first real alert.
_CHAT_ID = re.compile(r"^(-?\d{1,20}|@[A-Za-z][A-Za-z0-9_]{4,31})$")


def is_valid_chat_id(value: str) -> bool:
    return bool(_CHAT_ID.match(value.strip()))
