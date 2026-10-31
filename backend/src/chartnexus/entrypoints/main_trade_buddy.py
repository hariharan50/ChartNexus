"""Trade Buddy watcher process.

Holds a Fyers WebSocket open through the session and alerts on the morning's
marked levels. Its own process so a stalled socket never occupies an API
worker, and so the watch survives an API restart — a redeploy at 11:00 must not
be a gap in the watch. The loop lives in :mod:`entrypoints.trade_buddy_runtime`,
shared with the API's local in-process task so the two cannot drift.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal

from chartnexus.bootstrap.container import Container
from chartnexus.bootstrap.logging import configure_logging
from chartnexus.bootstrap.settings import Settings, get_settings
from chartnexus.entrypoints.catalog_runtime import load_registry, registry_kept_current
from chartnexus.entrypoints.trade_buddy_runtime import run_trade_buddy_loop
from chartnexus.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)


async def _run(settings: Settings) -> None:
    configure_logging(settings)
    # A pool is needed: the Fyers credentials come from the broker connection
    # the user made in the app, which lives in Postgres. The levels themselves
    # are still a JSON file — that part never touches the database.
    container = Container.create(settings, use_db_pool=True)
    # Adapters resolve symbols through the catalog registry, so it has to be
    # warm before this process subscribes to anything.
    await load_registry(container)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    try:
        async with registry_kept_current(container, settings, stop=stop):
            await run_trade_buddy_loop(container, settings, stop=stop)
    finally:
        log.info("trade_buddy_stopping")
        await container.aclose()


def run() -> None:
    """Console-script entrypoint: ``uv run chartnexus-trade-buddy``."""
    asyncio.run(_run(get_settings()))


if __name__ == "__main__":
    run()
