"""Verify, link and send for Trade Buddy's own Telegram bot.

Reuses ``TelegramClient`` — the transport is identical and there is no reason
to own a second copy of `getMe`/`getUpdates`. What differs is one line: alerts
are sent with ``parse_mode: HTML`` so a break reads as a headline rather than
a wall of tags, and that client deliberately sends no parse mode because it is
shared with the briefing and the daily report.

So the HTTP call for `send` is made here while the two read calls go through
the shared client. That split is the whole of the duplication, and it is
smaller than the alternative — changing how every other message in the product
renders.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from chartnexus.contexts.trade_buddy.application.ports import ChannelIdentity
from chartnexus.contexts.trade_buddy.domain.errors import ChannelVerificationError
from chartnexus.infrastructure.notifications.telegram.client import (
    TelegramClient,
    TelegramRejectedError,
    TelegramUnavailableError,
)
from chartnexus.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)

#: Telegram rejects anything over 4096 characters outright.
_MAX_TEXT = 4000


class TelegramAlertSender:
    """Implements ``AlertSenderPort`` for Trade Buddy's bot."""

    def __init__(
        self,
        client: TelegramClient,
        http: httpx.AsyncClient,
        *,
        api_base: str = "https://api.telegram.org",
        timeout_seconds: float = 10.0,
        chart_url: str | None = None,
    ) -> None:
        self._client = client
        self._http = http
        self._api_base = api_base.rstrip("/")
        self._timeout = timeout_seconds
        self._chart_url = chart_url

    async def verify(self, secret: str) -> ChannelIdentity:
        """Confirm the token and report the bot's @username.

        The username is what makes two bots tellable apart in the UI — without
        it, an alerts bot and a briefing bot are two identical rows.
        """
        try:
            me = await self._client.get_me(secret)
        except TelegramRejectedError as exc:
            raise ChannelVerificationError(str(exc), provider="telegram") from exc
        except TelegramUnavailableError as exc:
            raise ChannelVerificationError(
                f"Telegram could not be reached: {exc}", provider="telegram"
            ) from exc

        username = me.get("username") if isinstance(me, dict) else None
        return ChannelIdentity(label=f"@{username}" if username else "Telegram bot")

    async def detect_target(self, secret: str) -> str | None:
        """The chat id of whoever last messaged the bot, or ``None``.

        ``None`` is a normal first-run answer, not a failure: a bot cannot
        message someone who has never opened a conversation with it, so the
        user has to send it something before there is a chat to find.
        """
        try:
            updates = await self._client.get_updates(secret)
        except TelegramRejectedError as exc:
            raise ChannelVerificationError(str(exc), provider="telegram") from exc
        except TelegramUnavailableError:
            # Transient. The caller offers manual entry rather than treating a
            # momentary outage as "you have no chat".
            return None

        # Newest first: the chat that most recently messaged the bot.
        for update in reversed(updates):
            message = update.get("message") or update.get("channel_post")
            chat = (message or {}).get("chat") if isinstance(message, dict) else None
            chat_id = (chat or {}).get("id") if isinstance(chat, dict) else None
            if chat_id is not None:
                return str(chat_id)
        return None

    async def send(self, secret: str, target: str, text: str) -> None:
        """Deliver ``text`` as HTML. Raises ``httpx.HTTPError`` so the router retries."""
        payload: dict[str, Any] = {
            "chat_id": target,
            "text": text if len(text) <= _MAX_TEXT else f"{text[: _MAX_TEXT - 1]}…",
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if self._chart_url:
            payload["reply_markup"] = json.dumps(
                {"inline_keyboard": [[{"text": "Open chart", "url": self._chart_url}]]}
            )

        # The token is a path segment in the Bot API, so the URL is never logged.
        response = await self._http.post(
            f"{self._api_base}/bot{secret}/sendMessage",
            json=payload,
            timeout=self._timeout,
        )
        if response.status_code >= httpx.codes.BAD_REQUEST:
            description = _description(response)
            log.warning(
                "trade_buddy_telegram_rejected",
                status=response.status_code,
                description=description,
            )
            raise httpx.HTTPError(
                f"Telegram rejected the alert ({response.status_code}): {description}"
            )


def _description(response: httpx.Response) -> str:
    """Telegram's own error text, which is the only useful part of the body."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, dict):
        return str(body.get("description", ""))[:200]
    return ""
