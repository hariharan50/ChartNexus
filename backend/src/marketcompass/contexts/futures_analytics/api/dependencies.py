"""Per-request assembly for the futures-analytics routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.infrastructure.futures.build_futures import (
    FuturesServices,
    build_futures_services,
)
from marketcompass.infrastructure.transport.http.dependencies import get_container, get_session


def build_services(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FuturesServices:
    return build_futures_services(get_container(request), session)


Services = Annotated[FuturesServices, Depends(build_services)]
