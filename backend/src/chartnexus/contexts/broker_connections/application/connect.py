"""Connecting a broker account.

The flow is:

1. ``SaveCredentials`` stores the tenant's own API application keys.
2. ``StartConnect`` mints a single-use ``state`` bound to the tenant and user,
   and returns the broker's consent URL.
3. The user authorises at the broker and is returned with ``code`` + ``state``.
4. ``CompleteConnect`` consumes the state, exchanges the code, proves the token
   works, and stores it encrypted.

Step 2/4 state binding is the correction the source architecture calls for: its
own callback accepts a code without tying it to whoever began the flow, so
anyone who can reach the endpoint can attach a broker account to it.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from chartnexus.contexts.broker_connections.application.dto import (
    AuthorizationView,
    ConnectionView,
)
from chartnexus.contexts.broker_connections.application.ports import (
    BrokerConnectionRepository,
    BrokerOAuthClient,
    Clock,
    ConnectionCacheInvalidator,
    ConnectStateStore,
    PendingConnection,
    UnitOfWork,
)
from chartnexus.contexts.broker_connections.domain.connection import BrokerConnection
from chartnexus.contexts.broker_connections.domain.errors import (
    CredentialsMissingError,
    OAuthStateError,
)
from chartnexus.contexts.broker_connections.domain.value_objects import (
    BrokerCredentials,
    BrokerName,
)
from chartnexus.shared_kernel.types.identifiers import TenantId, UserId

_STATE_BYTES = 32


@dataclass(frozen=True, slots=True)
class ConnectPolicy:
    redirect_uri: str
    state_ttl_seconds: int = 600


@dataclass(frozen=True, slots=True)
class SaveCredentialsCommand:
    tenant_id: TenantId
    app_id: str
    secret: str
    broker: BrokerName = BrokerName.FYERS


@dataclass(frozen=True, slots=True)
class StartConnectCommand:
    tenant_id: TenantId
    user_id: UserId
    broker: BrokerName = BrokerName.FYERS
    redirect_to: str | None = None


@dataclass(frozen=True, slots=True)
class CompleteConnectCommand:
    code: str
    state: str
    broker: BrokerName = BrokerName.FYERS


class SaveCredentials:
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

    async def __call__(self, command: SaveCredentialsCommand) -> ConnectionView:
        credentials = BrokerCredentials.parse(command.app_id, command.secret)
        now = self._clock.now()

        connection = await self._connections.find(command.tenant_id, command.broker)
        if connection is None:
            connection = BrokerConnection.start(
                tenant_id=command.tenant_id,
                broker=command.broker,
                credentials=credentials,
                now=now,
            )
            await self._connections.add(connection)
        else:
            connection.replace_credentials(credentials, now)
            await self._connections.update(connection)

        await self._uow.commit()
        # New keys mean any provider cached against the old ones is wrong.
        await self._cache.invalidate(command.tenant_id, command.broker)

        return ConnectionView.of(connection, redirect_uri=self._policy.redirect_uri)


class StartConnect:
    def __init__(
        self,
        *,
        connections: BrokerConnectionRepository,
        oauth: BrokerOAuthClient,
        states: ConnectStateStore,
        policy: ConnectPolicy,
    ) -> None:
        self._connections = connections
        self._oauth = oauth
        self._states = states
        self._policy = policy

    async def __call__(self, command: StartConnectCommand) -> AuthorizationView:
        connection = await self._connections.find(command.tenant_id, command.broker)
        if connection is None:
            raise CredentialsMissingError
        credentials = connection.require_credentials()

        state = secrets.token_urlsafe(_STATE_BYTES)
        await self._states.save(
            state,
            PendingConnection(
                tenant_id=command.tenant_id,
                user_id=command.user_id,
                broker=command.broker,
                redirect_to=_safe_redirect(command.redirect_to),
            ),
            ttl_seconds=self._policy.state_ttl_seconds,
        )

        return AuthorizationView(
            authorization_url=self._oauth.build_authorization_url(
                credentials=credentials,
                state=state,
                redirect_uri=self._policy.redirect_uri,
            ),
            state=state,
            expires_in_seconds=self._policy.state_ttl_seconds,
        )


class CompleteConnect:
    def __init__(
        self,
        *,
        connections: BrokerConnectionRepository,
        oauth: BrokerOAuthClient,
        states: ConnectStateStore,
        clock: Clock,
        uow: UnitOfWork,
        policy: ConnectPolicy,
        cache: ConnectionCacheInvalidator,
    ) -> None:
        self._connections = connections
        self._oauth = oauth
        self._states = states
        self._clock = clock
        self._uow = uow
        self._policy = policy
        self._cache = cache

    async def __call__(self, command: CompleteConnectCommand) -> ConnectionView:
        pending = await self._states.consume(command.state)
        if pending is None or pending.broker is not command.broker:
            # Unknown, expired, replayed, or for a different broker. All are
            # indistinguishable to the caller by design.
            raise OAuthStateError

        # The tenant comes from the stored state, never from the request. This
        # is what stops a code being attached to somebody else's tenant.
        connection = await self._connections.find(pending.tenant_id, pending.broker)
        if connection is None:
            raise OAuthStateError
        credentials = connection.require_credentials()

        tokens = await self._oauth.exchange_code(
            credentials=credentials,
            code=command.code,
            redirect_uri=self._policy.redirect_uri,
        )

        # Prove the token before claiming a connection. A token the broker will
        # not honour is worse than no token: it makes the UI lie.
        profile = await self._oauth.fetch_profile(
            credentials=credentials, access_token=tokens.access_token
        )

        now = self._clock.now()
        connection.complete_connect(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            profile=profile,
            expires_at=tokens.expires_at,
            connected_by=pending.user_id,
            now=now,
        )
        await self._connections.update(connection)
        await self._uow.commit()
        await self._cache.invalidate(pending.tenant_id, pending.broker)

        return ConnectionView.of(connection, redirect_uri=self._policy.redirect_uri)


def _safe_redirect(target: str | None) -> str | None:
    """Same-site relative paths only, so the callback cannot become an open redirect."""
    if not target:
        return None
    if not target.startswith("/") or target.startswith("//"):
        return None
    return target[:512]
