"""STRYX endpoints — the aggressive trade-call agent.

Authenticated. STRYX reads live market data through the same read-only tools as
HELLA and issues a structured [STRYX CALL] (or NO TRADE / WATCHING), inside a hard
discipline frame: every LIVE call carries a stop, and at most two LIVE calls are
issued per trading day (enforced from the journal).

* ``GET  /stryx/availability`` — whether a model is configured. LLM-only, so the
  frontend disables the STRYX tab when this is false.
* ``POST /{id}/ask`` — a single JSON answer (non-streaming).
* ``POST /{id}/ask/stream`` — a Server-Sent Events stream: the call streams
  token-by-token with ``tool`` events showing what STRYX is reading, a ``styles``
  event listing the playbook, and a ``session`` event that threads follow-ups.
* ``GET  /{id}/journal/today`` — today's calls and the remaining LIVE-call budget.

Not investment advice — educational / paper-trade only.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, status
from fastapi.responses import StreamingResponse

from marketcompass.contexts.stryx.api.dependencies import Services, StryxServices
from marketcompass.contexts.stryx.api.schemas import (
    AskRequest,
    AskResponse,
    AvailabilityResponse,
    JournalTodayResponse,
)
from marketcompass.contexts.stryx.application.ports import (
    AgentDone,
    StylesConsidered,
    TextDelta,
    ToolFinished,
    ToolStarted,
    Turn,
)
from marketcompass.infrastructure.observability.structured_logging import get_logger
from marketcompass.infrastructure.transport.http.dependencies import CurrentPrincipal, Principal
from marketcompass.shared_kernel.types.identifiers import TenantId

log = get_logger(__name__)

router = APIRouter(prefix="/stryx", tags=["stryx"])

InstrumentParam = Annotated[
    str, Path(description="NIFTY, BANKNIFTY, or SENSEX", examples=["NIFTY"])
]


@router.get(
    "/availability",
    response_model=AvailabilityResponse,
    summary="Whether STRYX is available",
    description="False when no LLM is configured — the STRYX tab shows a notice instead of chat.",
)
async def availability(principal: CurrentPrincipal, services: Services) -> AvailabilityResponse:
    _ = principal
    return AvailabilityResponse(available=services.agent.available)


@router.post(
    "/{instrument_id}/ask",
    response_model=AskResponse,
    summary="Ask STRYX for a call on the current setup",
    description=(
        "A structured [STRYX CALL] (or NO TRADE / WATCHING) grounded in live market data "
        "STRYX reads through its tools. Requires a configured LLM (see /stryx/availability). "
        "Not investment advice."
    ),
    responses={
        422: {"description": "Unknown instrument"},
        503: {"description": "No LLM configured"},
    },
)
async def ask(
    principal: CurrentPrincipal,
    services: Services,
    instrument_id: InstrumentParam,
    body: AskRequest,
) -> AskResponse:
    _require_available(services)
    symbol = instrument_id.strip().upper()
    answer = await services.agent(principal.tenant_id, symbol, body.question)
    return AskResponse.of(answer)


@router.post(
    "/{instrument_id}/ask/stream",
    summary="Stream a call from STRYX",
    description=(
        "Server-Sent Events. Streams STRYX's call token-by-token as it reads the market, "
        "with `tool` events for visibility, a `styles` event for the playbook, and a "
        "`session` event that threads follow-ups. Requires a configured LLM. Not investment "
        "advice."
    ),
    responses={
        422: {"description": "Unknown instrument"},
        503: {"description": "No LLM configured"},
    },
)
async def ask_stream(
    principal: CurrentPrincipal,
    services: Services,
    instrument_id: InstrumentParam,
    body: AskRequest,
) -> StreamingResponse:
    _require_available(services)
    symbol = instrument_id.strip().upper()
    return StreamingResponse(
        _events(principal, services, symbol, body),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/{instrument_id}/journal/today",
    response_model=JournalTodayResponse,
    summary="Today's STRYX calls and remaining LIVE-call budget",
    description=(
        "Every call STRYX logged today (LIVE / NO TRADE / WATCHING), newest first, plus how "
        "many LIVE calls remain before the daily cap. The instrument is accepted for "
        "symmetry with the other routes; the journal is tenant-wide for the day."
    ),
)
async def journal_today(
    principal: CurrentPrincipal,
    services: Services,
    instrument_id: InstrumentParam,
) -> JournalTodayResponse:
    _ = instrument_id
    entries = await services.journal.today(principal.tenant_id)
    return JournalTodayResponse.of(entries)


def _require_available(services: StryxServices) -> None:
    if not services.agent.available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="STRYX is unavailable — no language model is configured.",
        )


async def _events(
    principal: Principal,
    services: StryxServices,
    symbol: str,
    body: AskRequest,
) -> AsyncIterator[str]:
    """The SSE body: `data: {json}\\n\\n` frames for each agent event."""
    tenant: TenantId = principal.tenant_id
    session = await services.sessions.load(body.session_id)
    yield _frame({"type": "session", "session_id": session.id})

    answer = ""
    try:
        async for event in services.agent.stream(
            tenant, symbol, body.question, history=list(session.turns)
        ):
            if isinstance(event, StylesConsidered):
                yield _frame({"type": "styles", "titles": list(event.titles)})
            elif isinstance(event, TextDelta):
                answer += event.text
                yield _frame({"type": "token", "text": event.text})
            elif isinstance(event, ToolStarted):
                yield _frame(
                    {"type": "tool", "status": "started", "name": event.name, "title": event.title}
                )
            elif isinstance(event, ToolFinished):
                yield _frame({"type": "tool", "status": "finished", "name": event.name})
            elif isinstance(event, AgentDone):
                answer = event.text or answer
    except Exception as exc:  # a stream must not 500 mid-flight
        log.warning("stryx_stream_failed", error=repr(exc))
        # Only surface the error when the turn produced nothing. A failure *after*
        # the call has streamed (journaling, say) must not throw the call away —
        # the client renders an `error` frame in place of the answer.
        if not answer:
            yield _frame({"type": "error", "message": "Couldn't get a read just now — try again."})
            return

    # Remember this exchange so the next question carries context; skip empties.
    if answer:
        turns = (
            *session.turns,
            Turn(role="user", text=body.question),
            Turn(role="assistant", text=answer),
        )
        await services.sessions.save(replace(session, turns=turns))

    yield _frame({"type": "done"})


def _frame(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
