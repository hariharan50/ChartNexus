"""WhatsApp via the CallMeBot relay.

A deliberately dumb channel, and the adapter's job is mostly to be honest about
that. CallMeBot accepts a GET with the message in the query string and sends it
to one pre-authorised number. It offers no formatting, no delivery receipt, and
no useful error body — a 200 means it accepted the request, not that WhatsApp
delivered anything.

Two consequences shape this file:

**Plain text only.** No bold, no monospace, no buttons. The router hands this
sender the unformatted render; stripping markup here would be too late, because
the message would already have been written for a channel that cannot show it.

**The budget is not enforced here.** CallMeBot throttles at roughly 25 messages
per four hours and signals it inconsistently. Counting lives in
``WhatsAppBudget`` so the engine can *see* the ceiling coming and degrade to
Telegram deliberately, rather than discovering at 15:00 that the afternoon's
alerts went nowhere.
"""

from __future__ import annotations

import httpx

from chartnexus.contexts.trade_buddy.application.routing import Notifier
from chartnexus.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)

_ENDPOINT = "https://api.callmebot.com/whatsapp.php"

#: CallMeBot truncates long messages unpredictably. Cutting locally, with an
#: ellipsis, beats letting the provider decide where the sentence ends.
_MAX_TEXT = 900


class CallMeBotNotifier(Notifier):
    """Implements ``Notifier`` for the CallMeBot WhatsApp relay."""

    name = "whatsapp"
    #: Plain text only — the router uses this to pick the renderer.
    rich = False

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        phone: str,
        api_key: str,
        endpoint: str = _ENDPOINT,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._client = client
        self._phone = phone
        self._api_key = api_key
        self._endpoint = endpoint
        self._timeout = timeout_seconds

    async def send(self, text: str) -> None:
        """Deliver ``text``. Raises ``httpx.HTTPError`` for the router to retry.

        Params go through httpx's encoder rather than a hand-built query string:
        the message contains spaces, newlines and ``▲``, and a manually escaped
        URL is where an alert turns into a 400 nobody notices.
        """
        body = text if len(text) <= _MAX_TEXT else f"{text[: _MAX_TEXT - 1]}…"
        response = await self._client.get(
            self._endpoint,
            params={"phone": self._phone, "text": body, "apikey": self._api_key},
            timeout=self._timeout,
        )
        # CallMeBot answers 200 with an HTML error page for a bad key or an
        # unapproved number, so the status alone is not proof of acceptance.
        if response.status_code >= httpx.codes.BAD_REQUEST:
            log.warning(
                "callmebot_rejected",
                status=response.status_code,
                # Never the key or the phone number.
                body=response.text[:200],
            )
            response.raise_for_status()
        lowered = response.text.lower()
        if "apikey" in lowered and "error" in lowered:
            raise httpx.HTTPError("CallMeBot rejected the API key or phone number")
        log.info("callmebot_sent", chars=len(body))
