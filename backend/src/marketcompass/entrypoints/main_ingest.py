"""Market ingestion process.

Captures option-chain snapshots on a fixed cadence during market hours and
writes them to Postgres, building the application's own time-series archive of
open interest. Runs as its own process so a slow broker call can never occupy an
API worker.

The capture loop itself lives in :mod:`infrastructure.ingestion.scheduler`,
shared with the API's local in-process loop so the two cannot drift. This module
is just the process shell: settings, signals, and the container lifetime.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal

from marketcompass.bootstrap.container import Container
from marketcompass.bootstrap.logging import configure_logging
from marketcompass.bootstrap.settings import Settings, get_settings
from marketcompass.entrypoints.ingest_runtime import run_capture_loop
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
        await run_capture_loop(container, settings, stop=stop)
    finally:
        log.info("ingest_stopping")
        await container.aclose()


def run() -> None:
    """Console-script entrypoint: ``uv run marketcompass-ingest``."""
    asyncio.run(_run(get_settings()))


if __name__ == "__main__":
    run()
