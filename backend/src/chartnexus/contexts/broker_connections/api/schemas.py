"""Wire contract for broker connection endpoints.

Nothing in this module can carry a token or a secret. The request models accept
a secret; no response model has a field that could hold one.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from chartnexus.contexts.broker_connections.application.dto import (
    AuthorizationView,
    ConnectionView,
)


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SaveCredentialsRequest(_Schema):
    app_id: str = Field(
        min_length=6,
        max_length=32,
        examples=["ABCDE123XY-100", "abcd1234efgh5678"],
        description="FYERS: the App ID. Kite: the API key. From your broker's developer console.",
    )
    secret_id: str = Field(
        min_length=5,
        max_length=64,
        description="FYERS: the Secret ID. Kite: the API secret. Stored encrypted, never returned.",
    )
    client_id: str | None = Field(
        default=None,
        max_length=16,
        examples=["AB1234"],
        description=(
            "Optional. The broker login ID you intend to connect as. When set, a "
            "login as any other account is refused and nothing is stored."
        ),
    )


class ConnectRequest(_Schema):
    redirect_to: str | None = Field(
        default=None,
        max_length=512,
        description="Relative path to return to. Absolute URLs are ignored.",
    )


class CallbackRequest(_Schema):
    """What the broker hands back via the frontend callback route."""

    auth_code: str = Field(min_length=1, max_length=4096)
    state: str = Field(min_length=1, max_length=512)


class ConnectionResponse(_Schema):
    broker: str
    status: str
    configured: bool
    connected: bool
    masked_app_id: str | None
    redirect_uri: str
    display_name: str | None
    broker_user_id: str | None
    connected_at: datetime | None
    last_validated_at: datetime | None
    last_error: str | None
    expires_at: datetime | None = None
    client_id: str | None = None

    @classmethod
    def of(cls, view: ConnectionView) -> ConnectionResponse:
        return cls(
            broker=view.broker,
            status=view.status,
            configured=view.configured,
            connected=view.connected,
            masked_app_id=view.masked_app_id,
            redirect_uri=view.redirect_uri,
            display_name=view.display_name,
            broker_user_id=view.broker_user_id,
            connected_at=view.connected_at,
            last_validated_at=view.last_validated_at,
            last_error=view.last_error,
            expires_at=view.expires_at,
            client_id=view.client_id,
        )


class ConnectionsResponse(_Schema):
    """Every broker for the caller's tenant, and which one serves their data."""

    active_broker: str | None
    connections: list[ConnectionResponse]


class AuthorizationResponse(_Schema):
    authorization_url: str
    state: str
    expires_in_seconds: int

    @classmethod
    def of(cls, view: AuthorizationView) -> AuthorizationResponse:
        return cls(
            authorization_url=view.authorization_url,
            state=view.state,
            expires_in_seconds=view.expires_in_seconds,
        )
