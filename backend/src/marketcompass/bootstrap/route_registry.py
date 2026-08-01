"""Where every context's HTTP routes get attached.

One list, in one file: adding a context means adding a line here, and the API
surface can be read without hunting through the tree.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI

from marketcompass.contexts.identity.api.router import router as identity_router

API_PREFIX = "/api/v1"

_ROUTERS: tuple[APIRouter, ...] = (identity_router,)


def register_routes(app: FastAPI, *, prefix: str = API_PREFIX) -> None:
    for router in _ROUTERS:
        app.include_router(router, prefix=prefix)
