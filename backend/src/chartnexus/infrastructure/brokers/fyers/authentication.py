"""FYERS OAuth adapter.

Implements the ``BrokerOAuthClient`` port: build the consent URL, trade the
one-time code for a token, and prove a token works by fetching the profile.

The token never leaves this layer except to be stored encrypted — it is not
logged, not returned to a caller, and not placed in any error message.
"""

from __future__ import annotations

from typing import Any

from chartnexus.contexts.broker_connections.application.ports import BrokerTokens
from chartnexus.contexts.broker_connections.domain.errors import BrokerRejectedError
from chartnexus.contexts.broker_connections.domain.value_objects import (
    BrokerCredentials,
    BrokerProfile,
)
from chartnexus.infrastructure.brokers.fyers.rest_client import FyersRestClient


class FyersOAuthClient:
    """Implements the ``BrokerOAuthClient`` port."""

    def __init__(self, rest: FyersRestClient) -> None:
        self._rest = rest

    def build_authorization_url(
        self, *, credentials: BrokerCredentials, state: str, redirect_uri: str
    ) -> str:
        return self._rest.build_authorization_url(
            app_id=credentials.app_id, redirect_uri=redirect_uri, state=state
        )

    async def exchange_code(
        self,
        *,
        credentials: BrokerCredentials,
        code: str,
        redirect_uri: str,  # noqa: ARG002 — FYERS validates it against the app registration
    ) -> BrokerTokens:
        payload = await self._rest.exchange_auth_code(
            app_id=credentials.app_id,
            secret_id=credentials.secret,
            auth_code=code,
        )

        access_token = str(payload.get("access_token") or "")
        if not access_token:
            # A 200 with no token means the code was already used or was issued
            # for different keys. Both need a fresh authorization round.
            raise BrokerRejectedError("The broker did not return an access token.")

        refresh_token = payload.get("refresh_token")
        return BrokerTokens(
            access_token=access_token,
            refresh_token=str(refresh_token) if refresh_token else None,
        )

    async def fetch_profile(
        self, *, credentials: BrokerCredentials, access_token: str
    ) -> BrokerProfile:
        payload = await self._rest.fetch_profile(
            app_id=credentials.app_id, access_token=access_token
        )
        return _to_profile(payload)


def _to_profile(payload: dict[str, Any]) -> BrokerProfile:
    """Extract only the fields worth showing a user.

    The full profile carries PAN, bank details, and address. None of that is
    needed to display "connected as ...", so none of it is retained.
    """
    data = payload.get("data")
    if not isinstance(data, dict):
        data = payload

    return BrokerProfile(
        broker_user_id=str(data.get("fy_id") or data.get("id") or ""),
        display_name=str(data.get("name") or data.get("display_name") or "").strip(),
        email=_optional(data.get("email_id") or data.get("email")),
    )


def _optional(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
