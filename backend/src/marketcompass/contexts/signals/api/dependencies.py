"""Per-request assembly for the AI Market Guider routes.

The cross-context wiring lives in ``infrastructure`` (``build_guidance_market_source``),
so this module — inside the signals context — never imports ``market_data`` or
``options_analytics`` itself, only the infrastructure adapters that satisfy its
ports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.signals.application.get_guidance import GetGuidance
from marketcompass.contexts.signals.application.guidance_history import GetGuidanceHistory
from marketcompass.infrastructure.brokers.guidance_market_source import (
    build_guidance_market_source,
)
from marketcompass.infrastructure.persistence.postgresql.repositories.signals.decision_repository import (
    SqlAlchemySignalDecisionRepository,
)
from marketcompass.infrastructure.transport.http.dependencies import get_session


@dataclass(slots=True)
class SignalsServices:
    guidance: GetGuidance
    history: GetGuidanceHistory


def build_signals_services(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SignalsServices:
    market = build_guidance_market_source(request, session)
    repository = SqlAlchemySignalDecisionRepository(session)
    return SignalsServices(
        guidance=GetGuidance(market=market, repository=repository),
        history=GetGuidanceHistory(repository=repository),
    )


Services = Annotated[SignalsServices, Depends(build_signals_services)]
