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
from dataclasses import dataclass

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine

from chartnexus.bootstrap.settings import Settings
from chartnexus.entrypoints.main_api import create_app

pytestmark = [pytest.mark.integration, pytest.mark.security]

BROKERS_API = "/api/v1/broker"
MARKET = "/api/v1/market"
PASSWORD = "a-perfectly-fine-password"
APP_ID = "ABCDE123XY-100"
SECRET_ID = "the-plaintext-app-secret"


@dataclass(frozen=True)
class Broker:
    """What differs between the brokers, for tests that hold for both."""

    name: str
    app_id: str
    secret: str
    login_prefix: str
    key_param: str
    bad_app_id: str

    @property
    def base(self) -> str:
        return f"{BROKERS_API}/{self.name}"


FYERS = Broker(
    name="fyers",
    app_id=APP_ID,
    secret=SECRET_ID,
    login_prefix="https://api-t1.fyers.in/",
    key_param="client_id",
    bad_app_id="not-an-app-id",
)
KITE = Broker(
    name="kite",
    app_id="abc123xyz789",
    secret="kitesecret0123456789abcdef",
    login_prefix="https://kite.zerodha.com/connect/login?",
    key_param="api_key",
    bad_app_id="ABCDE123XY-100",
)


@pytest.fixture(params=[FYERS, KITE], ids=lambda broker: broker.name)
def broker(request: pytest.FixtureRequest) -> Broker:
    return request.param  # type: ignore[no-any-return]


ASYNC_DSN = "postgresql+asyncpg://chartnexus:chartnexus@localhost:5433/chartnexus"


