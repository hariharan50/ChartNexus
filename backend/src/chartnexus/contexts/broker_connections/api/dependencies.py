"""Per-request assembly for the broker connection routes.

The broker comes from the URL path (``/broker/{broker}/…``), so one set of
routes serves FYERS and Kite. Each request gets the OAuth adapter and the
redirect URI for the broker it names.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from chartnexus.contexts.broker_connections.application.connect import (
    CompleteConnect,
    ConnectPolicy,
    SaveCredentials,
    StartConnect,
)
from chartnexus.contexts.broker_connections.application.manage import (
    DisconnectBroker,
    GetConnectionStatus,
    RevokeBrokerCredentials,
)
from chartnexus.contexts.broker_connections.application.ports import BrokerOAuthClient
from chartnexus.contexts.broker_connections.domain.value_objects import BrokerName
from chartnexus.infrastructure.brokers.fyers.authentication import FyersOAuthClient
from chartnexus.infrastructure.brokers.fyers.rest_client import FyersRestClient
from chartnexus.infrastructure.brokers.kite.authentication import KiteOAuthClient
from chartnexus.infrastructure.brokers.kite.rest_client import KiteEndpoints, KiteRestClient
from chartnexus.infrastructure.brokers.provider_resolver import ConnectionCacheReset
from chartnexus.infrastructure.cache.redis.session_store import RedisConnectStateStore
from chartnexus.infrastructure.persistence.postgresql.repositories.integration.broker_connection_repository import (
    SqlAlchemyBrokerConnectionRepository,
)
from chartnexus.infrastructure.time.clock import SystemClock
from chartnexus.infrastructure.transport.http.dependencies import (
    SessionUnitOfWork,
    get_container,
    get_session,
)


@dataclass(slots=True)
class BrokerServices:
    broker: BrokerName
    save_credentials: SaveCredentials
    start_connect: StartConnect
    complete_connect: CompleteConnect
    status: GetConnectionStatus
    disconnect: DisconnectBroker
    revoke: RevokeBrokerCredentials


def oauth_clients(request: Request) -> dict[BrokerName, BrokerOAuthClient]:
    """One OAuth adapter per broker, sharing the process's HTTP client."""
    container = get_container(request)
    settings = container.settings
    return {
        BrokerName.FYERS: FyersOAuthClient(
            FyersRestClient(container.http, timeout_seconds=settings.broker.request_timeout_seconds)
        ),
        BrokerName.KITE: KiteOAuthClient(
            KiteRestClient(
                container.http,
                endpoints=KiteEndpoints(
                    api_base=settings.kite.api_base, login_url=settings.kite.login_url
                ),
                timeout_seconds=settings.kite.request_timeout_seconds,
            )
        ),
    }


def redirect_uri_for(request: Request, broker: BrokerName) -> str:
    settings = get_container(request).settings
    uri: str = (
        settings.kite.redirect_uri
        if broker is BrokerName.KITE
        else settings.broker.fyers_redirect_uri
    )
    return uri


def build_broker_services(
    broker: BrokerName,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BrokerServices:
    container = get_container(request)
    clock = SystemClock()

    connections = SqlAlchemyBrokerConnectionRepository(session, container.token_cipher)
    uow = SessionUnitOfWork(session)
    clients = oauth_clients(request)
    oauth = clients[broker]
    states = RedisConnectStateStore(container.redis)
    cache = ConnectionCacheReset(connections)
    policy = ConnectPolicy(redirect_uri=redirect_uri_for(request, broker))

    return BrokerServices(
        broker=broker,
        save_credentials=SaveCredentials(
            connections=connections, clock=clock, uow=uow, policy=policy, cache=cache
        ),
        start_connect=StartConnect(
            connections=connections, oauth=oauth, states=states, policy=policy
        ),
        complete_connect=CompleteConnect(
            connections=connections,
            oauth=oauth,
            states=states,
            clock=clock,
            uow=uow,
            policy=policy,
            cache=cache,
            revokers=clients,
        ),
        status=GetConnectionStatus(
            connections=connections, oauth=oauth, clock=clock, uow=uow, policy=policy
        ),
        disconnect=DisconnectBroker(
            connections=connections, clock=clock, uow=uow, policy=policy, cache=cache, oauth=oauth
        ),
        revoke=RevokeBrokerCredentials(
            connections=connections, clock=clock, uow=uow, policy=policy, cache=cache, oauth=oauth
        ),
    )


Services = Annotated[BrokerServices, Depends(build_broker_services)]


@dataclass(slots=True)
class ConnectionsOverview:
    """Every broker's status for one tenant, without verifying tokens remotely."""

    statuses: dict[BrokerName, GetConnectionStatus]


def build_overview(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ConnectionsOverview:
    container = get_container(request)
    clock = SystemClock()
    connections = SqlAlchemyBrokerConnectionRepository(session, container.token_cipher)
    uow = SessionUnitOfWork(session)
    clients = oauth_clients(request)
    return ConnectionsOverview(
        statuses={
            broker: GetConnectionStatus(
                connections=connections,
                oauth=clients[broker],
                clock=clock,
                uow=uow,
                policy=ConnectPolicy(redirect_uri=redirect_uri_for(request, broker)),
            )
            for broker in BrokerName
        }
    )


Overview = Annotated[ConnectionsOverview, Depends(build_overview)]
