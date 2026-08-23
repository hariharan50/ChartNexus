"""Wire contract for the messaging endpoints.

Requests accept a raw secret (the bot token); no response model has a field that
could hold one — the token is only ever returned masked.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from marketcompass.contexts.messaging.application.dto import ChannelView


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ConnectTelegramRequest(_Schema):
    bot_token: str = Field(
        min_length=8,
        max_length=512,
        description="Your Telegram bot token from @BotFather. Stored encrypted, never returned.",
    )


class DetectChatRequest(_Schema):
    #: Optional manual override; when omitted the chat is auto-detected from recent
    #: messages sent to the bot.
    chat_id: str | None = Field(default=None, max_length=64)


class SetEnabledRequest(_Schema):
    enabled: bool


class ChannelResponse(_Schema):
    channel: str
    configured: bool
    verified: bool
    enabled: bool
    ready: bool
    label: str | None
    target: str | None
    masked_secret: str | None

    @classmethod
    def of(cls, view: ChannelView) -> ChannelResponse:
        return cls(
            channel=view.channel,
            configured=view.configured,
            verified=view.verified,
            enabled=view.enabled,
            ready=view.ready,
            label=view.label,
            target=view.target,
            masked_secret=view.masked_secret,
        )


class ChannelsResponse(_Schema):
    channels: tuple[ChannelResponse, ...]

    @classmethod
    def of(cls, views: tuple[ChannelView, ...]) -> ChannelsResponse:
        return cls(channels=tuple(ChannelResponse.of(v) for v in views))
