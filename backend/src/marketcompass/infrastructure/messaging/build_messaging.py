"""Composition bridge for messaging — assembles services from the ``Container``.

The one module the ``messaging`` context imports from infrastructure. Provides the
request-side services (connect/verify/test/manage) and the worker-side
``DeliverText`` (used by the MME100 briefing loop). The sender registry is built
once from the shared httpx client; adding WhatsApp later is a new entry here plus
its adapter — no context change.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from fastapi import Request

from marketcompass.contexts.messaging.application.deliver import DeliverDocument, DeliverText
from marketcompass.contexts.messaging.application.ports import (
    ChannelConnectionRepository,
    MessageSenderPort,
)
from marketcompass.contexts.messaging.application.use_cases import (
    ConnectTelegram,
    DetectTelegramChat,
    DisconnectChannel,
    GetChannels,
    SendTestMessage,
    SetChannelEnabled,
)
from marketcompass.contexts.messaging.domain.channel import Channel
from marketcompass.infrastructure.notifications.telegram.client import TelegramClient
from marketcompass.infrastructure.notifications.telegram.sender import TelegramSender
from marketcompass.infrastructure.persistence.postgresql.repositories.messaging.channel_repository import (
    SqlAlchemyChannelConnectionRepository,
)
from marketcompass.infrastructure.time.clock import SystemClock
from marketcompass.infrastructure.transport.http.dependencies import get_container


@dataclass(slots=True)
class MessagingServices:
    """The request side of messaging, wired for one authenticated request."""

    get: GetChannels
    connect_telegram: ConnectTelegram
    detect_chat: DetectTelegramChat
    test: SendTestMessage
    set_enabled: SetChannelEnabled
    disconnect: DisconnectChannel


def _senders(container: Any) -> Mapping[Channel, MessageSenderPort]:
    messaging = container.settings.messaging
    telegram = TelegramSender(
        TelegramClient(
            container.http,
            api_base=messaging.telegram_api_base,
            timeout_seconds=messaging.request_timeout_seconds,
        )
    )
    return {Channel.TELEGRAM: telegram}


def _repository(container: Any) -> ChannelConnectionRepository:
    return SqlAlchemyChannelConnectionRepository(container.database, container.messaging_cipher)


def build_messaging_services(request: Request) -> MessagingServices:
    container = get_container(request)
    repository = _repository(container)
    senders = _senders(container)
    clock = SystemClock()
    return MessagingServices(
        get=GetChannels(repository=repository),
        connect_telegram=ConnectTelegram(repository=repository, senders=senders, clock=clock),
        detect_chat=DetectTelegramChat(repository=repository, senders=senders, clock=clock),
        test=SendTestMessage(repository=repository, senders=senders),
        set_enabled=SetChannelEnabled(repository=repository, clock=clock),
        disconnect=DisconnectChannel(repository=repository),
    )


def build_text_delivery(container: Any) -> DeliverText:
    """The reusable delivery entry point for background workers (no request scope)."""
    return DeliverText(repository=_repository(container), senders=_senders(container))


def build_document_delivery(container: Any) -> DeliverDocument:
    """Delivery of files (e.g. the daily PDF report) for background workers."""
    return DeliverDocument(repository=_repository(container), senders=_senders(container))
