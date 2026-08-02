"""Data crossing the broker-connection application boundary.

Nothing here may carry a token or a secret. The view a caller receives is the
same view that can safely be logged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from marketcompass.contexts.broker_connections.domain.connection import BrokerConnection


@dataclass(frozen=True, slots=True)
class ConnectionView:
    broker: str
    status: str
    configured: bool
    """Credentials are stored, so the connect button can be offered."""

    connected: bool
    """The broker accepted our token the last time we asked."""

    masked_app_id: str | None
    redirect_uri: str
    display_name: str | None
    broker_user_id: str | None
    connected_at: datetime | None
    last_validated_at: datetime | None
    last_error: str | None

    @classmethod
    def of(cls, connection: BrokerConnection | None, *, redirect_uri: str) -> ConnectionView:
        if connection is None:
            return cls(
                broker="fyers",
                status="pending",
                configured=False,
                connected=False,
                masked_app_id=None,
                redirect_uri=redirect_uri,
                display_name=None,
                broker_user_id=None,
                connected_at=None,
                last_validated_at=None,
                last_error=None,
            )

        return cls(
            broker=connection.broker.value,
            status=connection.status.value,
            configured=connection.has_credentials,
            connected=connection.is_connected,
            masked_app_id=connection.masked_app_id,
            redirect_uri=redirect_uri,
            display_name=connection.profile.display_name if connection.profile else None,
            broker_user_id=connection.profile.broker_user_id if connection.profile else None,
            connected_at=connection.connected_at,
            last_validated_at=connection.last_validated_at,
            last_error=connection.last_error,
        )


@dataclass(frozen=True, slots=True)
class AuthorizationView:
    authorization_url: str
    state: str
    expires_in_seconds: int
