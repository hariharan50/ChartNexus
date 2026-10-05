"""The BrokerConnection aggregate.

Holds one tenant's link to one broker across its whole lifecycle: credentials
saved, OAuth completed, token rejected, deliberately disconnected.

Secrets live here as plaintext in memory for exactly as long as an operation
needs them; encryption is the repository's job, because the algorithm is an
infrastructure concern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from chartnexus.contexts.broker_connections.domain.errors import (
    ConnectionExpiredError,
    CredentialsMissingError,
    NotConnectedError,
)
from chartnexus.contexts.broker_connections.domain.value_objects import (
    BrokerCredentials,
    BrokerName,
    BrokerProfile,
    ConnectionStatus,
)
from chartnexus.shared_kernel.types.identifiers import (
    BrokerConnectionId,
    TenantId,
    UserId,
    new_id,
)


@dataclass(slots=True)
class BrokerConnection:
    id: BrokerConnectionId
    tenant_id: TenantId
    broker: BrokerName
    status: ConnectionStatus
    credentials: BrokerCredentials | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    profile: BrokerProfile | None = None
    connected_at: datetime | None = None
    revoked_at: datetime | None = None
    expires_at: datetime | None = None
    last_validated_at: datetime | None = None
    last_error: str | None = None
    connected_by: UserId | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    _events: list[str] = field(default_factory=list, repr=False)

    # -- construction -------------------------------------------------------

    @classmethod
    def start(
        cls,
        *,
        tenant_id: TenantId,
        broker: BrokerName,
        credentials: BrokerCredentials,
        now: datetime,
    ) -> BrokerConnection:
        """Create a connection holding credentials but no token yet."""
        return cls(
            id=BrokerConnectionId(new_id()),
            tenant_id=tenant_id,
            broker=broker,
            status=ConnectionStatus.PENDING,
            credentials=credentials,
            created_at=now,
            updated_at=now,
        )

    # -- queries ------------------------------------------------------------

    @property
    def has_credentials(self) -> bool:
        return self.credentials is not None

    @property
    def is_connected(self) -> bool:
        return self.status is ConnectionStatus.ACTIVE and self.access_token is not None

    @property
    def masked_app_id(self) -> str | None:
        if self.credentials is None:
            return None
        app_id = self.credentials.app_id
        # The suffix after the dash identifies the app; the prefix is the part
        # worth obscuring.
        head, _, tail = app_id.partition("-")
        visible = head[:4]
        return f"{visible}{'*' * max(0, len(head) - 4)}-{tail}" if tail else visible

    def require_credentials(self) -> BrokerCredentials:
        if self.credentials is None:
            raise CredentialsMissingError
        return self.credentials

    def require_access_token(self) -> str:
        """Return the token, or explain precisely why there isn't one."""
        if self.status is ConnectionStatus.EXPIRED:
            raise ConnectionExpiredError
        if self.access_token is None or self.status is not ConnectionStatus.ACTIVE:
            raise NotConnectedError
        return self.access_token

    # -- behaviour ----------------------------------------------------------

    def replace_credentials(self, credentials: BrokerCredentials, now: datetime) -> None:
        """Save new API application keys.

        Changing the application invalidates any token issued under the old one,
        so the connection drops back to pending rather than claiming to still
        be live.
        """
        changed = self.credentials is None or self.credentials.app_id != credentials.app_id
        self.credentials = credentials
        if changed and self.status is ConnectionStatus.ACTIVE:
            self.access_token = None
            self.refresh_token = None
            self.status = ConnectionStatus.PENDING
        elif self.status is ConnectionStatus.REVOKED:
            self.status = ConnectionStatus.PENDING
        self.updated_at = now

    def complete_connect(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        profile: BrokerProfile | None,
        now: datetime,
        expires_at: datetime | None = None,
        connected_by: UserId | None = None,
    ) -> None:
        """Record a successful OAuth exchange."""
        if not access_token:
            msg = "cannot complete a connection without an access token"
            raise ValueError(msg)

        self.access_token = access_token
        self.refresh_token = refresh_token
        self.profile = profile
        self.status = ConnectionStatus.ACTIVE
        self.connected_at = now
        self.last_validated_at = now
        self.expires_at = expires_at
        self.revoked_at = None
        self.last_error = None
        self.connected_by = connected_by
        self.updated_at = now

    def record_validated(self, profile: BrokerProfile | None, now: datetime) -> None:
        """The broker confirmed the token still works."""
        self.last_validated_at = now
        self.last_error = None
        if profile is not None:
            self.profile = profile
        if self.status is ConnectionStatus.EXPIRED:
            self.status = ConnectionStatus.ACTIVE
        self.updated_at = now

    def record_rejected(self, reason: str, now: datetime) -> None:
        """The broker refused the token.

        The token is dropped immediately — keeping it would mean every
        subsequent request re-learns the same rejection.
        """
        self.access_token = None
        self.refresh_token = None
        self.status = ConnectionStatus.EXPIRED
        self.last_error = reason[:255]
        self.last_validated_at = now
        self.updated_at = now

    def disconnect(self, now: datetime) -> None:
        """Drop the token, keep the credentials.

        Reconnecting is then one OAuth round trip with no re-typing of keys.
        """
        self.access_token = None
        self.refresh_token = None
        self.profile = None
        self.status = ConnectionStatus.PENDING if self.has_credentials else ConnectionStatus.REVOKED
        self.revoked_at = now
        self.updated_at = now

    def revoke(self, now: datetime) -> None:
        """Drop everything: token and stored API application."""
        self.access_token = None
        self.refresh_token = None
        self.credentials = None
        self.profile = None
        self.status = ConnectionStatus.REVOKED
        self.revoked_at = now
        self.updated_at = now
