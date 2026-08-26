"""AI Console endpoints — Hella, the independent agentic guider.

Authenticated. Hella reads live market data through read-only tools and forms
her own view; she does not consult the deterministic signals engine.

* ``GET  /copilot/availability`` — whether a model is configured. The console is
  LLM-only, so the frontend disables the Agent tab when this is false.
* ``POST /{id}/ask`` — a single JSON answer (non-streaming).
* ``POST /{id}/ask/stream`` — a Server-Sent Events stream: the answer streams
  token-by-token with ``tool`` events showing what Hella is reading, and a
  ``session`` event that threads follow-up questions.

Not investment advice.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, status
from fastapi.responses import StreamingResponse

from marketcompass.contexts.copilot.api.dependencies import CopilotServices, Services
from marketcompass.contexts.copilot.api.schemas import (
    AskRequest,
    AskResponse,
    AvailabilityResponse,
)
from marketcompass.contexts.copilot.application.ports import (
    AgentDone,
    SkillsSelected,
    TextDelta,
    ToolFinished,
    ToolStarted,
    Turn,
)
from marketcompass.infrastructure.observability.structured_logging import get_logger
from marketcompass.infrastructure.transport.http.dependencies import CurrentPrincipal, Principal
from marketcompass.shared_kernel.types.identifiers import TenantId

log = get_logger(__name__)

router = APIRouter(prefix="/copilot", tags=["copilot"])

InstrumentParam = Annotated[
    str, Path(description="NIFTY, BANKNIFTY, or SENSEX", examples=["NIFTY"])
]


@router.get(
    "/availability",
    response_model=AvailabilityResponse,
    summary="Whether the AI Console is available",
    description="False when no LLM is configured — the Agent tab shows a notice instead of chat.",
)
async def availability(principal: CurrentPrincipal, services: Services) -> AvailabilityResponse:
    _ = principal
    return AvailabilityResponse(available=services.agent.available)


@router.post(
    "/{instrument_id}/ask",
    response_model=AskResponse,
    summary="Ask Hella about the current setup",
    description=(
        "A plain-language answer grounded in live market data Hella reads through her "
        "tools. Requires a configured LLM (see /copilot/availability). Not investment advice."
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
    summary="Stream an answer from Hella",
    description=(
        "Server-Sent Events. Streams Hella's answer token-by-token as she reads the "
        "market through her tools, with `tool` events for visibility and a `session` "
        "event that threads follow-ups. Requires a configured LLM. Not investment advice."
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


def _require_available(services: CopilotServices) -> None:
    if not services.agent.available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI Console is unavailable — no language model is configured.",
        )


async def _events(
    principal: Principal,
    services: CopilotServices,
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
            if isinstance(event, SkillsSelected):
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
        log.warning("copilot_stream_failed", error=repr(exc), exc_info=True)
        yield _frame({"type": "error", "message": _error_message(exc)})
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


_GENERIC_ERROR = "Sorry — I couldn't answer that just now."


def _error_message(exc: Exception) -> str:
    """Turn a provider failure into a message the user can act on.

    The common real-world cause is the user's own LLM key being out of credits,
    invalid, or rate-limited — surfacing that plainly (rather than the generic
    line) tells them to fix their key in Settings → AI instead of chasing a
    phantom bug. Anything unrecognised stays generic.
    """
    text = str(exc).lower()
    if "credit balance" in text or "billing" in text or "insufficient" in text:
        return (
            "Your Anthropic API key has run out of credits. Add credits or update "
            "the key in Settings → AI, then try again."
        )
    if "authentication" in text or "invalid x-api-key" in text or "unauthorized" in text:
        return "Your Anthropic API key looks invalid. Check it in Settings → AI, then try again."
    if "rate limit" in text or "429" in text or "overloaded" in text:
        return "The model is rate-limited right now. Wait a moment and try again."
    return _GENERIC_ERROR


def _frame(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
