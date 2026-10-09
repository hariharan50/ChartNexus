"""Per-request assembly for the realtime routes.

No bridge module and no independence exemption needed, unlike most contexts
here: issuing a ticket needs nothing from another context. It needs the signer,
which the container already holds, reached through the shared
``get_container`` in transport — the same loosely-typed accessor every router
uses, which is what keeps this context free of an import of the composition
root.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request

from chartnexus.contexts.realtime_delivery.application.issue_ticket import IssueRealtimeTicket
from chartnexus.infrastructure.transport.http.dependencies import get_container

__all__ = ["IssueTicket", "build_issue_ticket"]


class _SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def build_issue_ticket(request: Request) -> IssueRealtimeTicket:
    """Wire the use case.

    ``container.websocket_tickets`` is read structurally rather than imported:
    the use case declares a ``TicketIssuer`` protocol, and the concrete JWT
    adapter is chosen in the container. This module never names it.
    """
    container = get_container(request)
    return IssueRealtimeTicket(issuer=container.websocket_tickets, clock=_SystemClock())


IssueTicket = Annotated[IssueRealtimeTicket, Depends(build_issue_ticket)]
