"""Websocket ticket signing and verification.

The security properties worth a test are the ones that stop a ticket being
something it should not be: usable twice over (covered in the authenticator's
tests), usable against the REST API, usable after it expires, or forgeable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from chartnexus.bootstrap.settings import AuthSettings, SecuritySettings
from chartnexus.infrastructure.security.token_signer import JwtAccessTokenIssuer
from chartnexus.infrastructure.security.websocket_tickets import (
    TICKET_AUDIENCE,
    JwtWebsocketTicketIssuer,
    TicketExpiredError,
    TicketInvalidError,
)
from chartnexus.shared_kernel.domain.errors import AuthenticationError
from chartnexus.shared_kernel.types.identifiers import SessionId, TenantId, UserId

# Anchored on real time, not a frozen instant: `verify` checks `exp` against the
# wall clock (pyjwt has no injectable clock), so a ticket minted at a fixed past
# timestamp is already expired by the time it is verified. Tests that assert
# expiry *arithmetic* pass an explicit instant and never call verify.
FIXED = datetime(2026, 10, 9, 8, 30, tzinfo=UTC)
USER = UserId(uuid.uuid4())
TENANT = TenantId(uuid.uuid4())
SESSION = SessionId(uuid.uuid4())

# Long enough to satisfy the HS256 minimum the access-token issuer enforces.
SECRET = "test-only-secret-key-of-sufficient-length-for-hs256"


@pytest.fixture
def auth() -> AuthSettings:
    return AuthSettings()


@pytest.fixture
def security() -> SecuritySettings:
    return SecuritySettings(secret_key=SECRET)


@pytest.fixture
def issuer(auth: AuthSettings, security: SecuritySettings) -> JwtWebsocketTicketIssuer:
    return JwtWebsocketTicketIssuer(auth, security)


def _now() -> datetime:
    return datetime.now(UTC)


def _issue(issuer: JwtWebsocketTicketIssuer, *, now: datetime | None = None) -> str:
    return issuer.issue(user_id=USER, tenant_id=TENANT, session_id=SESSION, now=now or _now()).value


def _claims(**overrides: object) -> dict[str, object]:
    """A structurally valid ticket body, minus whatever the caller drops."""
    now = _now()
    body: dict[str, object] = {
        "iss": "chartnexus",
        "aud": TICKET_AUDIENCE,
        "sub": str(USER),
        "tid": str(TENANT),
        "sid": str(SESSION),
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "typ": "ws-ticket",
    }
    body.update(overrides)
    return {key: value for key, value in body.items() if value is not None}


class TestIssuing:
    def test_round_trips_the_identity_it_asserts(self, issuer: JwtWebsocketTicketIssuer) -> None:
        claims = issuer.verify(_issue(issuer))

        assert claims.user_id == USER
        assert claims.tenant_id == TENANT
        assert claims.session_id == SESSION

    def test_expiry_follows_the_configured_ttl(self, auth: AuthSettings) -> None:
        issuer = JwtWebsocketTicketIssuer(
            auth, SecuritySettings(secret_key=SECRET, websocket_ticket_ttl_seconds=30)
        )

        ticket = issuer.issue(user_id=USER, tenant_id=TENANT, session_id=SESSION, now=FIXED)

        assert ticket.expires_in_seconds == 30
        assert ticket.expires_at == FIXED + timedelta(seconds=30)

    def test_every_ticket_has_its_own_id(self, issuer: JwtWebsocketTicketIssuer) -> None:
        """The jti is what single-use enforcement keys on, so it cannot repeat."""
        first = issuer.verify(_issue(issuer))
        second = issuer.verify(_issue(issuer))

        assert first.jti != second.jti

    def test_carries_no_roles(self, issuer: JwtWebsocketTicketIssuer) -> None:
        """A credential that travels in a URL asserts the minimum."""
        payload = jwt.decode(
            _issue(issuer),
            SECRET,
            algorithms=["HS256"],
            audience=TICKET_AUDIENCE,
            issuer="chartnexus",
        )

        assert "roles" not in payload
        assert "email" not in payload


class TestVerification:
    def test_refuses_an_expired_ticket_distinguishably(
        self, issuer: JwtWebsocketTicketIssuer, security: SecuritySettings
    ) -> None:
        """Expired is its own error: the client's fix is a new ticket, not a login."""
        stale = _issue(
            issuer,
            now=_now() - timedelta(seconds=security.websocket_ticket_ttl_seconds + 60),
        )

        with pytest.raises(TicketExpiredError):
            issuer.verify(stale)

    def test_refuses_a_ticket_signed_with_another_key(self, auth: AuthSettings) -> None:
        forged = JwtWebsocketTicketIssuer(
            auth, SecuritySettings(secret_key="a-completely-different-secret-key-value")
        )
        verifier = JwtWebsocketTicketIssuer(auth, SecuritySettings(secret_key=SECRET))

        with pytest.raises(TicketInvalidError):
            verifier.verify(_issue(forged))

    def test_refuses_garbage(self, issuer: JwtWebsocketTicketIssuer) -> None:
        with pytest.raises(TicketInvalidError):
            issuer.verify("not.a.jwt")

    def test_refuses_an_unsigned_token(self, issuer: JwtWebsocketTicketIssuer) -> None:
        """The 'alg: none' bypass, which pinning the algorithm list prevents."""
        unsigned = jwt.encode(_claims(), key="", algorithm="none")

        with pytest.raises(TicketInvalidError):
            issuer.verify(unsigned)

    def test_refuses_a_ticket_missing_its_tenant(self, issuer: JwtWebsocketTicketIssuer) -> None:
        incomplete = jwt.encode(_claims(tid=None), SECRET, algorithm="HS256")

        with pytest.raises(TicketInvalidError):
            issuer.verify(incomplete)


class TestCredentialIsolation:
    """A ticket and an access token must not be usable in each other's place."""

    def test_an_access_token_cannot_open_a_socket(
        self, auth: AuthSettings, security: SecuritySettings, issuer: JwtWebsocketTicketIssuer
    ) -> None:
        access = JwtAccessTokenIssuer(auth, security).issue(
            user_id=USER,
            tenant_id=TENANT,
            session_id=SESSION,
            roles=frozenset({"owner"}),
            email="trader@example.com",
            now=_now(),
        )

        with pytest.raises(TicketInvalidError):
            issuer.verify(access.value)

    def test_a_ticket_cannot_authorise_a_rest_request(
        self, auth: AuthSettings, security: SecuritySettings, issuer: JwtWebsocketTicketIssuer
    ) -> None:
        """The whole point of a separate audience: a leaked ticket is socket-only."""
        with pytest.raises(AuthenticationError):
            JwtAccessTokenIssuer(auth, security).decode(_issue(issuer))
