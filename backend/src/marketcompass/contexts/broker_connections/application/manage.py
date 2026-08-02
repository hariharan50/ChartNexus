"""Inspecting and ending a broker connection."""

from __future__ import annotations

from dataclasses import dataclass

from marketcompass.contexts.broker_connections.application.connect import ConnectPolicy
from marketcompass.contexts.broker_connections.application.dto import ConnectionView
from marketcompass.contexts.broker_connections.application.ports import (
    BrokerConnectionRepository,
    BrokerOAuthClient,
    Clock,
    ConnectionCacheInvalidator,
    UnitOfWork,
)
from marketcompass.contexts.broker_connections.domain.errors import (
    BrokerRejectedError,
    BrokerUnavailableError,
)
from marketcompass.contexts.broker_connections.domain.value_objects import BrokerName
from marketcompass.shared_kernel.types.identifiers import TenantId


@dataclass(frozen=True, slots=True)
class ConnectionQuery:
    tenant_id: TenantId
    broker: BrokerName = BrokerName.FYERS


class GetConnectionStatus:
    """Report the connection, verifying the token against the broker.

    Token presence is not proof of anything — the source architecture is
    explicit that status must call the broker's profile endpoint. A rejection
    is recorded so the next caller does not have to re-discover it.
    """

    def __init__(
        self,
        *,
        connections: BrokerConnectionRepository,
        oauth: BrokerOAuthClient,
        clock: Clock,
        uow: UnitOfWork,
        policy: ConnectPolicy,
    ) -> None:
        self._connections = connections
        self._oauth = oauth
        self._clock = clock
        self._uow = uow
        self._policy = policy

    async def __call__(self, query: ConnectionQuery, *, verify: bool = True) -> ConnectionView:
        connection = await self._connections.find(query.tenant_id, query.broker)
        if connection is None or not connection.is_connected or not verify:
            return ConnectionView.of(connection, redirect_uri=self._policy.redirect_uri)

        credentials = connection.require_credentials()
        now = self._clock.now()
        try:
            profile = await self._oauth.fetch_profile(
                credentials=credentials, access_token=connection.access_token or ""
            )
        except BrokerRejectedError as exc:
            connection.record_rejected(exc.message, now)
            await self._connections.update(connection)
            await self._uow.commit()
        except BrokerUnavailableError:
            # The broker being down does not mean our token is bad. Report the
            # last known state rather than marking the connection expired.
            pass
        else:
            connection.record_validated(profile, now)
            await self._connections.update(connection)
            await self._uow.commit()

        return ConnectionView.of(connection, redirect_uri=self._policy.redirect_uri)


class DisconnectBroker:
    """Drop the token, keep the stored API application."""

    def __init__(
        self,
        *,
        connections: BrokerConnectionRepository,
        clock: Clock,
        uow: UnitOfWork,
        policy: ConnectPolicy,
        cache: ConnectionCacheInvalidator,
    ) -> None:
        self._connections = connections
        self._clock = clock
        self._uow = uow
        self._policy = policy
        self._cache = cache

    async def __call__(self, query: ConnectionQuery) -> ConnectionView:
        connection = await self._connections.find(query.tenant_id, query.broker)
        if connection is None:
            # Already disconnected. Idempotent: there is nothing to report as
            # an error, and saying so leaks nothing useful.
            return ConnectionView.of(None, redirect_uri=self._policy.redirect_uri)

        connection.disconnect(self._clock.now())
        await self._connections.update(connection)
        await self._uow.commit()
        await self._cache.invalidate(query.tenant_id, query.broker)

        return ConnectionView.of(connection, redirect_uri=self._policy.redirect_uri)


class RevokeBrokerCredentials:
    """Drop the token and the stored API application.

    Distinct from disconnect: reconnecting afterwards requires re-entering keys.
    """

    def __init__(
        self,
        *,
        connections: BrokerConnectionRepository,
        clock: Clock,
        uow: UnitOfWork,
        policy: ConnectPolicy,
        cache: ConnectionCacheInvalidator,
    ) -> None:
        self._connections = connections
        self._clock = clock
        self._uow = uow
        self._policy = policy
        self._cache = cache

    async def __call__(self, query: ConnectionQuery) -> ConnectionView:
        connection = await self._connections.find(query.tenant_id, query.broker)
        if connection is None:
            return ConnectionView.of(None, redirect_uri=self._policy.redirect_uri)

        connection.revoke(self._clock.now())
        await self._connections.update(connection)
        await self._uow.commit()
        await self._cache.invalidate(query.tenant_id, query.broker)

        return ConnectionView.of(connection, redirect_uri=self._policy.redirect_uri)
