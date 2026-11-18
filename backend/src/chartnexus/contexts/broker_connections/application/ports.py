"""Ports the broker connection use cases depend on."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from chartnexus.contexts.broker_connections.domain.connection import BrokerConnection
from chartnexus.contexts.broker_connections.domain.value_objects import (
    BrokerCredentials,
    BrokerName,
    BrokerProfile,
)
from chartnexus.shared_kernel.types.identifiers import TenantId, UserId


@runtime_checkable
class BrokerConnectionRepository(Protocol):
    async def find(self, tenant_id: TenantId, broker: BrokerName) -> BrokerConnection | None:
        """The tenant's connection for a broker, in any status."""
        ...

    async def find_active(self, tenant_id: TenantId) -> BrokerConnection | None:
        """The tenant's one active connection, whichever broker it is with.

        A tenant has at most one active broker at a time — enforced by the
        aggregate's use cases and by a partial unique index — so this is the
        connection that serves the tenant's market data.
        """
        ...

    async def find_others(self, tenant_id: TenantId, broker: BrokerName) -> list[BrokerConnection]:
        """The tenant's connections with every broker except ``broker``."""
        ...

    async def find_market_feed(self, now: datetime | None = None) -> BrokerConnection | None:
        """Any tenant's active, unexpired connection, preferring Kite.

        For background jobs that capture market-wide data. Kite is preferred
        because its quote endpoint returns open interest for up to five hundred
        instruments per call, where FYERS needs one depth call per contract.

        A connection whose known expiry has passed (``now``, default the current
        time) is skipped, so a Kite token that lapsed at 06:00 IST gives way to
        a working FYERS connection instead of shadowing it.
        """
        ...

    async def find_any_active(self, broker: BrokerName) -> BrokerConnection | None:
        """Any one tenant's active connection for a broker.

        For background jobs that capture market-wide data (option-chain
        snapshots): the open interest on an index is the same fact for every
        tenant, so a single working credential is enough. Returns ``None`` when
        no tenant has an active connection, letting the caller fall back to mock.
        """
        ...

    async def add(self, connection: BrokerConnection) -> None: ...

    async def update(self, connection: BrokerConnection) -> None: ...


@runtime_checkable
class TokenCipher(Protocol):
    """Authenticated encryption for credentials at rest.

    ``aad`` is authenticated but not encrypted. Callers pass the location a
    value belongs to — tenant, broker, column — so a ciphertext copied into a
    different row or column fails to decrypt instead of being accepted. It must
    match between encrypt and decrypt.
    """

    def encrypt(self, plaintext: str, *, aad: str | None = None) -> str: ...

    def decrypt(self, ciphertext: str, *, aad: str | None = None) -> str: ...


@dataclass(frozen=True, slots=True)
class AuthorizationRequest:
    authorization_url: str
    state: str


@dataclass(frozen=True, slots=True)
class BrokerTokens:
    """What the broker returns from a successful code exchange."""

    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None


@runtime_checkable
class BrokerOAuthClient(Protocol):
    """The broker's OAuth and identity surface.

    Deliberately narrow: market data is a separate port, so a broker that only
    ever supplies authentication can implement this alone.
    """

    def build_authorization_url(
        self, *, credentials: BrokerCredentials, state: str, redirect_uri: str
    ) -> str: ...

    async def exchange_code(
        self, *, credentials: BrokerCredentials, code: str, redirect_uri: str
    ) -> BrokerTokens:
        """Trade a one-time authorization code for a token.

        Raises ``BrokerRejectedError`` when the broker refuses, and
        ``BrokerUnavailableError`` when it cannot be reached.
        """
        ...

    async def fetch_profile(
        self, *, credentials: BrokerCredentials, access_token: str
    ) -> BrokerProfile:
        """Prove a token works by using it.

        Token presence is not connection: this is what makes status honest.
        """
        ...

    async def revoke_token(self, *, credentials: BrokerCredentials, access_token: str) -> None:
        """Ask the broker to invalidate a token, where the broker supports it.

        Best-effort: callers drop the token locally whatever happens here. A
        broker with no revocation endpoint implements this as a no-op.
        """
        ...


@dataclass(frozen=True, slots=True)
class PendingConnection:
    """A connection attempt that has started but not returned."""

    tenant_id: TenantId
    user_id: UserId
    broker: BrokerName
    redirect_to: str | None = None


@runtime_checkable
class ConnectStateStore(Protocol):
    """Short-lived, single-use storage binding an OAuth state to its initiator.

    Without this the callback would accept any code from anyone and attach the
    resulting token to whichever tenant happened to ask.
    """

    async def save(self, state: str, pending: PendingConnection, *, ttl_seconds: int) -> None: ...

    async def consume(self, state: str) -> PendingConnection | None:
        """Fetch and delete atomically, so a state cannot be replayed."""
        ...


@runtime_checkable
class ConnectionCacheInvalidator(Protocol):
    """Drops any cached provider built from a connection that just changed.

    Without it the UI can report "disconnected" while requests keep succeeding
    against a cached client.
    """

    async def invalidate(self, tenant_id: TenantId, broker: BrokerName) -> None: ...


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...


@runtime_checkable
class UnitOfWork(Protocol):
    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
