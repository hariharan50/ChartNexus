"""Broker connection endpoints.

Every route is authenticated and scoped to the caller's tenant. The OAuth
callback is authenticated too — unlike the source architecture's public
callback, because our frontend posts the code back rather than the broker
redirecting straight to the API. That removes the need for a public endpoint
entirely.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from marketcompass.contexts.broker_connections.api.dependencies import Services
from marketcompass.contexts.broker_connections.api.schemas import (
    AuthorizationResponse,
    CallbackRequest,
    ConnectionResponse,
    ConnectRequest,
    SaveCredentialsRequest,
)
from marketcompass.contexts.broker_connections.application.connect import (
    CompleteConnectCommand,
    SaveCredentialsCommand,
    StartConnectCommand,
)
from marketcompass.contexts.broker_connections.application.manage import ConnectionQuery
from marketcompass.infrastructure.transport.http.dependencies import CurrentPrincipal

router = APIRouter(prefix="/broker/fyers", tags=["broker"])


@router.get(
    "/status",
    response_model=ConnectionResponse,
    summary="Broker connection status",
    description=(
        "Verifies the stored token against the broker rather than reporting that one merely exists."
    ),
)
async def get_status(principal: CurrentPrincipal, services: Services) -> ConnectionResponse:
    view = await services.status(ConnectionQuery(tenant_id=principal.tenant_id))
    return ConnectionResponse.of(view)


@router.post(
    "/credentials",
    response_model=ConnectionResponse,
    status_code=status.HTTP_200_OK,
    summary="Save broker API credentials",
    responses={422: {"description": "The App ID or Secret ID is malformed"}},
)
async def save_credentials(
    payload: SaveCredentialsRequest,
    principal: CurrentPrincipal,
    services: Services,
) -> ConnectionResponse:
    view = await services.save_credentials(
        SaveCredentialsCommand(
            tenant_id=principal.tenant_id,
            app_id=payload.app_id,
            secret=payload.secret_id,
        )
    )
    return ConnectionResponse.of(view)


@router.post(
    "/connect",
    response_model=AuthorizationResponse,
    summary="Begin the broker OAuth flow",
    description=(
        "Returns the broker consent URL. The client sends the browser there; the "
        "broker returns to the configured redirect URI with `auth_code` and "
        "`state`, which the client posts to `/broker/fyers/callback`."
    ),
    responses={409: {"description": "No credentials have been saved yet"}},
)
async def connect(
    payload: ConnectRequest,
    principal: CurrentPrincipal,
    services: Services,
) -> AuthorizationResponse:
    view = await services.start_connect(
        StartConnectCommand(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            redirect_to=payload.redirect_to,
        )
    )
    return AuthorizationResponse.of(view)


@router.post(
    "/callback",
    response_model=ConnectionResponse,
    summary="Complete the broker OAuth flow",
    responses={
        422: {"description": "The state is unknown, expired, or already used"},
        502: {"description": "The broker rejected the exchange"},
    },
)
async def callback(
    payload: CallbackRequest,
    principal: CurrentPrincipal,  # noqa: ARG001 — authenticates the caller; the
    # tenant the token is bound to comes from the stored state, not from here.
    services: Services,
) -> ConnectionResponse:
    view = await services.complete_connect(
        CompleteConnectCommand(code=payload.auth_code, state=payload.state)
    )
    return ConnectionResponse.of(view)


@router.delete(
    "/connection",
    response_model=ConnectionResponse,
    summary="Disconnect, keeping saved credentials",
)
async def disconnect(principal: CurrentPrincipal, services: Services) -> ConnectionResponse:
    view = await services.disconnect(ConnectionQuery(tenant_id=principal.tenant_id))
    return ConnectionResponse.of(view)


@router.delete(
    "/credentials",
    response_model=ConnectionResponse,
    summary="Revoke: disconnect and remove saved credentials",
)
async def revoke(principal: CurrentPrincipal, services: Services) -> ConnectionResponse:
    view = await services.revoke(ConnectionQuery(tenant_id=principal.tenant_id))
    return ConnectionResponse.of(view)
