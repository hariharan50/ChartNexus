"""Copilot chat endpoint.

Authenticated. Answers a free-form question about an instrument's current setup,
grounded in the signals guidance. Not cached — each question is distinct — but
the guidance it grounds on is (see the signals routes).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path

from marketcompass.contexts.copilot.api.dependencies import Services
from marketcompass.contexts.copilot.api.schemas import AskRequest, AskResponse
from marketcompass.infrastructure.transport.http.dependencies import CurrentPrincipal

router = APIRouter(prefix="/copilot", tags=["copilot"])

InstrumentParam = Annotated[
    str, Path(description="NIFTY, BANKNIFTY, or SENSEX", examples=["NIFTY"])
]


@router.post(
    "/{instrument_id}/ask",
    response_model=AskResponse,
    summary="Ask the guider about the current setup",
    description=(
        "Answers a plain-language question grounded in the current guidance — its "
        "call, skill breakdown, levels and scaffold. Uses the configured LLM when a "
        "key is set, otherwise a deterministic rule-based answer. Not investment advice."
    ),
    responses={422: {"description": "Unknown instrument"}},
)
async def ask(
    principal: CurrentPrincipal,
    services: Services,
    instrument_id: InstrumentParam,
    body: AskRequest,
) -> AskResponse:
    symbol = instrument_id.strip().upper()
    answer = await services.converse(principal.tenant_id, symbol, body.question)
    return AskResponse.of(answer)
