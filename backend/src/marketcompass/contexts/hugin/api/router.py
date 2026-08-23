"""HUGIN endpoints — the desk's autonomous market memory.

Authenticated and **read-only**: HUGIN writes only from its background worker, so
there is no "ask" endpoint here. The UI polls these to render the hourly timeline,
the accumulated lessons, and HUGIN's self-measured hit-rate. The tenant always
comes from ``CurrentPrincipal``, never the request body.

* ``GET /hugin/availability`` — whether the caller has an LLM key (gates the tab).
* ``GET /hugin/{instrument}/memory/today`` — today's observations + grades + lessons + hit-rate.
* ``GET /hugin/{instrument}/observations/latest`` — the most recent hourly read.
* ``GET /hugin/memory/lessons`` — everything HUGIN has learned, across days.

Not investment advice — educational only.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Path, Query, Response, status
from fastapi.responses import StreamingResponse

from marketcompass.contexts.hugin.api.dependencies import CallServices, ChatServices, Services
from marketcompass.contexts.hugin.api.schemas import (
    AskRequest,
    AvailabilityResponse,
    CallResponse,
    CallsResponse,
    EnrollmentResponse,
    HistoryResponse,
    LessonsResponse,
    MemoryTodayResponse,
    ObservationResponse,
    SetEnrollmentRequest,
)
from marketcompass.contexts.hugin.domain.conversation import ChatDone, TextDelta, Turn
from marketcompass.infrastructure.observability.structured_logging import get_logger
from marketcompass.infrastructure.transport.http.dependencies import CurrentPrincipal, Principal

log = get_logger(__name__)

router = APIRouter(prefix="/hugin", tags=["hugin"])

InstrumentParam = Annotated[
    str, Path(description="NIFTY, BANKNIFTY, or SENSEX", examples=["NIFTY"])
]


@router.get(
    "/availability",
    response_model=AvailabilityResponse,
    summary="Whether HUGIN is available",
    description="False when the caller has no LLM key — the HUGIN tab shows a notice instead.",
)
async def availability(principal: CurrentPrincipal, services: Services) -> AvailabilityResponse:
    _ = principal
    return AvailabilityResponse(available=services.available)


@router.get(
    "/enrollment",
    response_model=EnrollmentResponse,
    summary="Whether HUGIN is turned on for this tenant",
    description="HUGIN is off by default — it spends the owner's LLM tokens hourly when on.",
)
async def get_enrollment(principal: CurrentPrincipal, services: Services) -> EnrollmentResponse:
    enabled = await services.get_enrollment(principal.tenant_id)
    return EnrollmentResponse(enabled=enabled)


@router.put(
    "/enrollment",
    response_model=EnrollmentResponse,
    summary="Turn HUGIN on or off for this tenant",
    description="Persists the opt-in. Turning it off stops HUGIN at the next hourly tick.",
)
async def set_enrollment(
    principal: CurrentPrincipal,
    services: Services,
    body: SetEnrollmentRequest,
) -> EnrollmentResponse:
    enabled = await services.set_enrollment(principal.tenant_id, enabled=body.enabled)
    return EnrollmentResponse(enabled=enabled)


@router.get(
    "/{instrument_id}/memory/today",
    response_model=MemoryTodayResponse,
    summary="Today's HUGIN memory for an instrument",
    description=(
        "The day's hourly observations (each with its grade once the next hour lands), "
        "the active lessons, and the running hit-rate HUGIN measures on itself."
    ),
)
async def memory_today(
    principal: CurrentPrincipal,
    services: Services,
    instrument_id: InstrumentParam,
) -> MemoryTodayResponse:
    symbol = instrument_id.strip().upper()
    view = await services.memory.today(principal.tenant_id, symbol)
    return MemoryTodayResponse.of(view)


@router.get(
    "/{instrument_id}/history",
    response_model=HistoryResponse,
    summary="HUGIN's multi-day track record for an instrument",
    description=(
        "Per-day observations and hit-rate across the last N trading days, newest day first, "
        "plus the overall hit-rate — the 'watch it sharpen' view."
    ),
)
async def history(
    principal: CurrentPrincipal,
    services: Services,
    instrument_id: InstrumentParam,
    days: Annotated[int, Query(ge=1, le=60, description="Trading days to include")] = 7,
) -> HistoryResponse:
    symbol = instrument_id.strip().upper()
    view = await services.history(principal.tenant_id, symbol, days)
    return HistoryResponse.of(view)


@router.get(
    "/{instrument_id}/observations/latest",
    response_model=ObservationResponse,
    summary="The most recent hourly read",
    description="The panel headline. 204 when HUGIN has recorded nothing yet.",
    responses={204: {"description": "No observation recorded yet"}},
)
async def latest_observation(
    principal: CurrentPrincipal,
    services: Services,
    instrument_id: InstrumentParam,
) -> ObservationResponse | Response:
    symbol = instrument_id.strip().upper()
    view = await services.memory.latest(principal.tenant_id, symbol)
    if view is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return ObservationResponse.of(view)


@router.get(
    "/memory/lessons",
    response_model=LessonsResponse,
    summary="Everything HUGIN has learned",
    description="The accumulated lessons across days, with their hit/miss tallies and weight.",
)
async def lessons(principal: CurrentPrincipal, services: Services) -> LessonsResponse:
    views = await services.memory.lessons(principal.tenant_id)
    return LessonsResponse.of(views)


@router.post(
    "/{instrument_id}/call",
    response_model=CallResponse,
    summary="Generate and save a memory-driven call",
    description=(
        "HUGIN turns its accumulated memory (reads, lessons, track record) into a two-part call — "
        "an analytical read with conviction and a concrete trade structure — and saves it. "
        "Requires a configured LLM. Not investment advice."
    ),
    responses={503: {"description": "No LLM configured"}},
)
async def make_call(
    principal: CurrentPrincipal,
    services: CallServices,
    instrument_id: InstrumentParam,
) -> CallResponse:
    if not services.generate.available:
        raise _unavailable()
    symbol = instrument_id.strip().upper()
    call = await services.generate(principal.tenant_id, symbol)
    return CallResponse.of(call)


@router.get(
    "/{instrument_id}/calls",
    response_model=CallsResponse,
    summary="Recent HUGIN calls for an instrument",
    description="The calls HUGIN has saved, newest first.",
)
async def recent_calls(
    principal: CurrentPrincipal,
    services: CallServices,
    instrument_id: InstrumentParam,
) -> CallsResponse:
    symbol = instrument_id.strip().upper()
    calls = await services.recent(principal.tenant_id, symbol)
    return CallsResponse.of(calls)


@router.post(
    "/{instrument_id}/ask/stream",
    summary="Chat with HUGIN about what it has learned",
    description=(
        "Server-Sent Events. HUGIN answers grounded ONLY in its stored memory (its hourly reads, "
        "graded track record, and lessons) — not live market tools. Requires a configured LLM. "
        "Not investment advice."
    ),
    responses={503: {"description": "No LLM configured"}},
)
async def ask_stream(
    principal: CurrentPrincipal,
    services: ChatServices,
    instrument_id: InstrumentParam,
    body: AskRequest,
) -> StreamingResponse:
    if not services.ask.available:
        raise _unavailable()
    symbol = instrument_id.strip().upper()
    return StreamingResponse(
        _events(principal, services, symbol, body),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _unavailable() -> Exception:
    from fastapi import HTTPException  # noqa: PLC0415

    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="HUGIN chat is unavailable — no language model is configured.",
    )


async def _events(
    principal: Principal,
    services: ChatServices,
    symbol: str,
    body: AskRequest,
) -> AsyncIterator[str]:
    """The SSE body: `data: {json}` frames for each chat event."""
    session = await services.sessions.load(body.session_id)
    yield _frame({"type": "session", "session_id": session.id})

    answer = ""
    try:
        async for event in services.ask.stream(
            principal.tenant_id, symbol, body.question, history=list(session.turns)
        ):
            if isinstance(event, TextDelta):
                answer += event.text
                yield _frame({"type": "token", "text": event.text})
            elif isinstance(event, ChatDone):
                answer = event.text or answer
    except Exception as exc:  # a stream must not 500 mid-flight
        log.warning("hugin_chat_stream_failed", error=repr(exc))
        if not answer:
            yield _frame({"type": "error", "message": "Couldn't answer just now — try again."})
            return

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
