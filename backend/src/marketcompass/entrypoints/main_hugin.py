"""HUGIN worker process.

Runs the autonomous market-memory loop on its own cadence: each hour during the
IST session it snapshots the market per tenant, judges last hour's read, and
writes the graded memory HUGIN accumulates. Runs as its own process so a slow
broker or LLM call can never occupy an API worker.

The loop itself lives in :mod:`entrypoints.hugin_runtime`, shared with the API's
local in-process task so the two cannot drift. This module is just the process
shell: settings, signals, and the container lifetime.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal

from marketcompass.bootstrap.container import Container
from marketcompass.bootstrap.logging import configure_logging
from marketcompass.bootstrap.settings import Settings, get_settings
from marketcompass.entrypoints.hugin_runtime import run_hugin_loop
from marketcompass.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)


async def _run(settings: Settings) -> None:
    configure_logging(settings)
    container = Container.create(settings, use_db_pool=False)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        # Windows event loops do not support signal handlers; Ctrl+C still raises
        # KeyboardInterrupt out of asyncio.run and unwinds cleanly.
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    try:
        await run_hugin_loop(container, settings, stop=stop)
    finally:
        log.info("hugin_stopping")
        await container.aclose()


def run() -> None:
    """Console-script entrypoint: ``uv run marketcompass-hugin``."""
    asyncio.run(_run(get_settings()))


if __name__ == "__main__":
    run()
