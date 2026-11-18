"""The Kite Connect v3 HTTP contract.

**Every Kite URL, header, form field and envelope shape in this application
lives here.** Nothing else knows how Zerodha spells anything — the same rule
``fyers/rest_client.py`` follows, for the same reason: this is the part most
likely to change, and it should be the only casualty when it does.

Kite Connect is plain HTTPS, so this uses httpx rather than the
``kiteconnect`` SDK (ADR 0002). The SDK is synchronous, and its ticker runs a
Twisted reactor on its own thread — every problem ``fyers/data_socket.py``
already has to work around, for no gain.

**Read-only by construction.** There is deliberately no method here for any
order, portfolio, margin, GTT or mutual-fund endpoint, and
``tests/architecture/test_kite_read_only.py`` fails the build if one appears.

Response convention: ``{"status": "success", "data": ...}`` or
``{"status": "error", "message": ..., "error_type": ...}``. ``error_type`` is
the thing to switch on; the HTTP status is a secondary signal.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

import httpx

from chartnexus.contexts.broker_connections.domain.errors import (
    BrokerRejectedError,
    BrokerUnavailableError,
)

BROKER = "kite"

DEFAULT_API_BASE = "https://api.kite.trade"
DEFAULT_LOGIN_URL = "https://kite.zerodha.com/connect/login"

KITE_VERSION = "3"

#: Kite's own cap on instruments per ``/quote`` request.
QUOTE_BATCH_LIMIT = 500

_MAX_MESSAGE_LENGTH = 200

# error_type values (from Kite's docs). Anything not listed is treated as a
# rejection: a decision by Zerodha, not a hiccup worth retrying.
_TRANSIENT_ERRORS = frozenset({"NetworkException"})
_AUTH_ERRORS = frozenset({"TokenException", "PermissionException"})


@dataclass(frozen=True, slots=True)
class KiteEndpoints:
    """Endpoint layout, overridable so a path change needs no code edit."""

    api_base: str = DEFAULT_API_BASE
    login_url: str = DEFAULT_LOGIN_URL

    @property
    def session_token(self) -> str:
        return f"{self.api_base}/session/token"

    @property
    def profile(self) -> str:
        return f"{self.api_base}/user/profile"

    @property
    def quote(self) -> str:
        return f"{self.api_base}/quote"

    @property
    def instruments(self) -> str:
        return f"{self.api_base}/instruments"

    def historical(self, instrument_token: int, interval: str) -> str:
        return f"{self.api_base}/instruments/historical/{instrument_token}/{interval}"


def checksum(api_key: str, request_token: str, api_secret: str) -> str:
    """SHA-256 of ``api_key + request_token + api_secret``, as lower-case hex.

    Plain concatenation — **no separator**, unlike FYERS' ``app_id:secret``.
    It proves possession of the secret without sending it, and unlike the
    FYERS hash it includes the one-time request token, so a captured checksum
    is useless once that login has been exchanged.
    """
    return hashlib.sha256(f"{api_key}{request_token}{api_secret}".encode()).hexdigest()


def authorization_header(api_key: str, access_token: str) -> str:
    """Kite's request authentication: ``token <api_key>:<access_token>``."""
    return f"token {api_key}:{access_token}"


def batch_instruments(instruments: Sequence[str], size: int = QUOTE_BATCH_LIMIT) -> list[list[str]]:
    """Split ``EXCHANGE:SYMBOL`` strings into request-sized chunks, deduplicated."""
    if size < 1:
        raise ValueError("batch size must be at least 1")
    unique = list(dict.fromkeys(instruments))
    return [unique[index : index + size] for index in range(0, len(unique), size)]


