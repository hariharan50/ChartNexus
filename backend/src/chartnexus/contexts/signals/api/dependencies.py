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

from chartnexus.contexts.signals.application.get_guidance import GetGuidance
from chartnexus.contexts.signals.application.guidance_history import GetGuidanceHistory
from chartnexus.infrastructure.analytics.model_provider import ModelProvider
from chartnexus.infrastructure.brokers.guidance_market_source import (
    build_guidance_market_source,
)
from chartnexus.infrastructure.persistence.postgresql.repositories.signals.decision_repository import (
    SqlAlchemySignalDecisionRepository,
)
from chartnexus.infrastructure.transport.http.dependencies import get_session


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
    model = ModelProvider()
    return SignalsServices(
        guidance=GetGuidance(market=market, repository=repository, model=model),
        history=GetGuidanceHistory(repository=repository),
    )


Services = Annotated[SignalsServices, Depends(build_signals_services)]
