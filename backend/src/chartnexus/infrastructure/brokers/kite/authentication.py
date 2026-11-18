"""Kite Connect login adapter.

Implements the ``BrokerOAuthClient`` port: build Zerodha's login URL, trade
the one-time ``request_token`` for an access token, prove the token works by
fetching the profile, and log a token out when the user disconnects.

The access token never leaves this layer except to be stored encrypted — it
is not logged, not returned to a caller, and not put in any error message.
It is also, unlike a FYERS data token, a **trading** credential: Kite issues
one token for everything an API key is entitled to. ChartNexus never calls an
order endpoint (ADR 0002), but that is why this adapter revokes on disconnect.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from chartnexus.contexts.broker_connections.application.ports import BrokerTokens
from chartnexus.contexts.broker_connections.domain.errors import BrokerRejectedError
from chartnexus.contexts.broker_connections.domain.value_objects import (
    BrokerCredentials,
    BrokerProfile,
)
from chartnexus.infrastructure.brokers.kite.rest_client import BROKER, KiteRestClient

IST = ZoneInfo("Asia/Kolkata")

#: Zerodha logs every access token out around 06:00 IST, every day.
DAILY_LOGOUT = time(6, 0)


def next_logout(moment: datetime) -> datetime:
    """The next 06:00 IST strictly after ``moment``, in UTC.

    A login at 05:59 IST is good for one minute; a login at 06:01 lasts until
    tomorrow morning. Known at login, so expiry is recognised without a
    network call (``BrokerConnection.has_lapsed``).
    """
    local = moment.astimezone(IST)
    candidate = datetime.combine(local.date(), DAILY_LOGOUT, tzinfo=IST)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate.astimezone(UTC)


class KiteOAuthClient:
    """Implements the ``BrokerOAuthClient`` port."""

    def __init__(self, rest: KiteRestClient, *, clock: Any = None) -> None:
        self._rest = rest
        self._now = clock.now if clock is not None else (lambda: datetime.now(UTC))

    def build_authorization_url(
        self,
        *,
        credentials: BrokerCredentials,
        state: str,
        redirect_uri: str,  # noqa: ARG002 — Kite uses the URL registered on the app
    ) -> str:
        return self._rest.build_login_url(api_key=credentials.app_id, state=state)

    async def exchange_code(
        self,
        *,
        credentials: BrokerCredentials,
        code: str,
        redirect_uri: str,  # noqa: ARG002 — Kite validates against the app registration
    ) -> BrokerTokens:
        payload = await self._rest.create_session(
            api_key=credentials.app_id,
            api_secret=credentials.secret,
            request_token=code,
        )
        data = payload.get("data")
        data = data if isinstance(data, dict) else {}

        access_token = str(data.get("access_token") or "")
        if not access_token:
            # A success envelope without a token means the request token was
            # already spent, or minted for a different app. Either way it needs
            # a fresh login.
            raise BrokerRejectedError("Zerodha did not return an access token.", broker=BROKER)

        # Kite issues a refresh token only to specially approved platforms; a
        # retail app gets none, and logs in again each morning. If one ever
        # arrives it is stored (encrypted) but nothing uses it yet.
        refresh_token = data.get("refresh_token")
        return BrokerTokens(
            access_token=access_token,
            refresh_token=str(refresh_token) if refresh_token else None,
            expires_at=next_logout(self._now()),
        )

    async def fetch_profile(
        self, *, credentials: BrokerCredentials, access_token: str
    ) -> BrokerProfile:
        payload = await self._rest.fetch_profile(
            api_key=credentials.app_id, access_token=access_token
        )
        return _to_profile(payload)

    async def revoke_token(self, *, credentials: BrokerCredentials, access_token: str) -> None:
        await self._rest.invalidate_session(api_key=credentials.app_id, access_token=access_token)


def _to_profile(payload: dict[str, Any]) -> BrokerProfile:
    """Only what "connected as …" needs.

    The profile also lists exchanges, products, order types, bank and DP
    details for some account types. None of that is retained.
    """
    data = payload.get("data")
    if not isinstance(data, dict):
        data = {}
    email = str(data.get("email") or "").strip()
    return BrokerProfile(
        broker_user_id=str(data.get("user_id") or "").strip().upper(),
        display_name=str(data.get("user_name") or data.get("user_shortname") or "").strip(),
        email=email or None,
    )
