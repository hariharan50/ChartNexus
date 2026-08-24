"""TelegramSender — implements the messaging ``MessageSenderPort`` over the Bot API.

Verifies a bot token (getMe), resolves a chat id from recent updates (getUpdates),
and sends text (sendMessage), chunked to Telegram's 4096-character per-message
limit. Transport errors from the client are translated into the messaging domain
errors so the API renders the right status.
"""

from __future__ import annotations

from marketcompass.contexts.messaging.application.ports import ChannelIdentity
from marketcompass.contexts.messaging.domain.channel import Channel
from marketcompass.contexts.messaging.domain.errors import (
    ChannelVerificationError,
    MessageSendError,
)
from marketcompass.infrastructure.notifications.telegram.client import (
    TelegramClient,
    TelegramRejectedError,
    TelegramUnavailableError,
)

# Telegram rejects messages over 4096 characters; leave a small margin.
_MAX_CHARS = 4000


class TelegramSender:
    """A ``MessageSenderPort`` for Telegram."""

    def __init__(self, client: TelegramClient) -> None:
        self._client = client

    @property
    def channel(self) -> Channel:
        return Channel.TELEGRAM

    async def verify(self, secret: str) -> ChannelIdentity:
        try:
            me = await self._client.get_me(secret)
        except TelegramRejectedError as exc:
            raise ChannelVerificationError(
                "Telegram rejected that bot token. Copy it again from @BotFather."
            ) from exc
        except TelegramUnavailableError as exc:
            raise ChannelVerificationError(
                "Couldn't reach Telegram just now — try again in a moment."
            ) from exc
        username = (me or {}).get("username") if isinstance(me, dict) else None
        label = f"@{username}" if username else "Telegram bot"
        return ChannelIdentity(label=label)

    async def detect_target(self, secret: str) -> str | None:
        try:
            updates = await self._client.get_updates(secret)
        except (TelegramRejectedError, TelegramUnavailableError) as exc:
            raise ChannelVerificationError(
                "Couldn't read your Telegram messages just now — try again."
            ) from exc
        # Newest first: the chat that most recently messaged the bot is the target.
        for update in reversed(updates):
            message = update.get("message") or update.get("channel_post")
            chat = (message or {}).get("chat") if isinstance(message, dict) else None
            chat_id = (chat or {}).get("id") if isinstance(chat, dict) else None
            if chat_id is not None:
                return str(chat_id)
        return None

    async def send(self, secret: str, target: str, text: str) -> None:
        try:
            for chunk in _chunk(text):
                await self._client.send_message(secret, target, chunk)
        except TelegramRejectedError as exc:
            raise MessageSendError(str(exc), provider="telegram") from exc
        except TelegramUnavailableError as exc:
            raise MessageSendError(
                "Telegram is unavailable right now.", provider="telegram"
            ) from exc

    async def send_document(
        self, secret: str, target: str, *, filename: str, content: bytes, caption: str
    ) -> None:
        try:
            await self._client.send_document(
                secret, target, filename=filename, content=content, caption=caption
            )
        except TelegramRejectedError as exc:
            raise MessageSendError(str(exc), provider="telegram") from exc
        except TelegramUnavailableError as exc:
            raise MessageSendError(
                "Telegram is unavailable right now.", provider="telegram"
            ) from exc


def _chunk(text: str, *, limit: int = _MAX_CHARS) -> list[str]:
    """Split ``text`` into <=limit pieces, preferring to break on line breaks."""
    text = text.strip()
    if len(text) <= limit:
        return [text] if text else []

    chunks: list[str] = []
    current = ""
    for original in text.split("\n"):
        line = original
        # A single over-long line is hard-split.
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks
