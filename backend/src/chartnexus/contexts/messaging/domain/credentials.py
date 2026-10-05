"""Value objects for a channel's connection credentials.

Provider-neutral at the seam: the aggregate stores one secret string plus an
optional delivery target. ``TelegramCredentials`` is the first concrete shape; a
``WhatsAppCredentials`` will slot in beside it in phase 2 with the same contract.
The secret never appears in a repr or log line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from chartnexus.contexts.messaging.domain.errors import ChannelCredentialsInvalidError

_MIN_TOKEN_LENGTH = 8
_MAX_TOKEN_LENGTH = 512
_MAX_TARGET_LENGTH = 64
# A Telegram bot token is `<bot_id>:<alphanumeric secret>` — validated loosely so
# a format tweak on Telegram's side never needs a code change.
_TELEGRAM_TOKEN_RE = re.compile(r"^\d{3,}:[A-Za-z0-9_-]{20,}$")


@dataclass(frozen=True, slots=True)
class TelegramCredentials:
    """A user's Telegram bot token and (once linked) the chat to deliver to."""

    bot_token: str
    chat_id: str | None = None

    def __post_init__(self) -> None:
        length = len(self.bot_token)
        if not (_MIN_TOKEN_LENGTH <= length <= _MAX_TOKEN_LENGTH):
            raise ChannelCredentialsInvalidError(
                f"The bot token must be between {_MIN_TOKEN_LENGTH} and "
                f"{_MAX_TOKEN_LENGTH} characters."
            )
        if any(ch in self.bot_token for ch in "\r\n") or not self.bot_token.isprintable():
            raise ChannelCredentialsInvalidError("The bot token contains unsupported characters.")
        if not _TELEGRAM_TOKEN_RE.match(self.bot_token):
            raise ChannelCredentialsInvalidError(
                "That doesn't look like a Telegram bot token — copy it from @BotFather "
                "(it looks like 123456789:AA...)."
            )
        if self.chat_id is not None and not (1 <= len(self.chat_id) <= _MAX_TARGET_LENGTH):
            raise ChannelCredentialsInvalidError("The chat id is invalid.")

    @classmethod
    def parse(cls, bot_token: str, chat_id: str | None = None) -> TelegramCredentials:
        """Normalise then validate untrusted input from the settings form."""
        target = (chat_id or "").strip() or None
        return cls(bot_token=(bot_token or "").strip(), chat_id=target)

    def __repr__(self) -> str:
        return f"TelegramCredentials(bot_token=***, chat_id={self.chat_id!r})"
