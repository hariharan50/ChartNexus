"""Websocket tickets: sign and verify.

Implements the ``TicketIssuer`` port for ``realtime_delivery``. A ticket is a
JWT, for the same reason access tokens are — one dependency, one well-reviewed
verification path — but it is deliberately *not* interchangeable with one:

* its audience is its own (``chartnexus-ws``), so the API rejects a ticket and
  the socket rejects an access token. Neither can be used where the other
  belongs, even though both are signed by the same key;
* ``typ`` is pinned to ``ws-ticket``, a second independent check on the same
  confusion;
* it lives for ``CN_SECURITY_WEBSOCKET_TICKET_TTL_SECONDS`` — 60 seconds by
  default — against the access token's fifteen minutes.

It carries no roles. Nothing on the socket varies by role today, and a
credential that travels in a URL should assert the minimum that makes it useful.

Signed with ``CN_SECURITY_SECRET_KEY``, which the setting's own description
already promised ("Signs sessions and websocket tickets").
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from chartnexus.bootstrap.settings import AuthSettings, SecuritySettings
from chartnexus.contexts.realtime_delivery.application.ports import Ticket
from chartnexus.shared_kernel.domain.errors import AuthenticationError
from chartnexus.shared_kernel.types.identifiers import SessionId, TenantId, UserId

# A claim value, not a credential.
TICKET_TYPE = "ws-ticket"
TICKET_AUDIENCE = "chartnexus-ws"

# Tickets are always symmetric. RS256 exists on the access-token path so a
# second service can verify without the signing key; the realtime process holds
# the same configuration as the API, so that buys nothing here and asymmetric
# signing of a 60-second credential is cost without a benefit.
_ALGORITHM = "HS256"


class TicketExpiredError(AuthenticationError):
    """The ticket was valid but is past its (very short) lifetime."""

    code = "ticket_expired"


class TicketInvalidError(AuthenticationError):
    """Signature, audience, type or claims did not check out."""

    code = "not_authenticated"


@dataclass(frozen=True, slots=True)
class TicketClaims:
    """What a verified ticket asserts."""

    user_id: UserId
    tenant_id: TenantId
    session_id: SessionId
    jti: str
    issued_at: datetime
    expires_at: datetime


class JwtWebsocketTicketIssuer:
    """Signs and verifies websocket tickets.

    One object does both halves because one process may do both: the API mints
    them, the realtime process verifies them, and in local development those can
    be the same interpreter. Keeping the claim names in a single class is what
    stops the two sides from drifting.
    """

    def __init__(self, auth: AuthSettings, security: SecuritySettings) -> None:
        self._issuer = auth.issuer
        self._ttl_seconds = security.websocket_ticket_ttl_seconds
        # Deliberately the security secret, not auth.jwt_signing_key: a ticket is
        # a session-scoped credential, and CN_SECURITY_SECRET_KEY is the key
        # documented as signing them. No length guard here because the same value
        # already backs JwtAccessTokenIssuer, which enforces the HS256 minimum at
        # startup — a short key fails the process before it can reach this.
        self._key = security.secret_key.get_secret_value()

    def issue(
        self,
        *,
        user_id: UserId,
        tenant_id: TenantId,
        session_id: SessionId,
        now: datetime,
    ) -> Ticket:
        expires_at = now + timedelta(seconds=self._ttl_seconds)
        claims = {
            "iss": self._issuer,
            "aud": TICKET_AUDIENCE,
            "sub": str(user_id),
            "jti": uuid.uuid4().hex,
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "typ": TICKET_TYPE,
            "tid": str(tenant_id),
            "sid": str(session_id),
        }
        return Ticket(
            value=jwt.encode(claims, self._key, algorithm=_ALGORITHM),
            expires_at=expires_at,
            expires_in_seconds=self._ttl_seconds,
        )

    def verify(self, token: str) -> TicketClaims:
        """Decode and validate, or raise.

        Raises :class:`TicketExpiredError` separately from :class:`TicketInvalidError` so
        the handshake can tell a client "fetch another" rather than "you are not
        signed in" — a meaningful difference when the whole lifetime is 60
        seconds and a slow page load can legitimately miss the window.
        """
        try:
            payload = jwt.decode(
                token,
                self._key,
                # Pinned, not read from the token: this is what prevents the
                # "alg: none" bypass.
                algorithms=[_ALGORITHM],
                audience=TICKET_AUDIENCE,
                issuer=self._issuer,
                options={
                    "require": ["exp", "iat", "nbf", "sub", "jti", "aud", "iss"],
                    "verify_exp": True,
                    "verify_aud": True,
                    "verify_iss": True,
                    "verify_signature": True,
                },
            )
        except ExpiredSignatureError as exc:
            raise TicketExpiredError("This connection ticket has expired.") from exc
        except InvalidTokenError as exc:
            raise TicketInvalidError("This connection ticket is not valid.") from exc

        if payload.get("typ") != TICKET_TYPE:
            raise TicketInvalidError("This token cannot be used to open a connection.")

        try:
            return TicketClaims(
                user_id=UserId(uuid.UUID(payload["sub"])),
                tenant_id=TenantId(uuid.UUID(payload["tid"])),
                session_id=SessionId(uuid.UUID(payload["sid"])),
                jti=str(payload["jti"]),
                issued_at=datetime.fromtimestamp(payload["iat"], tz=UTC),
                expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
            )
        except (KeyError, ValueError) as exc:
            raise TicketInvalidError("This connection ticket is missing required claims.") from exc
