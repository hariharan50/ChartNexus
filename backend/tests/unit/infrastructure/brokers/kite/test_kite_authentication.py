"""Kite login: expiry at 06:00 IST, the profile we keep, and revoke."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from chartnexus.contexts.broker_connections.domain.errors import BrokerRejectedError
from chartnexus.contexts.broker_connections.domain.value_objects import (
    BrokerCredentials,
    BrokerName,
)
from chartnexus.infrastructure.brokers.kite.authentication import (
    IST,
    KiteOAuthClient,
    next_logout,
)

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[4] / "fixtures" / "kite"
CREDENTIALS = BrokerCredentials.parse("abc123xyz789", "s3cretvalue0123456789", BrokerName.KITE)


def _fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _ist(*args: int) -> datetime:
    return datetime(*args, tzinfo=IST)  # type: ignore[misc]


class TestNextLogout:
    def test_a_morning_login_lasts_until_tomorrow(self) -> None:
        assert next_logout(_ist(2026, 8, 3, 9, 10)) == _ist(2026, 8, 4, 6, 0).astimezone(UTC)

    def test_a_login_just_before_six_lasts_minutes(self) -> None:
        assert next_logout(_ist(2026, 8, 3, 5, 59)) == _ist(2026, 8, 3, 6, 0).astimezone(UTC)

    def test_exactly_six_is_already_the_next_day(self) -> None:
        assert next_logout(_ist(2026, 8, 3, 6, 0)) == _ist(2026, 8, 4, 6, 0).astimezone(UTC)

    def test_a_late_night_login_crosses_midnight(self) -> None:
        # 23:30 IST on the 3rd is 18:00 UTC on the 3rd; the logout is 06:00 IST
        # on the 4th, not on the 3rd as a UTC-date calculation would give.
        moment = _ist(2026, 8, 3, 23, 30).astimezone(UTC)
        assert next_logout(moment) == _ist(2026, 8, 4, 6, 0).astimezone(UTC)

    def test_a_utc_moment_after_ist_midnight(self) -> None:
        # 19:00 UTC = 00:30 IST next day; still before that day's 06:00.
        assert next_logout(datetime(2026, 8, 3, 19, 0, tzinfo=UTC)) == _ist(
            2026, 8, 4, 6, 0
        ).astimezone(UTC)

    def test_the_result_is_utc(self) -> None:
        assert next_logout(_ist(2026, 8, 3, 9, 0)).tzinfo is UTC


class FakeRest:
    def __init__(self, session: dict[str, Any] | None = None) -> None:
        self.session = session or _fixture("session.json")
        self.revoked: list[tuple[str, str]] = []

    def build_login_url(self, *, api_key: str, state: str) -> str:
        return f"login?{api_key}&{state}"

    async def create_session(self, **_: Any) -> dict[str, Any]:
        return self.session

    async def fetch_profile(self, **_: Any) -> dict[str, Any]:
        return _fixture("profile.json")

    async def invalidate_session(self, *, api_key: str, access_token: str) -> None:
        self.revoked.append((api_key, access_token))


class FixedClock:
    def now(self) -> datetime:
        return _ist(2026, 8, 3, 9, 10).astimezone(UTC)


class TestKiteOAuthClient:
    async def test_exchange_sets_the_morning_expiry(self) -> None:
        client = KiteOAuthClient(FakeRest(), clock=FixedClock())  # type: ignore[arg-type]
        tokens = await client.exchange_code(credentials=CREDENTIALS, code="rt", redirect_uri="x")

        assert tokens.access_token == "acc3ss-t0ken"
        assert tokens.refresh_token is None  # "" from Kite means none
        assert tokens.expires_at == _ist(2026, 8, 4, 6, 0).astimezone(UTC)

    async def test_a_success_without_a_token_is_refused(self) -> None:
        rest = FakeRest({"status": "success", "data": {"user_id": "AB1234"}})
        client = KiteOAuthClient(rest, clock=FixedClock())  # type: ignore[arg-type]
        with pytest.raises(BrokerRejectedError):
            await client.exchange_code(credentials=CREDENTIALS, code="rt", redirect_uri="x")

    async def test_the_profile_keeps_only_identity(self) -> None:
        client = KiteOAuthClient(FakeRest())  # type: ignore[arg-type]
        profile = await client.fetch_profile(credentials=CREDENTIALS, access_token="t")

        assert profile.broker_user_id == "AB1234"  # upper-cased for comparison
        assert profile.display_name == "Test Trader"
        assert profile.email == "trader@example.com"
        flat = json.dumps(profile.as_dict())
        assert "ABCDE1234F" not in flat
        assert "XXXX1234" not in flat

    async def test_revoke_logs_the_session_out(self) -> None:
        rest = FakeRest()
        client = KiteOAuthClient(rest)  # type: ignore[arg-type]
        await client.revoke_token(credentials=CREDENTIALS, access_token="tok")
        assert rest.revoked == [("abc123xyz789", "tok")]

    def test_the_login_url_uses_the_api_key(self) -> None:
        client = KiteOAuthClient(FakeRest())  # type: ignore[arg-type]
        url = client.build_authorization_url(credentials=CREDENTIALS, state="st", redirect_uri="x")
        assert url == "login?abc123xyz789&st"
