"""Per-request assembly for the broker connection routes."""

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
from chartnexus.infrastructure.brokers.fyers.authentication import FyersOAuthClient
from chartnexus.infrastructure.brokers.fyers.rest_client import FyersRestClient
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
    save_credentials: SaveCredentials
    start_connect: StartConnect
    complete_connect: CompleteConnect
    status: GetConnectionStatus
    disconnect: DisconnectBroker
    revoke: RevokeBrokerCredentials


def build_broker_services(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BrokerServices:
    container = get_container(request)
    settings = container.settings
    clock = SystemClock()

    connections = SqlAlchemyBrokerConnectionRepository(session, container.token_cipher)
    uow = SessionUnitOfWork(session)
    oauth = FyersOAuthClient(
        FyersRestClient(
            container.http,
            timeout_seconds=settings.broker.request_timeout_seconds,
        )
    )
    states = RedisConnectStateStore(container.redis)
    cache = ConnectionCacheReset(connections)
    policy = ConnectPolicy(redirect_uri=settings.broker.fyers_redirect_uri)

    return BrokerServices(
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
        ),
        status=GetConnectionStatus(
            connections=connections, oauth=oauth, clock=clock, uow=uow, policy=policy
        ),
        disconnect=DisconnectBroker(
            connections=connections, clock=clock, uow=uow, policy=policy, cache=cache
        ),
        revoke=RevokeBrokerCredentials(
            connections=connections, clock=clock, uow=uow, policy=policy, cache=cache
        ),
    )


Services = Annotated[BrokerServices, Depends(build_broker_services)]
