"""Where every context's HTTP routes get attached.

One list, in one file: adding a context means adding a line here, and the API
surface can be read without hunting through the tree.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI

from chartnexus.contexts.ai_settings.api.router import router as ai_settings_router
from chartnexus.contexts.broker_connections.api.router import router as broker_router
from chartnexus.contexts.copilot.api.router import router as copilot_router
from chartnexus.contexts.futures_analytics.api.router import router as futures_router
from chartnexus.contexts.global_markets.api.router import router as global_router
from chartnexus.contexts.hugin.api.router import router as hugin_router
from chartnexus.contexts.identity.api.router import router as identity_router
from chartnexus.contexts.instrument_catalog.api.router import router as instruments_router
from chartnexus.contexts.market_breadth.api.router import router as breadth_router
from chartnexus.contexts.market_data.api.router import router as market_router
from chartnexus.contexts.messaging.api.router import router as messaging_router
from chartnexus.contexts.mme100.api.router import router as mme100_router
from chartnexus.contexts.options_analytics.api.router import router as options_lab_router
from chartnexus.contexts.realtime_delivery.api.router import router as realtime_router
from chartnexus.contexts.report.api.router import router as report_router
from chartnexus.contexts.signals.api.router import router as signals_router
from chartnexus.contexts.stryx.api.router import router as stryx_router

API_PREFIX = "/api/v1"

_ROUTERS: tuple[APIRouter, ...] = (
    identity_router,
    broker_router,
    ai_settings_router,
    instruments_router,
    market_router,
    options_lab_router,
    futures_router,
    breadth_router,
    global_router,
    signals_router,
    copilot_router,
    stryx_router,
    hugin_router,
    mme100_router,
    messaging_router,
    report_router,
    realtime_router,
)


def register_routes(app: FastAPI, *, prefix: str = API_PREFIX) -> None:
    for router in _ROUTERS:
        app.include_router(router, prefix=prefix)
