"""Where every context's HTTP routes get attached.

One list, in one file: adding a context means adding a line here, and the API
surface can be read without hunting through the tree.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI

from marketcompass.contexts.ai_settings.api.router import router as ai_settings_router
from marketcompass.contexts.broker_connections.api.router import router as broker_router
from marketcompass.contexts.copilot.api.router import router as copilot_router
from marketcompass.contexts.hugin.api.router import router as hugin_router
from marketcompass.contexts.identity.api.router import router as identity_router
from marketcompass.contexts.market_data.api.router import router as market_router
from marketcompass.contexts.messaging.api.router import router as messaging_router
from marketcompass.contexts.mme100.api.router import router as mme100_router
from marketcompass.contexts.options_analytics.api.router import router as options_lab_router
from marketcompass.contexts.signals.api.router import router as signals_router
from marketcompass.contexts.stryx.api.router import router as stryx_router

API_PREFIX = "/api/v1"

_ROUTERS: tuple[APIRouter, ...] = (
    identity_router,
    broker_router,
    ai_settings_router,
    market_router,
    options_lab_router,
    signals_router,
    copilot_router,
    stryx_router,
    hugin_router,
    mme100_router,
    messaging_router,
)


def register_routes(app: FastAPI, *, prefix: str = API_PREFIX) -> None:
    for router in _ROUTERS:
        app.include_router(router, prefix=prefix)
