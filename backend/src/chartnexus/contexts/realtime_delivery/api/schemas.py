"""Wire contract for the realtime endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from chartnexus.contexts.realtime_delivery.application.ports import Ticket


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RealtimeTicketResponse(_Schema):
    #: The credential to put in the handshake query string:
    #: ``new WebSocket(`${PUBLIC_WS_URL}?ticket=${ticket}`)``.
    ticket: str
    #: Absolute expiry, UTC. Single-use as well as short-lived, so a client
    #: fetches a fresh one per connection attempt rather than caching this until
    #: it expires — a reconnect that reuses a spent ticket is refused with
    #: ``ticket_already_used``.
    expires_at: datetime
    #: The same window as a duration, so a client need not trust its own clock.
    expires_in_seconds: int

    @classmethod
    def of(cls, ticket: Ticket) -> RealtimeTicketResponse:
        return cls(
            ticket=ticket.value,
            expires_at=ticket.expires_at,
            expires_in_seconds=ticket.expires_in_seconds,
        )
