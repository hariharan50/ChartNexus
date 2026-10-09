"""Websocket fan-out process.

Delivers market events to connected browsers over the protocol in
``contracts/websocket/v1/``. Runs as its own process because a websocket is held
for the length of a trading session: an API worker occupied by one is an API
worker serving nobody.

It reads nothing from Postgres and calls no broker. The only thing it consumes
is a Redis channel the ingest worker publishes to, and the only thing it sends
is a prompt to refetch — the browser then reads the detail over REST into the
same query cache the polled reads fill. That is why a frame carries headline
numbers rather than a 54-strike chain: one transport owns the shapes, and the
socket never has to version a large payload.

The application and the connection lifecycle live in
:mod:`entrypoints.realtime_runtime`, shared with any test that drives the socket
directly. This module is just the process shell: settings, signals, and uvicorn.

Authentication is by short-lived single-use ticket, minted by the API at
``POST /api/v1/realtime/ticket`` and presented as ``?ticket=`` on the handshake.
A browser cannot set headers on a websocket handshake and the cross-origin
cookie will not travel, so the credential has to be in the URL — which is
exactly why it is good for sixty seconds and one connection.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal

import uvicorn

from chartnexus.bootstrap.logging import configure_logging
from chartnexus.bootstrap.settings import Settings, get_settings
from chartnexus.entrypoints.realtime_runtime import create_app
from chartnexus.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)


async def _run(settings: Settings) -> None:
    configure_logging(settings)

    if not settings.realtime.enabled:
        # Explicit and loud. A silently exiting process under `restart:
        # unless-stopped` is a restart loop nobody can explain.
        log.info("realtime_disabled", reason="CN_REALTIME_ENABLED is false")
        return

    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings),
            host=settings.realtime.host,
            port=settings.realtime.port,
            log_config=None,
            access_log=False,
            # A websocket handshake arrives through nginx like any other
            # request, so without these the scheme reads as http and
            # request.client.host is the proxy for every caller. Trusted only
            # because nothing but the edge proxy can reach this port.
            proxy_headers=True,
            forwarded_allow_ips="*",
            # Protocol-level keepalive. This is what detects a browser that
            # vanished without closing — a laptop lid, a dropped tunnel — which
            # the application cannot see, because a silent client is normal.
            ws_ping_interval=20.0,
            ws_ping_timeout=20.0,
        )
    )

    # uvicorn installs its own handlers when it owns the process; this process
    # drives the server itself, so the signal wiring is ours. Windows event
    # loops do not support add_signal_handler — Ctrl+C still raises
    # KeyboardInterrupt out of asyncio.run and unwinds cleanly.
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, lambda: setattr(server, "should_exit", True))

    try:
        await server.serve()
    finally:
        log.info("realtime_stopped")


def run() -> None:
    """Console-script entrypoint: ``uv run chartnexus-realtime``."""
    asyncio.run(_run(get_settings()))


if __name__ == "__main__":
    run()
