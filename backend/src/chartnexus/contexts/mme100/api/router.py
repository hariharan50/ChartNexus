"""MME100 endpoints — the "Market Made Easy 100%" pre-market analyst.

Authenticated. MME100 reads live India market data through the same read-only
tools as HELLA/STRYX, plus live global cues via web search, and answers with a
structured six-section pre-market analysis.

* ``GET  /mme100/availability`` — whether a model is configured. LLM-only, so the
  frontend disables the MME100 tab when this is false.
* ``POST /{id}/ask`` — a single JSON answer (non-streaming).
* ``POST /{id}/ask/stream`` — a Server-Sent Events stream: the analysis streams
  token-by-token with ``tool`` events showing what MME100 is reading, a ``skills``
  event listing the six sections, and a ``session`` event that threads follow-ups.
* ``GET  /mme100/briefing/today`` — today's stored pre-market briefing, if any.
* ``GET/PUT /mme100/enrollment`` — the per-tenant opt-in for the morning briefing.

Not investment advice — educational only.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Response, status
from fastapi.responses import StreamingResponse

from chartnexus.contexts.mme100.api.dependencies import Mme100Services, Services
from chartnexus.contexts.mme100.api.schemas import (
    AskRequest,
    AskResponse,
    AvailabilityResponse,
    BriefingResponse,
    EnrollmentResponse,
    SetEnrollmentRequest,
)
from chartnexus.contexts.mme100.application.ports import (
    AgentDone,
    SkillsConsidered,
    TextDelta,
    ToolFinished,
    ToolStarted,
    Turn,
)
from chartnexus.infrastructure.observability.structured_logging import get_logger
from chartnexus.infrastructure.transport.http.dependencies import CurrentPrincipal, Principal
from chartnexus.shared_kernel.types.identifiers import TenantId

log = get_logger(__name__)

router = APIRouter(prefix="/mme100", tags=["mme100"])

InstrumentParam = Annotated[
    str,
    Path(
        description="NIFTY, BANKNIFTY, or SENSEX. This surface is index-only;"
        " the wider F&O catalog is not covered here yet.",
        examples=["NIFTY"],
    ),
]


@router.get(
    "/availability",
    response_model=AvailabilityResponse,
    summary="Whether MME100 is available",
    description="False when no LLM is configured — the MME100 tab shows a notice instead of chat.",
)
async def availability(principal: CurrentPrincipal, services: Services) -> AvailabilityResponse:
    _ = principal
    return AvailabilityResponse(available=services.agent.available)


@router.get(
    "/enrollment",
    response_model=EnrollmentResponse,
    summary="Whether the pre-market briefing is turned on for this tenant",
    description="Off by default — the morning briefing spends the owner's LLM tokens when on.",
)
async def get_enrollment(principal: CurrentPrincipal, services: Services) -> EnrollmentResponse:
    enabled = await services.get_enrollment(principal.tenant_id)
    return EnrollmentResponse(enabled=enabled)


@router.put(
    "/enrollment",
    response_model=EnrollmentResponse,
    summary="Turn the pre-market briefing on or off for this tenant",
    description="Persists the opt-in. Turning it off stops the next morning's briefing.",
)
async def set_enrollment(
    principal: CurrentPrincipal,
    services: Services,
    body: SetEnrollmentRequest,
) -> EnrollmentResponse:
    enabled = await services.set_enrollment(principal.tenant_id, enabled=body.enabled)
    return EnrollmentResponse(enabled=enabled)


@router.get(
    "/briefing/today",
    response_model=BriefingResponse,
    summary="Today's stored pre-market briefing",
    description="The autonomous morning briefing for today's IST session. 204 when none exists yet.",
    responses={204: {"description": "No briefing generated yet today"}},
)
async def briefing_today(
    principal: CurrentPrincipal,
    services: Services,
) -> BriefingResponse | Response:
    briefing = await services.briefing.today(principal.tenant_id)
    if briefing is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return BriefingResponse.of(briefing)


@router.post(
    "/{instrument_id}/ask",
    response_model=AskResponse,
    summary="Ask MME100 for a pre-market analysis",
    description=(
        "A structured six-section analysis grounded in live India market data and web "
        "cues. Requires a configured LLM (see /mme100/availability). Not investment advice."
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
    summary="Stream an analysis from MME100",
    description=(
        "Server-Sent Events. Streams MME100's analysis token-by-token as it reads the "
        "market and the web, with `tool` events for visibility, a `skills` event for the "
        "six sections, and a `session` event that threads follow-ups. Requires a configured "
        "LLM. Not investment advice."
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


def _require_available(services: Mme100Services) -> None:
    if not services.agent.available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MME100 is unavailable — no language model is configured.",
        )


async def _events(
    principal: Principal,
    services: Mme100Services,
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
            if isinstance(event, SkillsConsidered):
                yield _frame({"type": "skills", "titles": list(event.titles)})
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
        log.warning("mme100_stream_failed", error=repr(exc))
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
