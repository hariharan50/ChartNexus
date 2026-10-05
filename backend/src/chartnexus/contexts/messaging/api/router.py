"""Messaging endpoints — connect and manage a user's delivery channels.

Every route is authenticated and scoped to the caller's own user. v1 supports
Telegram: save the bot token, link the chat, send a test, enable/disable, and
disconnect. Updates (the MME100 briefing) are pushed to ready channels by the
background worker, not from here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Response, status

from chartnexus.contexts.messaging.api.dependencies import Services
from chartnexus.contexts.messaging.api.schemas import (
    ChannelResponse,
    ChannelsResponse,
    ConnectTelegramRequest,
    DetectChatRequest,
    SetEnabledRequest,
)
from chartnexus.contexts.messaging.application.use_cases import (
    ConnectTelegramCommand,
    DetectTelegramChatCommand,
    SetChannelEnabledCommand,
)
from chartnexus.contexts.messaging.domain.channel import Channel
from chartnexus.infrastructure.transport.http.dependencies import CurrentPrincipal

router = APIRouter(prefix="/messaging", tags=["messaging"])

ChannelParam = Annotated[str, Path(description="Channel id", examples=["telegram"])]


def _channel(value: str) -> Channel:
    try:
        return Channel(value.strip().lower())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown channel {value!r}."
        ) from exc


@router.get(
    "/channels",
    response_model=ChannelsResponse,
    summary="The user's connected channels",
)
async def list_channels(principal: CurrentPrincipal, services: Services) -> ChannelsResponse:
    return ChannelsResponse.of(await services.get(principal.user_id))


@router.put(
    "/telegram",
    response_model=ChannelResponse,
    summary="Save (and verify) the user's Telegram bot token",
    responses={422: {"description": "The token is invalid or was rejected by Telegram"}},
)
async def connect_telegram(
    payload: ConnectTelegramRequest,
    principal: CurrentPrincipal,
    services: Services,
) -> ChannelResponse:
    view = await services.connect_telegram(
        ConnectTelegramCommand(
            user_id=principal.user_id,
            tenant_id=principal.tenant_id,
            bot_token=payload.bot_token,
        )
    )
    return ChannelResponse.of(view)


@router.post(
    "/telegram/detect-chat",
    response_model=ChannelResponse,
    summary="Link the chat to deliver to (auto-detected, or a manual chat id)",
    responses={422: {"description": "No chat found and none supplied"}},
)
async def detect_chat(
    payload: DetectChatRequest,
    principal: CurrentPrincipal,
    services: Services,
) -> ChannelResponse:
    view = await services.detect_chat(
        DetectTelegramChatCommand(user_id=principal.user_id, chat_id=payload.chat_id)
    )
    return ChannelResponse.of(view)


@router.post(
    "/telegram/test",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Send a test message to confirm the connection",
    responses={
        204: {"description": "Test message sent"},
        422: {"description": "Channel not connected or not linked"},
    },
)
async def send_test(principal: CurrentPrincipal, services: Services) -> Response:
    await services.test(principal.user_id, Channel.TELEGRAM)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/channels/{channel_id}",
    response_model=ChannelResponse,
    summary="Enable or disable delivery to a channel",
)
async def set_enabled(
    payload: SetEnabledRequest,
    principal: CurrentPrincipal,
    services: Services,
    channel_id: ChannelParam,
) -> ChannelResponse:
    view = await services.set_enabled(
        SetChannelEnabledCommand(
            user_id=principal.user_id, channel=_channel(channel_id), enabled=payload.enabled
        )
    )
    return ChannelResponse.of(view)


@router.delete(
    "/channels/{channel_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Disconnect a channel",
)
async def disconnect(
    principal: CurrentPrincipal,
    services: Services,
    channel_id: ChannelParam,
) -> Response:
    await services.disconnect(principal.user_id, _channel(channel_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
