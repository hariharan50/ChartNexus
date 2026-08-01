"""The auth endpoints against real Postgres and Redis.

The unit suite covers the rules; this covers the wiring — cookies, CSRF, the
session limit, and that a rotation really is durable across requests.

Requires the compose stack:  docker compose -f deploy/compose/compose.yml up -d
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from marketcompass.bootstrap.settings import Settings
from marketcompass.entrypoints.main_api import create_app

pytestmark = [pytest.mark.integration, pytest.mark.security]

AUTH = "/api/v1/auth"
PASSWORD = "a-perfectly-fine-password"


@pytest.fixture(scope="module")
def settings() -> Settings:
    # The autouse isolation fixture strips MC_* and moves the working directory,
    # so the connection details are stated here rather than read from .env.
    return Settings(
        environment="local",
        database={
            "url": "postgresql+asyncpg://marketcompass:marketcompass@localhost:5433/marketcompass"
        },
        redis={"url": "redis://localhost:6381/0", "key_prefix": f"test-{uuid.uuid4().hex[:8]}"},
        auth={
            "jwt_signing_key": "integration-test-signing-key-long-enough",
            "max_active_sessions_per_user": 3,
            "refresh_reuse_grace_seconds": 0,
        },
        security={"cookie_secure": False},
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _email() -> str:
    return f"it-{uuid.uuid4().hex[:12]}@example.com"


def _register(client: TestClient, email: str | None = None) -> dict:
    response = client.post(
        f"{AUTH}/register",
        json={"email": email or _email(), "password": PASSWORD, "display_name": "Integration"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_register_sets_all_three_cookies(client: TestClient) -> None:
    _register(client)

    assert set(client.cookies.keys()) >= {"mc_at", "mc_rt", "mc_csrf"}


def test_refresh_cookie_is_scoped_to_the_auth_path(client: TestClient) -> None:
    """It must not ride along on every API call."""
    response = client.post(f"{AUTH}/register", json={"email": _email(), "password": PASSWORD})
    refresh_cookie = next(value for name, value in response.cookies.items() if name == "mc_rt")
    assert refresh_cookie
    set_cookie_headers = response.headers.get_list("set-cookie")
    refresh_header = next(header for header in set_cookie_headers if header.startswith("mc_rt="))
    assert "Path=/api/v1/auth" in refresh_header
    assert "HttpOnly" in refresh_header


def test_access_and_refresh_cookies_are_httponly_but_csrf_is_readable(
    client: TestClient,
) -> None:
    response = client.post(f"{AUTH}/register", json={"email": _email(), "password": PASSWORD})
    headers = {
        header.split("=", 1)[0]: header for header in response.headers.get_list("set-cookie")
    }

    assert "HttpOnly" in headers["mc_at"]
    assert "HttpOnly" in headers["mc_rt"]
    # The client has to copy this one into a header, so it cannot be httpOnly.
    assert "HttpOnly" not in headers["mc_csrf"]


def test_full_password_lifecycle(client: TestClient) -> None:
    email = _email()
    _register(client, email)
    client.cookies.clear()

    login = client.post(f"{AUTH}/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200
    tokens = login.json()["tokens"]

    me = client.get(f"{AUTH}/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == email

    logout = client.post(
        f"{AUTH}/logout",
        json={},
        headers={"X-CSRF-Token": tokens["csrf_token"]},
    )
    assert logout.status_code == 200

    # The refresh token is dead after logout.
    assert (
        client.post(f"{AUTH}/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code
        == 401
    )


def test_rotation_and_reuse_detection_across_requests(client: TestClient) -> None:
    """The security property this whole design exists for, end to end."""
    registered = _register(client)
    original_refresh = registered["tokens"]["refresh_token"]

    rotated = client.post(f"{AUTH}/refresh", json={"refresh_token": original_refresh})
    assert rotated.status_code == 200
    new_refresh = rotated.json()["tokens"]["refresh_token"]
    assert new_refresh != original_refresh

    # Replaying the original (grace window is 0 in these settings) must revoke
    # the family, not merely fail.
    replay = client.post(f"{AUTH}/refresh", json={"refresh_token": original_refresh})
    assert replay.status_code == 401
    assert replay.json()["code"] == "session_revoked"

    # The legitimate client's newer token died with the family.
    assert client.post(f"{AUTH}/refresh", json={"refresh_token": new_refresh}).status_code == 401


def test_cookie_authenticated_write_requires_the_csrf_header(client: TestClient) -> None:
    registered = _register(client)
    csrf = registered["tokens"]["csrf_token"]

    assert client.post(f"{AUTH}/logout-all", json={}).status_code == 403
    assert (
        client.post(f"{AUTH}/logout-all", json={}, headers={"X-CSRF-Token": "wrong"}).status_code
        == 403
    )
    assert (
        client.post(f"{AUTH}/logout-all", json={}, headers={"X-CSRF-Token": csrf}).status_code
        == 200
    )


def test_bearer_clients_are_exempt_from_csrf(client: TestClient) -> None:
    """A Bearer caller carries no ambient authority for a third party to ride."""
    registered = _register(client)
    access = registered["tokens"]["access_token"]
    client.cookies.clear()

    response = client.post(
        f"{AUTH}/logout-all", json={}, headers={"Authorization": f"Bearer {access}"}
    )
    assert response.status_code == 200


def test_session_limit_is_enforced_in_the_database(client: TestClient) -> None:
    email = _email()
    registered = _register(client, email)

    for _ in range(4):
        assert (
            client.post(f"{AUTH}/login", json={"email": email, "password": PASSWORD}).status_code
            == 200
        )

    sessions = client.get(
        f"{AUTH}/sessions",
        headers={"Authorization": f"Bearer {registered['tokens']['access_token']}"},
    )
    assert sessions.status_code == 200
    assert len(sessions.json()) <= 3


def test_duplicate_email_is_rejected_by_the_unique_index(client: TestClient) -> None:
    email = _email()
    _register(client, email)

    duplicate = client.post(f"{AUTH}/register", json={"email": email.upper(), "password": PASSWORD})
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "email_taken"


def test_logout_all_revokes_every_session(client: TestClient) -> None:
    email = _email()
    registered = _register(client, email)
    second = client.post(f"{AUTH}/login", json={"email": email, "password": PASSWORD}).json()

    client.post(
        f"{AUTH}/logout-all",
        json={},
        headers={"Authorization": f"Bearer {registered['tokens']['access_token']}"},
    )

    for tokens in (registered["tokens"], second["tokens"]):
        assert (
            client.post(
                f"{AUTH}/refresh", json={"refresh_token": tokens["refresh_token"]}
            ).status_code
            == 401
        )


def test_protected_route_rejects_a_missing_or_bad_token(client: TestClient) -> None:
    client.cookies.clear()
    assert client.get(f"{AUTH}/me").status_code == 401
    assert client.get(f"{AUTH}/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401
    assert client.get(f"{AUTH}/me", headers={"Authorization": "Basic abc"}).status_code == 401
