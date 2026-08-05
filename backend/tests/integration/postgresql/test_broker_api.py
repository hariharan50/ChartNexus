"""Broker + market endpoints against real Postgres and Redis.

Covers what unit tests structurally cannot: that secrets reach the database as
ciphertext, that the OAuth state is genuinely single-use across requests, and
that one tenant cannot observe another's connection.

Requires the compose stack:  docker compose -f deploy/compose/compose.yml up -d
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine

from marketcompass.bootstrap.settings import Settings
from marketcompass.entrypoints.main_api import create_app

pytestmark = [pytest.mark.integration, pytest.mark.security]

BROKER = "/api/v1/broker/fyers"
MARKET = "/api/v1/market"
PASSWORD = "a-perfectly-fine-password"
APP_ID = "ABCDE123XY-100"
SECRET_ID = "the-plaintext-app-secret"

ASYNC_DSN = "postgresql+asyncpg://marketcompass:marketcompass@localhost:5433/marketcompass"


@pytest.fixture(scope="module")
def settings() -> Settings:
    return Settings(
        environment="local",
        database={
            "url": "postgresql+asyncpg://marketcompass:marketcompass@localhost:5433/marketcompass"
        },
        redis={"url": "redis://localhost:6381/0", "key_prefix": f"it-{uuid.uuid4().hex[:8]}"},
        auth={"jwt_signing_key": "integration-test-signing-key-long-enough"},
        security={"cookie_secure": False},
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _sign_up(client: TestClient) -> dict[str, str]:
    """Register a fresh tenant and return the CSRF header for it."""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"br-{uuid.uuid4().hex[:12]}@example.com",
            "password": PASSWORD,
            # Unique per call: `uq_users_phone` would otherwise reject the
            # second tenant these tests sign up.
            "phone": f"9{secrets.randbelow(1_000_000_000):09d}",
        },
    )
    assert response.status_code == 201, response.text
    return {"X-CSRF-Token": response.json()["tokens"]["csrf_token"]}


def _save_credentials(client: TestClient, headers: dict[str, str]) -> None:
    response = client.post(
        f"{BROKER}/credentials",
        json={"app_id": APP_ID, "secret_id": SECRET_ID},
        headers=headers,
    )
    assert response.status_code == 200, response.text


# --- authentication --------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", f"{BROKER}/status"),
        ("POST", f"{BROKER}/credentials"),
        ("POST", f"{BROKER}/connect"),
        ("POST", f"{BROKER}/callback"),
        ("DELETE", f"{BROKER}/connection"),
        ("GET", f"{MARKET}/status"),
        ("GET", f"{MARKET}/spot"),
        ("GET", f"{MARKET}/option-chain"),
    ],
)
def test_every_route_requires_authentication(client: TestClient, method: str, path: str) -> None:
    client.cookies.clear()
    response = client.request(method, path, json={})
    assert response.status_code == 401


# --- credentials -----------------------------------------------------------


async def test_secret_is_stored_as_ciphertext(client: TestClient) -> None:
    """The security property the whole feature rests on."""
    headers = _sign_up(client)
    _save_credentials(client, headers)

    # Read the raw row through the same async driver the app uses, rather than
    # adding a synchronous driver purely for one assertion.
    engine = create_async_engine(ASYNC_DSN)
    async with engine.connect() as connection:
        result = await connection.execute(
            sa.text(
                "select app_id, app_secret_enc from broker_connections "
                "where app_id = :app_id order by created_at desc limit 1"
            ),
            {"app_id": APP_ID},
        )
        row = result.one()
    await engine.dispose()

    assert row.app_secret_enc is not None
    assert SECRET_ID not in row.app_secret_enc
    # The AES-256-GCM envelope: scheme, key id, then nonce+ciphertext+tag.
    scheme, kid, body = row.app_secret_enc.split(".")
    assert scheme == "mcv1"
    assert kid and body


def test_the_secret_is_never_returned(client: TestClient) -> None:
    headers = _sign_up(client)
    _save_credentials(client, headers)

    for response in (
        client.post(
            f"{BROKER}/credentials",
            json={"app_id": APP_ID, "secret_id": SECRET_ID},
            headers=headers,
        ),
        client.get(f"{BROKER}/status"),
    ):
        assert SECRET_ID not in response.text
        # The app id is masked rather than echoed in full.
        assert APP_ID not in response.text


def test_a_malformed_app_id_is_rejected(client: TestClient) -> None:
    headers = _sign_up(client)
    response = client.post(
        f"{BROKER}/credentials",
        json={"app_id": "not-an-app-id", "secret_id": SECRET_ID},
        headers=headers,
    )
    assert response.status_code == 422


# --- OAuth state -----------------------------------------------------------


def test_connect_requires_credentials_first(client: TestClient) -> None:
    headers = _sign_up(client)
    response = client.post(f"{BROKER}/connect", json={}, headers=headers)

    assert response.status_code == 409
    assert response.json()["code"] == "broker_credentials_missing"


def test_connect_returns_a_broker_url_carrying_the_state(client: TestClient) -> None:
    headers = _sign_up(client)
    _save_credentials(client, headers)

    response = client.post(f"{BROKER}/connect", json={}, headers=headers)
    assert response.status_code == 200

    body = response.json()
    assert body["authorization_url"].startswith("https://api-t1.fyers.in/")
    assert f"state={body['state']}" in body["authorization_url"]
    assert f"client_id={APP_ID}" in body["authorization_url"]


def test_an_unknown_state_is_rejected(client: TestClient) -> None:
    headers = _sign_up(client)
    _save_credentials(client, headers)

    response = client.post(
        f"{BROKER}/callback",
        json={"auth_code": "whatever", "state": "never-issued"},
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "broker_state_invalid"


def test_a_state_cannot_be_replayed(client: TestClient) -> None:
    """Single use: the second attempt must fail even with a valid code."""
    headers = _sign_up(client)
    _save_credentials(client, headers)
    state = client.post(f"{BROKER}/connect", json={}, headers=headers).json()["state"]

    # The first attempt consumes the state. It then fails at the broker, which
    # is unreachable from the test — but the state is spent either way.
    first = client.post(
        f"{BROKER}/callback", json={"auth_code": "code", "state": state}, headers=headers
    )
    assert first.status_code in (422, 502, 503)

    second = client.post(
        f"{BROKER}/callback", json={"auth_code": "code", "state": state}, headers=headers
    )
    assert second.status_code == 422
    assert second.json()["code"] == "broker_state_invalid"


def test_another_tenant_cannot_use_a_state_it_did_not_create(client: TestClient) -> None:
    """The token binds to the tenant stored with the state, not the caller."""
    victim = _sign_up(client)
    _save_credentials(client, victim)
    state = client.post(f"{BROKER}/connect", json={}, headers=victim).json()["state"]

    client.cookies.clear()
    attacker = _sign_up(client)

    response = client.post(
        f"{BROKER}/callback", json={"auth_code": "code", "state": state}, headers=attacker
    )
    # The state resolves to the victim's tenant; the attacker's own connection
    # is untouched either way.
    assert response.status_code in (422, 502, 503)

    attacker_status = client.get(f"{BROKER}/status").json()
    assert attacker_status["configured"] is False
    assert attacker_status["connected"] is False


# --- lifecycle -------------------------------------------------------------


def test_disconnect_keeps_credentials_and_revoke_removes_them(client: TestClient) -> None:
    headers = _sign_up(client)
    _save_credentials(client, headers)

    after_disconnect = client.delete(f"{BROKER}/connection", headers=headers).json()
    assert after_disconnect["configured"] is True

    after_revoke = client.delete(f"{BROKER}/credentials", headers=headers).json()
    assert after_revoke["configured"] is False
    assert after_revoke["status"] == "revoked"


def test_connections_are_isolated_between_tenants(client: TestClient) -> None:
    first = _sign_up(client)
    _save_credentials(client, first)

    client.cookies.clear()
    _sign_up(client)

    status = client.get(f"{BROKER}/status").json()
    assert status["configured"] is False
    assert status["masked_app_id"] is None


# --- market data -----------------------------------------------------------


def test_market_data_falls_back_to_mock_and_says_so(client: TestClient) -> None:
    """Without a broker the app still works — but never claims to be live."""
    _sign_up(client)

    status = client.get(f"{MARKET}/status").json()
    assert status["connected"] is False
    assert status["source"] == "mock"

    spot = client.get(f"{MARKET}/spot", params={"instrument": "NIFTY"}).json()
    assert spot["provenance"]["source"] == "mock"
    assert spot["provenance"]["is_stale"] is True


def test_option_chain_returns_the_canonical_shape(client: TestClient) -> None:
    _sign_up(client)
    chain = client.get(f"{MARKET}/option-chain", params={"instrument": "NIFTY"}).json()

    assert chain["instrument"] == "NIFTY"
    assert chain["strikes"], "expected strikes"
    assert chain["atm_strike"] is not None
    assert chain["pcr"] is not None
    # The bug this guards: every contract collapsing onto strike zero.
    assert all(float(row["strike"]) > 0 for row in chain["strikes"])
    assert chain["provenance"]["source"] == "mock"


def test_an_unknown_instrument_is_rejected(client: TestClient) -> None:
    _sign_up(client)
    response = client.get(f"{MARKET}/spot", params={"instrument": "DOGECOIN"})

    assert response.status_code == 422
    assert response.json()["field"] == "instrument"