@pytest.fixture(scope="module")
def settings() -> Settings:
    return Settings(
        environment="local",
        database={"url": "postgresql+asyncpg://chartnexus:chartnexus@localhost:5433/chartnexus"},
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


def _save_credentials(client: TestClient, headers: dict[str, str], broker: Broker = FYERS) -> None:
    response = client.post(
        f"{broker.base}/credentials",
        json={"app_id": broker.app_id, "secret_id": broker.secret},
        headers=headers,
    )
    assert response.status_code == 200, response.text


# --- authentication --------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", f"{BROKERS_API}/connections"),
        *(
            (method, f"{BROKERS_API}/{name}/{path}")
            for name in ("fyers", "kite")
            for method, path in (
                ("GET", "status"),
                ("POST", "credentials"),
                ("POST", "connect"),
                ("POST", "callback"),
                ("DELETE", "connection"),
            )
        ),
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


async def test_secret_is_stored_as_ciphertext(client: TestClient, broker: Broker) -> None:
    """The security property the whole feature rests on."""
    headers = _sign_up(client)
    _save_credentials(client, headers, broker)

    # Read the raw row through the same async driver the app uses, rather than
    # adding a synchronous driver purely for one assertion.
    engine = create_async_engine(ASYNC_DSN)
    async with engine.connect() as connection:
        result = await connection.execute(
            sa.text(
                "select app_id, app_secret_enc from broker_connections "
                "where app_id = :app_id and broker = :broker "
                "order by created_at desc limit 1"
            ),
            {"app_id": broker.app_id, "broker": broker.name},
        )
        row = result.one()
    await engine.dispose()

    assert row.app_secret_enc is not None
    assert broker.secret not in row.app_secret_enc
    # The AES-256-GCM envelope: scheme, key id, then nonce+ciphertext+tag.
    scheme, kid, body = row.app_secret_enc.split(".")
    assert scheme == "mcv1"
    assert kid and body


def test_the_secret_is_never_returned(client: TestClient, broker: Broker) -> None:
    headers = _sign_up(client)
    _save_credentials(client, headers, broker)

    for response in (
        client.post(
            f"{broker.base}/credentials",
            json={"app_id": broker.app_id, "secret_id": broker.secret},
            headers=headers,
        ),
        client.get(f"{broker.base}/status"),
        client.get(f"{BROKERS_API}/connections"),
    ):
        assert broker.secret not in response.text
        # The app id is masked rather than echoed in full.
        assert broker.app_id not in response.text


def test_a_malformed_app_id_is_rejected(client: TestClient, broker: Broker) -> None:
    headers = _sign_up(client)
    response = client.post(
        f"{broker.base}/credentials",
        json={"app_id": broker.bad_app_id, "secret_id": broker.secret},
        headers=headers,
    )
    assert response.status_code == 422


# --- OAuth state -----------------------------------------------------------


def test_connect_requires_credentials_first(client: TestClient, broker: Broker) -> None:
    headers = _sign_up(client)
    response = client.post(f"{broker.base}/connect", json={}, headers=headers)

    assert response.status_code == 409
    assert response.json()["code"] == "broker_credentials_missing"


def test_connect_returns_a_broker_url_carrying_the_state(
    client: TestClient, broker: Broker
) -> None:
    headers = _sign_up(client)
    _save_credentials(client, headers, broker)

    response = client.post(f"{broker.base}/connect", json={}, headers=headers)
    assert response.status_code == 200

    body = response.json()
    url = body["authorization_url"]
    assert url.startswith(broker.login_prefix)
    assert f"{broker.key_param}={broker.app_id}" in url
    # Kite carries state inside redirect_params (ADR 0002); FYERS takes it plainly.
    expected_state = f"state%3D{body['state']}" if broker == KITE else f"state={body['state']}"
    assert expected_state in url


def test_an_unknown_state_is_rejected(client: TestClient, broker: Broker) -> None:
    headers = _sign_up(client)
    _save_credentials(client, headers, broker)

    response = client.post(
        f"{broker.base}/callback",
        json={"auth_code": "whatever", "state": "never-issued"},
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "broker_state_invalid"


def test_a_state_cannot_be_replayed(client: TestClient, broker: Broker) -> None:
    """Single use: the second attempt must fail even with a valid code."""
    headers = _sign_up(client)
    _save_credentials(client, headers, broker)
    state = client.post(f"{broker.base}/connect", json={}, headers=headers).json()["state"]

    # The first attempt consumes the state. It then fails at the broker, which
    # is unreachable from the test — but the state is spent either way.
    first = client.post(
        f"{broker.base}/callback", json={"auth_code": "code", "state": state}, headers=headers
    )
    assert first.status_code in (422, 502, 503)

    second = client.post(
        f"{broker.base}/callback", json={"auth_code": "code", "state": state}, headers=headers
    )
    assert second.status_code == 422
    assert second.json()["code"] == "broker_state_invalid"


def test_another_tenant_cannot_use_a_state_it_did_not_create(
    client: TestClient, broker: Broker
) -> None:
    """The token binds to the tenant stored with the state, not the caller."""
    victim = _sign_up(client)
    _save_credentials(client, victim, broker)
    state = client.post(f"{broker.base}/connect", json={}, headers=victim).json()["state"]

    client.cookies.clear()
    attacker = _sign_up(client)

    response = client.post(
        f"{broker.base}/callback", json={"auth_code": "code", "state": state}, headers=attacker
    )
    # The state resolves to the victim's tenant; the attacker's own connection
    # is untouched either way.
    assert response.status_code in (422, 502, 503)

    attacker_status = client.get(f"{broker.base}/status").json()
    assert attacker_status["configured"] is False
    assert attacker_status["connected"] is False


# --- lifecycle -------------------------------------------------------------


def test_disconnect_keeps_credentials_and_revoke_removes_them(
    client: TestClient, broker: Broker
) -> None:
    headers = _sign_up(client)
    _save_credentials(client, headers, broker)

    after_disconnect = client.delete(f"{broker.base}/connection", headers=headers).json()
    assert after_disconnect["configured"] is True

    after_revoke = client.delete(f"{broker.base}/credentials", headers=headers).json()
    assert after_revoke["configured"] is False
    assert after_revoke["status"] == "revoked"


def test_connections_are_isolated_between_tenants(client: TestClient, broker: Broker) -> None:
    first = _sign_up(client)
    _save_credentials(client, first, broker)

    client.cookies.clear()
    _sign_up(client)

    status = client.get(f"{broker.base}/status").json()
    assert status["configured"] is False
    assert status["masked_app_id"] is None


def test_an_unknown_broker_is_not_a_route(client: TestClient) -> None:
    _sign_up(client)
    assert client.get(f"{BROKERS_API}/upstox/status").status_code == 422


def test_connections_lists_both_brokers_and_none_active(client: TestClient) -> None:
    headers = _sign_up(client)
    _save_credentials(client, headers, KITE)

    body = client.get(f"{BROKERS_API}/connections").json()

    assert body["active_broker"] is None
    by_name = {row["broker"]: row for row in body["connections"]}
    assert set(by_name) == {"fyers", "kite"}
    assert by_name["kite"]["configured"] is True
    assert by_name["fyers"]["configured"] is False


def test_kite_and_fyers_credentials_coexist(client: TestClient) -> None:
    """One active broker per tenant, but both sets of keys can be saved."""
    headers = _sign_up(client)
    _save_credentials(client, headers, FYERS)
    _save_credentials(client, headers, KITE)

    assert client.get(f"{FYERS.base}/status").json()["configured"] is True
    assert client.get(f"{KITE.base}/status").json()["configured"] is True


async def test_the_database_allows_one_active_broker_per_tenant(client: TestClient) -> None:
    """The backstop under the use case: a second active row is refused."""
    headers = _sign_up(client)
    _save_credentials(client, headers, FYERS)
    _save_credentials(client, headers, KITE)

    engine = create_async_engine(ASYNC_DSN)
    try:
        async with engine.connect() as connection:
            tenant = (
                await connection.execute(
                    sa.text(
                        "select tenant_id from broker_connections "
                        "where app_id = :app_id order by created_at desc limit 1"
                    ),
                    {"app_id": KITE.app_id},
                )
            ).scalar_one()
            with pytest.raises(sa.exc.IntegrityError, match="uq_broker_connections_one_active"):
                async with connection.begin():
                    await connection.execute(
                        sa.text(
                            "update broker_connections set status = 'active' "
                            "where tenant_id = :tenant"
                        ),
                        {"tenant": tenant},
                    )
    finally:
        await engine.dispose()


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
