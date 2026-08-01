"""The real Argon2 hasher, the password policy, and JWT verification.

These exercise the actual adapters rather than doubles — the properties being
checked (a hash reveals nothing, a tampered token is refused) are properties of
the libraries and their configuration, so a fake would prove nothing.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from marketcompass.bootstrap.settings import AuthSettings, SecuritySettings
from marketcompass.contexts.identity.domain.errors import SessionExpiredError
from marketcompass.contexts.identity.domain.password_policy import PasswordPolicy
from marketcompass.contexts.identity.domain.value_objects import EmailAddress, RawPassword
from marketcompass.infrastructure.security.password_hasher import Argon2Hasher
from marketcompass.infrastructure.security.token_signer import JwtAccessTokenIssuer
from marketcompass.shared_kernel.domain.errors import AuthenticationError, ValidationError
from marketcompass.shared_kernel.types.identifiers import SessionId, TenantId, UserId, new_id

pytestmark = pytest.mark.unit

PASSWORD = "a-perfectly-fine-password"


# --- Argon2 ----------------------------------------------------------------


@pytest.fixture(scope="module")
def argon2() -> Argon2Hasher:
    # Minimum cost: these tests check behaviour, not how slow the real
    # parameters are.
    return Argon2Hasher(
        SecuritySettings(argon2_time_cost=1, argon2_memory_cost_kib=8192, argon2_parallelism=1)
    )


def test_argon2_hash_verifies(argon2: Argon2Hasher) -> None:
    hashed = argon2.hash(PASSWORD)
    assert argon2.verify(PASSWORD, hashed)
    assert not argon2.verify(PASSWORD + "x", hashed)


def test_argon2_hash_reveals_nothing_about_the_password(argon2: Argon2Hasher) -> None:
    hashed = argon2.hash(PASSWORD)
    assert PASSWORD not in hashed
    assert hashed.startswith("$argon2id$")


def test_argon2_salts_every_hash(argon2: Argon2Hasher) -> None:
    """Identical passwords must not produce identical hashes."""
    assert argon2.hash(PASSWORD) != argon2.hash(PASSWORD)


def test_argon2_rejects_a_corrupt_hash_without_raising(argon2: Argon2Hasher) -> None:
    assert not argon2.verify(PASSWORD, "not-a-hash")


def test_argon2_flags_weaker_parameters_for_rehashing() -> None:
    weak = Argon2Hasher(
        SecuritySettings(argon2_time_cost=1, argon2_memory_cost_kib=8192, argon2_parallelism=1)
    )
    strong = Argon2Hasher(
        SecuritySettings(argon2_time_cost=3, argon2_memory_cost_kib=16384, argon2_parallelism=1)
    )
    assert strong.needs_rehash(weak.hash(PASSWORD))
    assert not strong.needs_rehash(strong.hash(PASSWORD))


def test_dummy_verify_does_not_raise(argon2: Argon2Hasher) -> None:
    argon2.dummy_verify()


# --- password policy -------------------------------------------------------


@pytest.mark.parametrize(
    "password",
    [
        "short",
        "password123",  # in the common list
        "aaaaaaaaaaaaaaaa",  # repeated characters
        "trader@example.com-x",  # contains the email address
        "traderXYZ123456",  # contains the local part
    ],
)
def test_policy_rejects_weak_passwords(password: str) -> None:
    with pytest.raises(ValidationError):
        PasswordPolicy().validate(RawPassword(password), email=EmailAddress("trader@example.com"))


@pytest.mark.parametrize(
    "password",
    ["a-perfectly-fine-password", "correct horse battery staple", "Nifty-Gamma-2026!"],
)
def test_policy_accepts_reasonable_passwords(password: str) -> None:
    PasswordPolicy().validate(RawPassword(password), email=EmailAddress("trader@example.com"))


def test_raw_password_never_leaks_through_repr() -> None:
    password = RawPassword(PASSWORD)
    assert PASSWORD not in repr(password)
    assert PASSWORD not in str(password)


def test_oversized_password_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RawPassword("x" * 2000)


# --- JWT -------------------------------------------------------------------


@pytest.fixture
def auth() -> AuthSettings:
    return AuthSettings(jwt_signing_key="unit-test-signing-key-long-enough-for-hs256")


@pytest.fixture
def issuer(auth: AuthSettings) -> JwtAccessTokenIssuer:
    return JwtAccessTokenIssuer(auth, SecuritySettings())


def _issue(issuer: JwtAccessTokenIssuer, *, now: datetime | None = None) -> str:
    return issuer.issue(
        user_id=UserId(new_id()),
        tenant_id=TenantId(new_id()),
        session_id=SessionId(new_id()),
        roles=frozenset({"owner"}),
        email="trader@example.com",
        now=now or datetime.now(UTC),
    ).value


def test_round_trip_preserves_the_claims(issuer: JwtAccessTokenIssuer) -> None:
    user_id, tenant_id, session_id = UserId(new_id()), TenantId(new_id()), SessionId(new_id())
    token = issuer.issue(
        user_id=user_id,
        tenant_id=tenant_id,
        session_id=session_id,
        roles=frozenset({"owner", "analyst"}),
        email="trader@example.com",
        now=datetime.now(UTC),
    )
    claims = issuer.decode(token.value)

    assert claims.subject == user_id
    assert claims.tenant_id == tenant_id
    assert claims.session_id == session_id
    assert claims.roles == frozenset({"owner", "analyst"})


def test_short_hs256_key_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="at least 32 bytes"):
        JwtAccessTokenIssuer(AuthSettings(jwt_signing_key="too-short"), SecuritySettings())


def test_tampered_payload_is_rejected(issuer: JwtAccessTokenIssuer) -> None:
    """Re-encoding the payload without re-signing must not pass."""
    header, payload, signature = _issue(issuer).split(".")
    claims = json.loads(_b64decode(payload))
    claims["roles"] = ["owner", "admin"]
    forged = _b64encode(json.dumps(claims).encode())

    with pytest.raises(AuthenticationError):
        issuer.decode(f"{header}.{forged}.{signature}")


def test_token_signed_with_another_key_is_rejected(auth: AuthSettings) -> None:
    other = JwtAccessTokenIssuer(
        AuthSettings(jwt_signing_key="a-completely-different-signing-key-value"),
        SecuritySettings(),
    )
    ours = JwtAccessTokenIssuer(auth, SecuritySettings())

    with pytest.raises(AuthenticationError):
        ours.decode(_issue(other))


def test_alg_none_token_is_rejected(issuer: JwtAccessTokenIssuer) -> None:
    """The classic JWT bypass: strip the signature and claim no algorithm."""
    unsigned = jwt.encode(
        {
            "iss": "marketcompass",
            "aud": "marketcompass-api",
            "sub": str(new_id()),
            "tid": str(new_id()),
            "sid": str(new_id()),
            "jti": "forged",
            "iat": int(datetime.now(UTC).timestamp()),
            "nbf": int(datetime.now(UTC).timestamp()),
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            "typ": "access",
            "roles": ["owner"],
        },
        key="",
        algorithm="none",
    )
    with pytest.raises(AuthenticationError):
        issuer.decode(unsigned)


def test_expired_token_is_rejected(issuer: JwtAccessTokenIssuer) -> None:
    token = _issue(issuer, now=datetime.now(UTC) - timedelta(hours=2))
    with pytest.raises(SessionExpiredError):
        issuer.decode(token)


def test_token_for_another_audience_is_rejected(issuer: JwtAccessTokenIssuer) -> None:
    foreign = JwtAccessTokenIssuer(
        AuthSettings(
            jwt_signing_key="unit-test-signing-key-long-enough-for-hs256",
            audience="some-other-service",
        ),
        SecuritySettings(),
    )
    with pytest.raises(AuthenticationError):
        issuer.decode(_issue(foreign))


def test_garbage_is_rejected(issuer: JwtAccessTokenIssuer) -> None:
    for value in ("", "not-a-token", "a.b.c"):
        with pytest.raises(AuthenticationError):
            issuer.decode(value)


def _b64decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
