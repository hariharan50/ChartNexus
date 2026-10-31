"""Connecting, linking and testing Trade Buddy's own alert bot.

The same five steps the messaging settings page walks, because it is the same
problem: save the token → verify it with Telegram → resolve a chat to deliver
to → prove it works → be able to switch it off without losing the setup.

They live here rather than being shared with ``messaging`` because the two
want *different bots*. A level break mid-trade and a once-a-morning briefing
want different notification settings on a phone, and silencing one must not
silence the other.
"""

from __future__ import annotations

from dataclasses import dataclass

from chartnexus.contexts.trade_buddy.application.ports import (
    AlertChannelRepository,
    AlertSenderPort,
    Clock,
)
from chartnexus.contexts.trade_buddy.domain.channel import AlertChannel, AlertConnection
from chartnexus.contexts.trade_buddy.domain.errors import (
    ChannelNotReadyError,
    ChannelVerificationError,
)
from chartnexus.shared_kernel.types.identifiers import TenantId, UserId


@dataclass(frozen=True, slots=True)
class ConnectCommand:
    user_id: UserId
    tenant_id: TenantId
    channel: AlertChannel
    secret: str


@dataclass(slots=True)
class ConnectChannel:
    """Store the token and verify it in one step.

    Verification happens before the write, not after: a token the provider has
    already refused should never reach the database, or the settings page shows
    a connection that cannot possibly deliver.
    """

    repository: AlertChannelRepository
    sender: AlertSenderPort
    clock: Clock

    async def __call__(self, command: ConnectCommand) -> AlertConnection:
        identity = await self.sender.verify(command.secret)
        now = self.clock.now()

        existing = await self.repository.find(command.user_id, command.channel)
        if existing is None:
            connection = AlertConnection.create(
                user_id=command.user_id,
                tenant_id=command.tenant_id,
                channel=command.channel,
                secret=command.secret,
                label=identity.label,
                now=now,
            )
        else:
            connection = existing
            connection.update_credentials(secret=command.secret, label=identity.label, now=now)

        await self.repository.upsert(connection)
        return connection


#: Sent the moment a chat is linked. Names what will arrive and when, so the
#: next message from this bot — possibly days later, mid-trade — is expected
#: rather than a surprise from a sender you have forgotten connecting.
WELCOME_MESSAGE = (
    "<b>Trade Buddy is connected</b>\n"
    "Level alerts arrive here during market hours, 09:15-15:20 IST.\n\n"
    "<i>You will get approaches, touches, confirmed breaks and reclaims "
    "for the indices you have marked levels on.</i>"
)


@dataclass(slots=True)
class LinkChat:
    """Resolve the chat to deliver to, and prove it by delivering to it.

    Returns the connection unchanged when nobody has messaged the bot yet — a
    normal first-run state, since a bot cannot open a conversation. The UI
    offers manual entry for that case rather than dead-ending.

    The welcome message is sent **before** the target is stored, and a failure
    to send means nothing is stored at all. That ordering is the point: a chat
    id that cannot actually receive is not a link, and persisting one would
    show "Ready" for a channel that silently drops every alert. Proving it at
    the moment of linking is the difference between a setup you can trust and
    one you discover is broken when a real break goes missing.
    """

    repository: AlertChannelRepository
    sender: AlertSenderPort
    clock: Clock

    async def __call__(
        self, user_id: UserId, channel: AlertChannel, *, target: str | None = None
    ) -> AlertConnection:
        connection = await _require(self.repository, user_id, channel)

        resolved = target or await self.sender.detect_target(connection.secret)
        if not resolved:
            return connection
        resolved = resolved.strip()

        try:
            await self.sender.send(connection.secret, resolved, WELCOME_MESSAGE)
        except Exception as exc:
            # Surfaced as a validation failure, not a 500: the usual cause is a
            # chat id the bot is not a member of, which the reader can fix.
            raise ChannelVerificationError(
                f"could not deliver to chat {resolved}: {exc}", provider=channel.value
            ) from exc

        connection.link_target(resolved, self.clock.now())
        await self.repository.upsert(connection)
        return connection


@dataclass(slots=True)
class SetChannelEnabled:
    """The on/off switch. Keeps the token and the chat, so switching back on
    does not mean connecting again."""

    repository: AlertChannelRepository
    clock: Clock

    async def __call__(
        self, user_id: UserId, channel: AlertChannel, *, enabled: bool
    ) -> AlertConnection:
        connection = await _require(self.repository, user_id, channel)
        connection.set_enabled(enabled, self.clock.now())
        await self.repository.upsert(connection)
        return connection


@dataclass(slots=True)
class DisconnectChannel:
    repository: AlertChannelRepository

    async def __call__(self, user_id: UserId, channel: AlertChannel) -> None:
        await self.repository.delete(user_id, channel)


@dataclass(slots=True)
class SendChannelTest:
    """Prove the setup before a real break depends on it.

    Sends through the same sender the watcher uses, so a passing test means
    the token, the chat id and the formatting all work — not merely that a row
    exists.
    """

    repository: AlertChannelRepository
    sender: AlertSenderPort

    async def __call__(self, user_id: UserId, channel: AlertChannel) -> None:
        connection = await _require(self.repository, user_id, channel)
        if not connection.ready:
            raise ChannelNotReadyError(channel.value)
        assert connection.target is not None  # noqa: S101 — guarded by `ready`
        await self.sender.send(
            connection.secret,
            connection.target,
            "<b>Trade Buddy</b> is connected.\n"
            "<i>Level alerts will arrive here during market hours.</i>",
        )


@dataclass(slots=True)
class GetChannels:
    repository: AlertChannelRepository

    async def __call__(self, user_id: UserId) -> tuple[AlertConnection, ...]:
        return await self.repository.find_all(user_id)


async def _require(
    repository: AlertChannelRepository, user_id: UserId, channel: AlertChannel
) -> AlertConnection:
    connection = await repository.find(user_id, channel)
    if connection is None or not connection.configured:
        raise ChannelNotReadyError(channel.value)
    return connection
