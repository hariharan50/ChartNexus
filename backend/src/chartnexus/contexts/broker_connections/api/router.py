"""Broker connection endpoints.

Every route is authenticated and scoped to the caller's tenant. The OAuth
callback is authenticated too — the broker returns the browser to a
*frontend* route, which posts the code here — so there is no public endpoint
at all.

One set of routes serves every broker: ``/broker/{broker}/…`` where
``broker`` is ``fyers`` or ``kite``. The original ``/broker/fyers/*`` URLs are
unchanged by this, so existing clients keep working.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Request, status

from chartnexus.contexts.broker_connections.api.dependencies import Overview, Services
from chartnexus.contexts.broker_connections.api.schemas import (
    AuthorizationResponse,
    CallbackRequest,
    ConnectionResponse,
    ConnectionsResponse,
    ConnectRequest,
    SaveCredentialsRequest,
)
from chartnexus.contexts.broker_connections.application.connect import (
    CompleteConnectCommand,
    SaveCredentialsCommand,
    StartConnectCommand,
)
from chartnexus.contexts.broker_connections.application.manage import ConnectionQuery
from chartnexus.contexts.broker_connections.domain.value_objects import BrokerName
from chartnexus.infrastructure.brokers.kite.sync import sync_after_connect
from chartnexus.infrastructure.transport.http.dependencies import CurrentPrincipal, get_container

router = APIRouter(prefix="/broker", tags=["broker"])


@router.get(
    "/connections",
    response_model=ConnectionsResponse,
    summary="Every broker connection for this account",
    description=(
        "One entry per supported broker, and which one is active. Does not call "
        "the brokers: use `/broker/{broker}/status` to verify a token."
    ),
)
async def list_connections(principal: CurrentPrincipal, overview: Overview) -> ConnectionsResponse:
    views = [
        await use_case(ConnectionQuery(tenant_id=principal.tenant_id, broker=broker), verify=False)
        for broker, use_case in overview.statuses.items()
    ]
    active = next((view.broker for view in views if view.connected), None)
    return ConnectionsResponse(
        active_broker=active,
        connections=[ConnectionResponse.of(view) for view in views],
    )


@router.get(
    "/{broker}/status",
    response_model=ConnectionResponse,
    summary="Broker connection status",
    description=(
        "Verifies the stored token against the broker rather than reporting that one merely exists."
    ),
)
async def get_status(principal: CurrentPrincipal, services: Services) -> ConnectionResponse:
    view = await services.status(
        ConnectionQuery(tenant_id=principal.tenant_id, broker=services.broker)
    )
    return ConnectionResponse.of(view)


@router.post(
    "/{broker}/credentials",
    response_model=ConnectionResponse,
    status_code=status.HTTP_200_OK,
    summary="Save broker API credentials",
    responses={422: {"description": "The key, secret or Client ID is malformed"}},
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
            broker=services.broker,
            client_id=payload.client_id,
        )
    )
    return ConnectionResponse.of(view)


@router.post(
    "/{broker}/connect",
    response_model=AuthorizationResponse,
    summary="Begin the broker login flow",
    description=(
        "Returns the broker's login URL. The client sends the browser there; the "
        "broker returns to the registered redirect URL with a one-time code "
        "(FYERS `auth_code`, Kite `request_token`) and `state`, which the client "
        "posts to `/broker/{broker}/callback`."
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
            broker=services.broker,
            redirect_to=payload.redirect_to,
        )
    )
    return AuthorizationResponse.of(view)


@router.post(
    "/{broker}/callback",
    response_model=ConnectionResponse,
    summary="Complete the broker login flow",
    description=(
        "Connecting one broker disconnects any other: a tenant has one active "
        "broker at a time. The other broker's credentials are kept."
    ),
    responses={
        409: {"description": "Logged in as an account other than the saved Client ID"},
        422: {"description": "The state is unknown, expired, or already used"},
        502: {"description": "The broker rejected the exchange"},
    },
)
async def callback(
    payload: CallbackRequest,
    principal: CurrentPrincipal,
    services: Services,
    request: Request,
    background: BackgroundTasks,
) -> ConnectionResponse:
    # The tenant the token is bound to comes from the stored state, not from
    # `principal`, which only authenticates the caller.
    view = await services.complete_connect(
        CompleteConnectCommand(code=payload.auth_code, state=payload.state, broker=services.broker)
    )
    if services.broker is BrokerName.KITE and view.connected:
        # Kite needs its instrument catalog before a chain or a future can be
        # resolved. Fetched after the response, so the user is not kept waiting
        # on a large download; it is idempotent with the 08:35 morning run.
        background.add_task(sync_after_connect, get_container(request), principal.tenant_id)
    return ConnectionResponse.of(view)


@router.delete(
    "/{broker}/connection",
    response_model=ConnectionResponse,
    summary="Disconnect, keeping saved credentials",
    description="Also ends the session at the broker where the broker supports it (Kite).",
)
async def disconnect(principal: CurrentPrincipal, services: Services) -> ConnectionResponse:
    view = await services.disconnect(
        ConnectionQuery(tenant_id=principal.tenant_id, broker=services.broker)
    )
    return ConnectionResponse.of(view)


@router.delete(
    "/{broker}/credentials",
    response_model=ConnectionResponse,
    summary="Revoke: disconnect and remove saved credentials",
)
async def revoke(principal: CurrentPrincipal, services: Services) -> ConnectionResponse:
    view = await services.revoke(
        ConnectionQuery(tenant_id=principal.tenant_id, broker=services.broker)
    )
    return ConnectionResponse.of(view)
