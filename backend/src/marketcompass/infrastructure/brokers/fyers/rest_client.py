"""The FYERS HTTP contract.

**Every FYERS URL, header and payload shape in this application lives here.**
Nothing else knows how the broker's API is spelled. That is deliberate: their
endpoint paths and field names are the part most likely to change, and this file
is meant to be the only casualty when they do.

FYERS API v3 is plain HTTPS, so this uses httpx directly rather than the
official SDK. The SDK is synchronous and pulls in ~26 transitive packages —
including an ``asyncio`` backport that shadows the standard library, and the AWS
SDK — none of which this integration needs.

Response convention: every FYERS response carries ``s`` ("ok" / "error") and
usually ``code``. Success is ``s == "ok"`` or ``code == 200``; anything else is
an error whose ``message`` is safe to log but not to show a user verbatim.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from marketcompass.contexts.broker_connections.domain.errors import (
    BrokerRejectedError,
    BrokerUnavailableError,
)

# The account/auth host and the market-data host differ on FYERS.
DEFAULT_API_BASE = "https://api-t1.fyers.in/api/v3"
DEFAULT_DATA_BASE = "https://api-t1.fyers.in/data"

_OK_STATUS = "ok"
_OK_CODE = 200
_MAX_MESSAGE_LENGTH = 200


@dataclass(frozen=True, slots=True)
class FyersEndpoints:
    """Endpoint layout, overridable so a path change needs no code edit."""

    api_base: str = DEFAULT_API_BASE
    data_base: str = DEFAULT_DATA_BASE

    @property
    def generate_authcode(self) -> str:
        return f"{self.api_base}/generate-authcode"

    @property
    def validate_authcode(self) -> str:
        return f"{self.api_base}/validate-authcode"

    @property
    def profile(self) -> str:
        return f"{self.api_base}/profile"

    @property
    def quotes(self) -> str:
        return f"{self.data_base}/quotes"

    @property
    def option_chain(self) -> str:
        return f"{self.data_base}/options-chain-v3"


def app_id_hash(app_id: str, secret_id: str) -> str:
    """SHA-256 of ``"{app_id}:{secret_id}"``.

    FYERS uses this so the secret itself never travels on the exchange request.
    """
    return hashlib.sha256(f"{app_id}:{secret_id}".encode()).hexdigest()


def authorization_header(app_id: str, access_token: str) -> str:
    """Data requests authenticate as ``<app_id>:<access_token>``."""
    return f"{app_id}:{access_token}"


class FyersRestClient:
    """Thin transport. Understands FYERS' envelope, nothing about our domain."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        endpoints: FyersEndpoints | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._http = http
        self._endpoints = endpoints or FyersEndpoints()
        self._timeout = timeout_seconds

    @property
    def endpoints(self) -> FyersEndpoints:
        return self._endpoints

    def build_authorization_url(self, *, app_id: str, redirect_uri: str, state: str) -> str:
        parameters = {
            "client_id": app_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
        }
        return f"{self._endpoints.generate_authcode}?{urlencode(parameters)}"

    async def exchange_auth_code(
        self, *, app_id: str, secret_id: str, auth_code: str
    ) -> dict[str, Any]:
        return await self._post(
            self._endpoints.validate_authcode,
            payload={
                "grant_type": "authorization_code",
                "appIdHash": app_id_hash(app_id, secret_id),
                "code": auth_code,
            },
        )

    async def fetch_profile(self, *, app_id: str, access_token: str) -> dict[str, Any]:
        return await self._get(self._endpoints.profile, app_id=app_id, access_token=access_token)

    async def fetch_quotes(self, *, app_id: str, access_token: str, symbols: str) -> dict[str, Any]:
        return await self._get(
            self._endpoints.quotes,
            app_id=app_id,
            access_token=access_token,
            params={"symbols": symbols},
        )

    async def fetch_option_chain(
        self,
        *,
        app_id: str,
        access_token: str,
        symbol: str,
        strike_count: int = 20,
        timestamp: str = "",
    ) -> dict[str, Any]:
        return await self._get(
            self._endpoints.option_chain,
            app_id=app_id,
            access_token=access_token,
            params={"symbol": symbol, "strikecount": strike_count, "timestamp": timestamp},
        )

    # -- transport ----------------------------------------------------------

    async def _get(
        self,
        url: str,
        *,
        app_id: str,
        access_token: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = await self._http.get(
                url,
                params=params,
                headers={
                    "Authorization": authorization_header(app_id, access_token),
                    "Accept": "application/json",
                },
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise BrokerUnavailableError from exc
        return self._unwrap(response)

    async def _post(self, url: str, *, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._http.post(
                url,
                json=payload,
                headers={"Accept": "application/json"},
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise BrokerUnavailableError from exc
        return self._unwrap(response)

    def _unwrap(self, response: httpx.Response) -> dict[str, Any]:
        """Turn a FYERS envelope into a payload or a typed error.

        A 5xx becomes "unavailable" (worth retrying); a rejection inside a 200
        body becomes "rejected" (never worth retrying).
        """
        if response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
            raise BrokerUnavailableError

        try:
            payload: dict[str, Any] = response.json()
        except ValueError as exc:
            raise BrokerRejectedError("The broker returned an unreadable response.") from exc

        status = str(payload.get("s", "")).lower()
        if status == _OK_STATUS or payload.get("code") == _OK_CODE:
            return payload

        if response.status_code in (httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN):
            raise BrokerRejectedError("The broker rejected these credentials.")
        if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
            raise BrokerUnavailableError

        # The broker's own message is kept for logs but not shown verbatim:
        # error payloads have been observed to echo request parameters back.
        raise BrokerRejectedError(_safe_message(payload))


def _safe_message(payload: dict[str, Any]) -> str:
    message = str(payload.get("message") or "").strip()
    return message[:_MAX_MESSAGE_LENGTH] if message else "The broker rejected this request."
