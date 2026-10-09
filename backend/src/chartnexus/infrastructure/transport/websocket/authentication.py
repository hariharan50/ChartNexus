"""Authenticating a websocket handshake.

Transport's job, not the context's — the same division that puts ``Principal``
in ``transport/http/dependencies.py`` and leaves ``identity`` owning only the
rules behind the token.

Two checks, in this order:

1. **Signature, audience, type and expiry**, by the ticket issuer.
2. **Replay**, by burning the ticket's ``jti`` in Redis.

Step 2 is what makes a ticket single-use. A 60-second credential that travels in
a URL will end up in a proxy log or a browser history; making it good for
exactly one connection means a copy recovered from there is already spent. The
burn uses ``SET NX`` with the ticket's own remaining lifetime as the TTL, so the
marker expires on its own and the keyspace cannot grow without bound.

Fails closed. If Redis is unreachable the handshake is refused rather than
waved through: this process cannot deliver anything without Redis anyway, so
"degrade to insecure" would buy nothing and cost the replay guarantee.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from chartnexus.infrastructure.cache.redis.client import RedisClient
from chartnexus.infrastructure.observability.structured_logging import get_logger
from chartnexus.infrastructure.security.websocket_tickets import (
    JwtWebsocketTicketIssuer,
    TicketClaims,
    TicketExpiredError,
    TicketInvalidError,
)
from chartnexus.infrastructure.transport.websocket import protocol

log = get_logger(__name__)

_BURN_KEY_PREFIX = "ws:ticket"

# Floor for the burn marker's TTL. A ticket presented in its final moments would
# otherwise get a zero or negative expiry, which Redis rejects — and a marker
# that never gets written is a ticket that stays replayable.
_MIN_BURN_TTL_SECONDS = 1


class TicketAlreadyUsedError(Exception):
    """This ticket has already opened a connection."""


@dataclass(frozen=True, slots=True)
class AuthenticatedConnection:
    """The verified identity behind an accepted socket."""

    claims: TicketClaims

    @property
    def user_id(self) -> str:
        return str(self.claims.user_id)

    @property
    def tenant_id(self) -> str:
        return str(self.claims.tenant_id)


class HandshakeAuthenticator:
    """Verifies the ticket presented on a websocket handshake."""

    def __init__(
        self,
        *,
        tickets: JwtWebsocketTicketIssuer,
        redis: RedisClient,
        single_use: bool = True,
    ) -> None:
        self._tickets = tickets
        self._redis = redis
        self._single_use = single_use

    async def authenticate(self, ticket: str | None, *, now: datetime) -> AuthenticatedConnection:
        """Verify ``ticket``, or raise.

        Raises :class:`TicketInvalidError`, :class:`TicketExpiredError` or
        :class:`TicketAlreadyUsedError` — three cases the caller reports with three
        different protocol codes, because a client's correct response differs:
        sign in again, fetch another ticket, or stop reconnecting in a loop.
        """
        if not ticket:
            raise TicketInvalidError("A connection ticket is required.")

        claims = self._tickets.verify(ticket)

        if self._single_use and not await self._burn(claims, now=now):
            log.warning(
                "ws_ticket_replayed",
                jti=claims.jti,
                user_id=str(claims.user_id),
                tenant_id=str(claims.tenant_id),
            )
            raise TicketAlreadyUsedError("This connection ticket has already been used.")

        return AuthenticatedConnection(claims=claims)

    async def _burn(self, claims: TicketClaims, *, now: datetime) -> bool:
        """Claim this ticket's id. ``False`` means someone already did.

        The TTL is the ticket's own remaining life: once it has expired on its
        own terms the marker is redundant, so there is nothing to keep.
        """
        remaining = int((claims.expires_at - now).total_seconds())
        written = await self._redis.client.set(
            self._redis.key(_BURN_KEY_PREFIX, claims.jti),
            b"1",
            ex=max(remaining, _MIN_BURN_TTL_SECONDS),
            nx=True,
        )
        return bool(written)


def close_code_for(exc: Exception) -> int:
    """Which websocket close code a failed handshake deserves."""
    if isinstance(exc, (TicketInvalidError, TicketExpiredError, TicketAlreadyUsedError)):
        return protocol.CLOSE_POLICY_VIOLATION
    return protocol.CLOSE_INTERNAL_ERROR


def error_code_for(exc: Exception) -> str:
    """Which protocol error code to report for a failed handshake."""
    if isinstance(exc, TicketExpiredError):
        return protocol.TICKET_EXPIRED
    if isinstance(exc, TicketAlreadyUsedError):
        return protocol.TICKET_ALREADY_USED
    if isinstance(exc, TicketInvalidError):
        return protocol.NOT_AUTHENTICATED
    return protocol.INTERNAL_ERROR
