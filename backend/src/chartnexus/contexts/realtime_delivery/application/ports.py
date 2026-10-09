"""Ports and DTOs for realtime delivery.

The context owns the rules behind a ticket — who may hold one, what it asserts,
how long it lives. It does not own the signing: that is a credential concern,
satisfied by ``infrastructure/security/websocket_tickets.py``.

Verifying a ticket is deliberately *not* a port here. Authenticating a
connection is transport's job, the same reasoning that puts ``Principal`` in
``infrastructure/transport/http/dependencies.py`` rather than in ``identity``:
this context owns the rules behind the credential, never the act of checking one
at the edge.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from chartnexus.shared_kernel.types.identifiers import SessionId, TenantId, UserId


@dataclass(frozen=True, slots=True)
class Ticket:
    """A short-lived bearer credential for opening one websocket connection.

    ``expires_in_seconds`` is carried alongside ``expires_at`` so a client can
    schedule its next fetch without trusting its own clock — the same reason the
    REST access-token response carries both.
    """

    value: str
    expires_at: datetime
    expires_in_seconds: int


@runtime_checkable
class TicketIssuer(Protocol):
    """Mints a signed ticket. Satisfied by the JWT adapter."""

    def issue(
        self,
        *,
        user_id: UserId,
        tenant_id: TenantId,
        session_id: SessionId,
        now: datetime,
    ) -> Ticket: ...


@runtime_checkable
class Clock(Protocol):
    """Current time, injected so ticket expiry is testable without sleeping."""

    def now(self) -> datetime: ...
