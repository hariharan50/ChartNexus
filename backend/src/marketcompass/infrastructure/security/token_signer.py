"""JWT access tokens.

Access tokens are stateless and therefore unrevocable before they expire, which
is why they are short-lived and carry ``sid``: any check that needs to be
authoritative (was this session revoked?) happens at refresh time, against the
database.

HS256 is the default because a single service both signs and verifies. RS256 is
supported for the day a second service needs to verify without holding the
signing key.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from jwt.exceptions import (
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidTokenError,
)

from marketcompass.bootstrap.settings import AuthSettings, SecuritySettings
from marketcompass.contexts.identity.application.ports import AccessToken, AccessTokenClaims
from marketcompass.contexts.identity.domain.errors import SessionExpiredError
from marketcompass.shared_kernel.domain.errors import AuthenticationError
from marketcompass.shared_kernel.types.identifiers import SessionId, TenantId, UserId

TOKEN_TYPE = "access"  # noqa: S105 — a claim value, not a credential

# RFC 7518 §3.2: an HMAC key shorter than the hash output weakens HS256.
_MIN_HS256_KEY_BYTES = 32


class JwtAccessTokenIssuer:
    """Implements the ``AccessTokenIssuer`` port."""

    def __init__(self, auth: AuthSettings, security: SecuritySettings) -> None:
        self._auth = auth
        self._algorithm = auth.jwt_algorithm
        signing_key = auth.jwt_signing_key.get_secret_value()
        # Local development should not need a second secret configured before
        # anything works; deployed environments are forced to set one in
        # Settings.assert_deployment_safe().
        self._signing_key = signing_key or security.secret_key.get_secret_value()
        self._verification_key = (
            auth.jwt_public_key.get_secret_value()
            if self._algorithm == "RS256"
            else self._signing_key
        )

        if self._algorithm == "HS256" and len(self._signing_key.encode()) < _MIN_HS256_KEY_BYTES:
            msg = (
                f"the JWT signing key must be at least {_MIN_HS256_KEY_BYTES} bytes for HS256; "
                'generate one with: python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
            raise ValueError(msg)

    def issue(
        self,
        *,
        user_id: UserId,
        tenant_id: TenantId,
        session_id: SessionId,
        roles: frozenset[str],
        email: str,
        now: datetime,
    ) -> AccessToken:
        expires_at = now + timedelta(seconds=self._auth.access_token_ttl_seconds)
        jti = uuid.uuid4().hex

        claims: dict[str, Any] = {
            "iss": self._auth.issuer,
            "aud": self._auth.audience,
            "sub": str(user_id),
            "jti": jti,
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "typ": TOKEN_TYPE,
            # Private claims. `sid` lets a revoked session be recognised, and
            # `tid` keeps every query tenant-scoped without a database lookup.
            "tid": str(tenant_id),
            "sid": str(session_id),
            "email": email,
            "roles": sorted(roles),
        }

        token = jwt.encode(
            claims,
            self._signing_key,
            algorithm=self._algorithm,
            headers={"kid": self._auth.jwt_key_id},
        )
        return AccessToken(
            value=token,
            expires_at=expires_at,
            expires_in_seconds=self._auth.access_token_ttl_seconds,
            jti=jti,
        )

    def decode(self, token: str) -> AccessTokenClaims:
        try:
            payload = jwt.decode(
                token,
                self._verification_key,
                # Pinning the algorithm list is what prevents the "alg: none"
                # and HS256-signed-with-the-RSA-public-key confusions.
                algorithms=[self._algorithm],
                audience=self._auth.audience,
                issuer=self._auth.issuer,
                options={
                    "require": ["exp", "iat", "nbf", "sub", "jti", "aud", "iss"],
                    "verify_exp": True,
                    "verify_aud": True,
                    "verify_iss": True,
                    "verify_signature": True,
                },
            )
        except ExpiredSignatureError as exc:
            raise SessionExpiredError("Your access token has expired.") from exc
        except (InvalidAudienceError, InvalidIssuerError) as exc:
            raise AuthenticationError("This token was not issued for this service.") from exc
        except InvalidTokenError as exc:
            raise AuthenticationError("This token is not valid.") from exc

        if payload.get("typ") != TOKEN_TYPE:
            # Refresh tokens are opaque, so this only fires if some other JWT
            # from this issuer is presented as an access token.
            raise AuthenticationError("This token cannot be used to authorise a request.")

        try:
            return AccessTokenClaims(
                subject=UserId(uuid.UUID(payload["sub"])),
                tenant_id=TenantId(uuid.UUID(payload["tid"])),
                session_id=SessionId(uuid.UUID(payload["sid"])),
                email=str(payload.get("email", "")),
                roles=frozenset(payload.get("roles", ())),
                issued_at=datetime.fromtimestamp(payload["iat"], tz=UTC),
                expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
                jti=str(payload["jti"]),
            )
        except (KeyError, ValueError) as exc:
            raise AuthenticationError("This token is missing required claims.") from exc
