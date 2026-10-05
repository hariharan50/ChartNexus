"""Data crossing the messaging application boundary.

Never carries the raw channel secret — the view a caller receives is the same view
that can safely be logged: the secret is only ever present masked.
"""

from __future__ import annotations

from dataclasses import dataclass

from chartnexus.contexts.messaging.domain.channel import ChannelConnection


@dataclass(frozen=True, slots=True)
class ChannelView:
    channel: str
    configured: bool
    verified: bool
    enabled: bool
    ready: bool
    label: str | None
    target: str | None
    masked_secret: str | None

    @classmethod
    def of(cls, connection: ChannelConnection) -> ChannelView:
        return cls(
            channel=connection.channel.value,
            configured=connection.configured,
            verified=connection.verified,
            enabled=connection.enabled,
            ready=connection.ready,
            label=connection.label,
            target=connection.target,
            masked_secret=connection.masked_secret,
        )
