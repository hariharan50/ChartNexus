"""Per-request assembly for the market-breadth routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.infrastructure.breadth.build_breadth import (
    BreadthServices,
    build_breadth_services,
)
from marketcompass.infrastructure.transport.http.dependencies import get_container, get_session


def build_services(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BreadthServices:
    return build_breadth_services(get_container(request), session)


Services = Annotated[BreadthServices, Depends(build_services)]
