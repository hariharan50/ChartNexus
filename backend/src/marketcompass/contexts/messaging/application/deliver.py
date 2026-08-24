"""DeliverText — push a piece of text to all of a user's ready channels.

The reusable delivery entry point. v1's only caller is the MME100 pre-market
briefing worker; STRYX calls and signal flips will call it the same way later. It
is **swallow-and-log per channel**: one channel failing (or a whole delivery
failing) must never break the caller's own job (the briefing is already stored).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass

from marketcompass.contexts.messaging.application.ports import (
    ChannelConnectionRepository,
    MessageSenderPort,
)
from marketcompass.contexts.messaging.domain.channel import Channel
from marketcompass.shared_kernel.types.identifiers import UserId

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DeliverText:
    repository: ChannelConnectionRepository
    senders: Mapping[Channel, MessageSenderPort]

    async def __call__(self, user_id: UserId, text: str, *, source: str) -> int:
        """Send ``text`` to every ready channel for ``user_id``. Returns how many
        channels were delivered to successfully."""
        try:
            connections = await self.repository.find_all(user_id)
        except Exception as exc:
            log.warning("messaging_delivery_load_failed", exc_info=exc)
            return 0

        sent = 0
        for connection in connections:
            if not connection.ready or connection.target is None:
                continue
            sender = self.senders.get(connection.channel)
            if sender is None:
                continue
            try:
                await sender.send(connection.secret, connection.target, text)
                sent += 1
            except Exception as exc:
                # One channel's failure must not stop the others or the caller.
                log.warning(
                    "messaging_delivery_failed channel=%s source=%s error=%r",
                    connection.channel.value,
                    source,
                    exc,
                )
        return sent


@dataclass(frozen=True, slots=True)
class DeliverDocument:
    """Push a file (e.g. a PDF report) to every ready channel for a user.

    Same swallow-and-log contract as :class:`DeliverText`; used by the report
    worker to deliver the daily PDF.
    """

    repository: ChannelConnectionRepository
    senders: Mapping[Channel, MessageSenderPort]

    async def __call__(
        self, user_id: UserId, *, filename: str, content: bytes, caption: str, source: str
    ) -> int:
        try:
            connections = await self.repository.find_all(user_id)
        except Exception as exc:
            log.warning("messaging_document_load_failed", exc_info=exc)
            return 0

        sent = 0
        for connection in connections:
            if not connection.ready or connection.target is None:
                continue
            sender = self.senders.get(connection.channel)
            if sender is None:
                continue
            try:
                await sender.send_document(
                    connection.secret,
                    connection.target,
                    filename=filename,
                    content=content,
                    caption=caption,
                )
                sent += 1
            except Exception as exc:
                log.warning(
                    "messaging_document_failed channel=%s source=%s error=%r",
                    connection.channel.value,
                    source,
                    exc,
                )
        return sent
