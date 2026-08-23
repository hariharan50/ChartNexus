"""The Telegram Bot API HTTP contract.

**Every Telegram URL, method and payload shape lives here.** Mirrors the FYERS
rest-client blueprint: a thin transport over the shared httpx client that knows
Telegram's envelope (`{ok, result | description, error_code}`) and nothing about
our domain. It raises two transport errors; the sender maps them to domain errors.

The bot token is a path segment (`/bot<token>/<method>`) — that is how Telegram's
API authenticates — so it is never logged here (only the method name is).
"""

from __future__ import annotations

from typing import Any

import httpx

DEFAULT_API_BASE = "https://api.telegram.org"
_MAX_MESSAGE_LENGTH = 200


class TelegramUnavailableError(Exception):
    """A transport/5xx/429 failure — worth retrying later."""


class TelegramRejectedError(Exception):
    """Telegram rejected the request (bad token, bad chat) — not worth retrying."""


class TelegramClient:
    """Thin transport for the Telegram Bot API over the shared httpx client."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        api_base: str = DEFAULT_API_BASE,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._http = http
        self._api_base = api_base.rstrip("/")
        self._timeout = timeout_seconds

    async def get_me(self, token: str) -> dict[str, Any]:
        """Verify a bot token; the result carries the bot's ``username``."""
        result = await self._call(token, "getMe", method="GET")
        return result if isinstance(result, dict) else {}

    async def get_updates(self, token: str) -> list[dict[str, Any]]:
        """Recent updates sent to the bot (for chat-id detection)."""
        result = await self._call(token, "getUpdates", method="GET")
        return result if isinstance(result, list) else []

    async def send_message(self, token: str, chat_id: str, text: str) -> dict[str, Any]:
        result = await self._call(
            token,
            "sendMessage",
            method="POST",
            payload={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        )
        return result if isinstance(result, dict) else {}

    # -- transport ----------------------------------------------------------

    async def _call(
        self,
        token: str,
        api_method: str,
        *,
        method: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self._api_base}/bot{token}/{api_method}"
        try:
            if method == "POST":
                response = await self._http.post(url, json=payload, timeout=self._timeout)
            else:
                response = await self._http.get(url, timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise TelegramUnavailableError(str(exc)) from exc
        return self._unwrap(response)

    def _unwrap(self, response: httpx.Response) -> Any:
        if response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
            raise TelegramUnavailableError(f"telegram {response.status_code}")
        if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
            raise TelegramUnavailableError("telegram rate limited")

        try:
            payload: dict[str, Any] = response.json()
        except ValueError as exc:
            raise TelegramRejectedError("Telegram returned an unreadable response.") from exc

        if payload.get("ok"):
            return payload.get("result")

        raise TelegramRejectedError(_safe_message(payload))


def _safe_message(payload: dict[str, Any]) -> str:
    message = str(payload.get("description") or "").strip()
    return message[:_MAX_MESSAGE_LENGTH] if message else "Telegram rejected this request."
