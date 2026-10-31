"""Telegram delivery for Trade Buddy — HTML parse mode and inline keyboards.

Separate from ``infrastructure/notifications/telegram/sender.py`` rather than an
extension of it, for one concrete reason: that client's ``send_message`` sends no
``parse_mode``, and it is shared with the messaging context and the daily report.
Adding HTML there would change how *their* messages render. Alerts are the only
thing here that wants markup, so the markup lives here.

The inline keyboard is a convenience, not decoration: a confirmed break is the
moment you want the chart, and a button is one tap versus finding the tab.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from chartnexus.contexts.trade_buddy.application.routing import Notifier
from chartnexus.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)

#: Telegram rejects messages over 4096 characters outright. Alerts are far
#: shorter, but a truncating guard beats a dropped alert.
_MAX_TEXT = 4000


class TelegramNotifier(Notifier):
    """Implements ``Notifier`` against the Telegram Bot API."""

    name = "telegram"
    rich = True

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        bot_token: str,
        chat_id: str,
        api_base: str = "https://api.telegram.org",
        timeout_seconds: float = 10.0,
        chart_url: str | None = None,
    ) -> None:
        self._client = client
        self._token = bot_token
        self._chat_id = chat_id
        self._api_base = api_base.rstrip("/")
        self._timeout = timeout_seconds
        self._chart_url = chart_url

    async def send(self, text: str) -> None:
        """Deliver ``text`` as HTML. Raises ``httpx.HTTPError`` so the router retries."""
        payload: dict[str, Any] = {
            "chat_id": self._chat_id,
            "text": text if len(text) <= _MAX_TEXT else f"{text[: _MAX_TEXT - 1]}…",
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if self._chart_url:
            payload["reply_markup"] = json.dumps(
                {"inline_keyboard": [[{"text": "Open chart", "url": self._chart_url}]]}
            )

        # The token is a path segment in the Bot API, so it must never be logged
        # — `_safe_url` exists purely so an error message can name the endpoint.
        response = await self._client.post(
            f"{self._api_base}/bot{self._token}/sendMessage",
            json=payload,
            timeout=self._timeout,
        )
        if response.status_code >= httpx.codes.BAD_REQUEST:
            log.warning(
                "telegram_alert_rejected",
                status=response.status_code,
                description=_description(response),
            )
            raise httpx.HTTPError(
                f"Telegram rejected the alert ({response.status_code}): {_description(response)}"
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
