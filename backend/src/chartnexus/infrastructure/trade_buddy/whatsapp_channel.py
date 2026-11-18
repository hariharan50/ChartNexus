"""Connect, test and send for a user's own WhatsApp, via the CallMeBot relay.

Implements ``AlertSenderPort`` so the generic channel use cases (test, enable,
disconnect) work for WhatsApp exactly as for Telegram. The transport is the
existing :class:`CallMeBotNotifier`, built per call from the user's own number
and key — nothing is held between calls, so one user's credentials can never be
used to send another's message.

CallMeBot has no "who am I" or "who messaged me" call, so ``verify`` and
``detect_target`` have nothing to ask: connecting proves the pair by sending a
welcome message instead (see ``ConnectWhatsApp``).
"""

from __future__ import annotations

import httpx

from chartnexus.contexts.trade_buddy.application.ports import ChannelIdentity
from chartnexus.infrastructure.notifications.whatsapp.callmebot import CallMeBotNotifier


class WhatsAppAlertSender:
    """Implements ``AlertSenderPort`` for a user's CallMeBot WhatsApp relay."""

    def __init__(self, http: httpx.AsyncClient, *, timeout_seconds: float = 10.0) -> None:
        self._http = http
        self._timeout = timeout_seconds

    async def verify(self, secret: str) -> ChannelIdentity:  # noqa: ARG002 — port shape
        """Nothing to ask CallMeBot; the welcome message is the verification."""
        return ChannelIdentity(label="WhatsApp (CallMeBot)")

    async def detect_target(self, secret: str) -> str | None:  # noqa: ARG002 — port shape
        """CallMeBot cannot say who messaged it; the number is always entered."""
        return None

    async def send(self, secret: str, target: str, text: str) -> None:
        """Deliver plain ``text`` to ``target`` with API key ``secret``.

        Raises ``httpx.HTTPError`` whose text never contains the key or number.
        """
        await CallMeBotNotifier(
            self._http, phone=target, api_key=secret, timeout_seconds=self._timeout
        ).send(text)
