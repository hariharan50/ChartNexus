"""Messaging use cases: connect a channel, link its target, test it, manage it."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from chartnexus.contexts.messaging.application.dto import ChannelView
from chartnexus.contexts.messaging.application.ports import (
    ChannelConnectionRepository,
    Clock,
    MessageSenderPort,
)
from chartnexus.contexts.messaging.domain.channel import Channel, ChannelConnection
from chartnexus.contexts.messaging.domain.credentials import TelegramCredentials
from chartnexus.contexts.messaging.domain.errors import (
    ChannelNotConfiguredError,
    ChannelVerificationError,
)
from chartnexus.shared_kernel.types.identifiers import TenantId, UserId

_TEST_MESSAGE = "✅ ChartNexus is connected. You'll receive your pre-market briefings here."


def _sender(senders: Mapping[Channel, MessageSenderPort], channel: Channel) -> MessageSenderPort:
    sender = senders.get(channel)
    if sender is None:
        raise ChannelVerificationError(f"{channel.value} is not available yet.")
    return sender


@dataclass(frozen=True, slots=True)
class ConnectTelegramCommand:
    user_id: UserId
    tenant_id: TenantId
    bot_token: str


@dataclass(frozen=True, slots=True)
class ConnectTelegram:
    """Save (and verify) a user's Telegram bot token. Chat linking is a later step."""

    repository: ChannelConnectionRepository
    senders: Mapping[Channel, MessageSenderPort]
    clock: Clock

    async def __call__(self, command: ConnectTelegramCommand) -> ChannelView:
        # Validate the token shape before spending a network round-trip.
        credentials = TelegramCredentials.parse(command.bot_token)
        identity = await _sender(self.senders, Channel.TELEGRAM).verify(credentials.bot_token)
        now = self.clock.now()

        connection = await self.repository.find(command.user_id, Channel.TELEGRAM)
        if connection is None:
            connection = ChannelConnection.create(
                user_id=command.user_id,
                tenant_id=command.tenant_id,
                channel=Channel.TELEGRAM,
                secret=credentials.bot_token,
                label=identity.label,
                now=now,
            )
        else:
            connection.update_credentials(
                secret=credentials.bot_token, label=identity.label, now=now
            )

        await self.repository.upsert(connection)
        return ChannelView.of(connection)


@dataclass(frozen=True, slots=True)
class DetectTelegramChatCommand:
    user_id: UserId
    #: Optional manual override; when absent, the chat is auto-detected from
    #: recent messages to the bot.
    chat_id: str | None = None


@dataclass(frozen=True, slots=True)
class DetectTelegramChat:
    """Resolve the chat to deliver to — auto from getUpdates, or a manual id."""

    repository: ChannelConnectionRepository
    senders: Mapping[Channel, MessageSenderPort]
    clock: Clock

    async def __call__(self, command: DetectTelegramChatCommand) -> ChannelView:
        connection = await self.repository.find(command.user_id, Channel.TELEGRAM)
        if connection is None or not connection.configured:
            raise ChannelNotConfiguredError("Save your Telegram bot token first.")

        target = command.chat_id
        if target:
            # Validate the manual value through the credentials VO.
            target = TelegramCredentials.parse(connection.secret, target).chat_id
        else:
            target = await _sender(self.senders, Channel.TELEGRAM).detect_target(connection.secret)
        if not target:
            raise ChannelVerificationError(
                "Couldn't find your chat. Open Telegram, send /start (or any message) to your "
                "bot, then try again — or paste your chat id manually."
            )

        connection.link_target(target, self.clock.now())
        await self.repository.upsert(connection)
        return ChannelView.of(connection)


@dataclass(frozen=True, slots=True)
class SendTestMessage:
    """Send a hello to confirm the channel end-to-end."""

    repository: ChannelConnectionRepository
    senders: Mapping[Channel, MessageSenderPort]

    async def __call__(self, user_id: UserId, channel: Channel) -> None:
        connection = await self.repository.find(user_id, channel)
        if connection is None or not connection.configured:
            raise ChannelNotConfiguredError("This channel isn't connected yet.")
        if not connection.target:
            raise ChannelVerificationError("Link your chat before sending a test.")
        await _sender(self.senders, channel).send(
            connection.secret, connection.target, _TEST_MESSAGE
        )


@dataclass(frozen=True, slots=True)
class SetChannelEnabledCommand:
    user_id: UserId
    channel: Channel
    enabled: bool


@dataclass(frozen=True, slots=True)
class SetChannelEnabled:
    repository: ChannelConnectionRepository
    clock: Clock

    async def __call__(self, command: SetChannelEnabledCommand) -> ChannelView:
        connection = await self.repository.find(command.user_id, command.channel)
        if connection is None:
            raise ChannelNotConfiguredError("This channel isn't connected yet.")
        connection.set_enabled(command.enabled, self.clock.now())
        await self.repository.upsert(connection)
        return ChannelView.of(connection)


@dataclass(frozen=True, slots=True)
class DisconnectChannel:
    repository: ChannelConnectionRepository

    async def __call__(self, user_id: UserId, channel: Channel) -> None:
        await self.repository.delete(user_id, channel)


@dataclass(frozen=True, slots=True)
class GetChannels:
    repository: ChannelConnectionRepository

    async def __call__(self, user_id: UserId) -> tuple[ChannelView, ...]:
        connections = await self.repository.find_all(user_id)
        return tuple(ChannelView.of(c) for c in connections)