class KiteRestClient:
    """Thin transport. Understands Kite's envelope, nothing about our domain."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        endpoints: KiteEndpoints | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._http = http
        self._endpoints = endpoints or KiteEndpoints()
        self._timeout = timeout_seconds

    @property
    def endpoints(self) -> KiteEndpoints:
        return self._endpoints

    # -- login ----------------------------------------------------------------

    def build_login_url(self, *, api_key: str, state: str) -> str:
        """Zerodha's login page, carrying our state through ``redirect_params``.

        Kite returns to the redirect URL registered on the app and ignores any
        query parameter we add — except ``redirect_params``, whose decoded
        contents it appends to that URL unchanged. So ``state`` rides there and
        comes back as an ordinary ``?state=`` parameter.
        """
        query = urlencode(
            {"v": KITE_VERSION, "api_key": api_key, "redirect_params": urlencode({"state": state})}
        )
        return f"{self._endpoints.login_url}?{query}"

    async def create_session(
        self, *, api_key: str, api_secret: str, request_token: str
    ) -> dict[str, Any]:
        return await self._send(
            "POST",
            self._endpoints.session_token,
            data={
                "api_key": api_key,
                "request_token": request_token,
                "checksum": checksum(api_key, request_token, api_secret),
            },
        )

    async def invalidate_session(self, *, api_key: str, access_token: str) -> None:
        """Log the token out at Zerodha, so a copy held anywhere stops working."""
        await self._send(
            "DELETE",
            self._endpoints.session_token,
            params={"api_key": api_key, "access_token": access_token},
            auth=(api_key, access_token),
        )

    async def fetch_profile(self, *, api_key: str, access_token: str) -> dict[str, Any]:
        return await self._send("GET", self._endpoints.profile, auth=(api_key, access_token))

    # -- market data ----------------------------------------------------------

    async def fetch_quotes(
        self, *, api_key: str, access_token: str, instruments: Sequence[str]
    ) -> dict[str, Any]:
        """Full quotes — LTP, OHLC, volume, OI, depth — keyed ``EXCHANGE:SYMBOL``.

        At most :data:`QUOTE_BATCH_LIMIT` per call; this method does not chunk.
        Instruments Zerodha does not recognise are simply absent from the
        response rather than failing it.
        """
        if len(instruments) > QUOTE_BATCH_LIMIT:
            msg = f"at most {QUOTE_BATCH_LIMIT} instruments per quote request"
            raise ValueError(msg)
        payload = await self._send(
            "GET",
            self._endpoints.quote,
            params=[("i", instrument) for instrument in instruments],
            auth=(api_key, access_token),
        )
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    async def fetch_historical(
        self,
        *,
        api_key: str,
        access_token: str,
        instrument_token: int,
        interval: str,
        start: datetime,
        end: datetime,
        continuous: bool = False,
        oi: bool = False,
    ) -> list[list[Any]]:
        """Candles ``[timestamp, open, high, low, close, volume(, oi)]``, oldest first."""
        payload = await self._send(
            "GET",
            self._endpoints.historical(instrument_token, interval),
            params={
                "from": start.strftime("%Y-%m-%d %H:%M:%S"),
                "to": end.strftime("%Y-%m-%d %H:%M:%S"),
                "continuous": int(continuous),
                "oi": int(oi),
            },
            auth=(api_key, access_token),
        )
        data = payload.get("data")
        candles = data.get("candles") if isinstance(data, dict) else None
        return candles if isinstance(candles, list) else []

    async def fetch_instruments_csv(self, *, api_key: str, access_token: str) -> str:
        """The full instrument dump as CSV text (served gzip; httpx inflates it)."""
        try:
            response = await self._http.get(
                self._endpoints.instruments,
                headers=self._headers((api_key, access_token)),
                # The dump is tens of megabytes; give it far longer than a quote.
                timeout=max(self._timeout, 60.0),
            )
        except httpx.HTTPError as exc:
            raise BrokerUnavailableError(BROKER) from exc
        if response.status_code >= httpx.codes.BAD_REQUEST:
            # An error here comes back as the usual JSON envelope.
            self._unwrap(response)
            raise BrokerRejectedError("The instrument list could not be downloaded.", broker=BROKER)
        return response.text

    # -- transport ------------------------------------------------------------

    def _headers(self, auth: tuple[str, str] | None) -> dict[str, str]:
        headers = {"X-Kite-Version": KITE_VERSION, "Accept": "application/json"}
        if auth is not None:
            headers["Authorization"] = authorization_header(*auth)
        return headers

    async def _send(
        self,
        method: str,
        url: str,
        *,
        params: Any = None,
        data: dict[str, Any] | None = None,
        auth: tuple[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            response = await self._http.request(
                method,
                url,
                params=params,
                data=data,
                headers=self._headers(auth),
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise BrokerUnavailableError(BROKER) from exc
        return self._unwrap(response)

    def _unwrap(self, response: httpx.Response) -> dict[str, Any]:
        """Turn a Kite envelope into a payload or a typed error.

        * transient (timeout, 5xx, 429, ``NetworkException``) →
          ``BrokerUnavailableError`` — retried, and counts toward the breaker;
        * everything else → ``BrokerRejectedError`` — never retried. A
          ``TokenException`` in particular means the session is over, and
          hammering the endpoint is how an API key gets blocked.
        """
        if response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
            raise BrokerUnavailableError(BROKER)
        if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
            raise BrokerUnavailableError(BROKER)

        try:
            payload: dict[str, Any] = response.json()
        except ValueError as exc:
            raise BrokerRejectedError(
                "The broker returned an unreadable response.", broker=BROKER
            ) from exc
        if not isinstance(payload, dict):
            raise BrokerRejectedError("The broker returned an unreadable response.", broker=BROKER)

        if payload.get("status") == "success" and response.is_success:
            return payload

        error_type = str(payload.get("error_type") or "")
        if error_type in _TRANSIENT_ERRORS:
            raise BrokerUnavailableError(BROKER)
        if error_type in _AUTH_ERRORS or response.status_code == httpx.codes.FORBIDDEN:
            raise BrokerRejectedError("Zerodha rejected this session.", broker=BROKER)
        raise BrokerRejectedError(_safe_message(payload), broker=BROKER)


def _safe_message(payload: dict[str, Any]) -> str:
    """The broker's message, truncated. Kept for logs and ``last_error``."""
    message = str(payload.get("message") or "").strip()
    return message[:_MAX_MESSAGE_LENGTH] if message else "Zerodha rejected this request."
