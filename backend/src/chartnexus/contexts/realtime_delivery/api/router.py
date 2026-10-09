"""Realtime delivery — the one REST route the websocket needs.

The socket itself is not served here. It runs in its own process
(``chartnexus.entrypoints.main_realtime``) on its own port, because a websocket
connection is held for the length of a trading session and an API worker
occupied by one is an API worker serving nobody. This endpoint is the handshake
the two processes share: the API, which owns sessions, mints a ticket; the
realtime process, which owns sockets, verifies it.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from chartnexus.contexts.realtime_delivery.api.dependencies import IssueTicket
from chartnexus.contexts.realtime_delivery.api.schemas import RealtimeTicketResponse
from chartnexus.infrastructure.transport.http.dependencies import CurrentPrincipal

router = APIRouter(prefix="/realtime", tags=["realtime"])


@router.post(
    "/ticket",
    response_model=RealtimeTicketResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Mint a single-use ticket for opening a websocket connection",
    description=(
        "POST, not GET, because each call mints a new credential — it creates "
        "something rather than reading it, and must never be cached or "
        "prefetched by a browser.\n\n"
        "The ticket is valid for 60 seconds and for exactly one connection. "
        "Fetch one immediately before each connection attempt, including every "
        "reconnect: replaying a spent ticket is refused with "
        "`ticket_already_used`, and an expired one with `ticket_expired`.\n\n"
        "It grants no authority over this REST surface. Its audience is the "
        "websocket process alone, so a ticket recovered from a proxy log or "
        "browser history cannot be used to call the API."
    ),
)
async def mint_ticket(
    principal: CurrentPrincipal,
    issue_ticket: IssueTicket,
) -> RealtimeTicketResponse:
    return RealtimeTicketResponse.of(
        issue_ticket(
            user_id=principal.user_id,
            tenant_id=principal.tenant_id,
            session_id=principal.session_id,
        )
    )
