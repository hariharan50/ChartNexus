"""Mint a websocket ticket for an already-authenticated caller.

Why a ticket at all, rather than reusing the access token the caller just
authenticated with:

* **Browsers cannot set headers on a websocket handshake.** The `WebSocket`
  constructor takes a URL and subprotocols, nothing else. So the credential has
  to travel in the URL — and an access token in a URL lands in proxy logs,
  `Referer` headers and browser history, where a 12-hour session token must
  never be. A 60-second single-use ticket in the same place is a far smaller
  thing to lose.
* **Cookies do not reliably travel either.** The realtime process answers on its
  own origin (port 8001 in development), so `SameSite=lax` suppresses the cookie
  on the handshake. Relaxing that to `none` to make websockets work would weaken
  CSRF posture across the whole REST surface — paying for one feature out of
  everything else's security budget.

The ticket therefore asserts exactly what the socket needs and nothing more:
*this user, in this tenant, on this session, right now.* It grants no REST
authority, so a leaked one cannot be replayed against the API.
"""

from __future__ import annotations

from chartnexus.contexts.realtime_delivery.application.ports import Clock, Ticket, TicketIssuer
from chartnexus.shared_kernel.types.identifiers import SessionId, TenantId, UserId


class IssueRealtimeTicket:
    """Use case: give the caller a credential for one websocket connection.

    Synchronous because it is pure signing — no database, no Redis. Making it
    ``async`` for symmetry would only invite a caller to assume there is I/O
    here worth batching.
    """

    def __init__(self, *, issuer: TicketIssuer, clock: Clock) -> None:
        self._issuer = issuer
        self._clock = clock

    def __call__(
        self,
        *,
        user_id: UserId,
        tenant_id: TenantId,
        session_id: SessionId,
    ) -> Ticket:
        """Issue a ticket.

        No authorisation check of its own: holding a valid session is the whole
        requirement, and the route has already proven that by resolving a
        principal. A ticket conveys no more authority than the session it was
        minted from, so there is nothing further to gate on here.
        """
        return self._issuer.issue(
            user_id=user_id,
            tenant_id=tenant_id,
            session_id=session_id,
            now=self._clock.now(),
        )
