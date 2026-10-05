"""Instrument-catalog worker process.

Refreshes the F&O universe from the exchange symbol master each morning. Its
own process so a 15 MB download never occupies an API worker. The loop lives in
:mod:`entrypoints.catalog_runtime`, shared with the API's local in-process task
so the two cannot drift.

``--once`` runs a single sync and exits, which is what a deployment's release
job (or a developer with an empty ``instruments`` table) wants.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import signal

from chartnexus.bootstrap.container import Container
from chartnexus.bootstrap.logging import configure_logging
from chartnexus.bootstrap.settings import Settings, get_settings
from chartnexus.entrypoints.catalog_runtime import run_catalog_loop, sync_once
from chartnexus.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)


async def _run(settings: Settings, *, once: bool) -> None:
    configure_logging(settings)
    container = Container.create(settings, use_db_pool=False)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    try:
        if once:
            await sync_once(container)
        else:
            await run_catalog_loop(container, settings, stop=stop)
    finally:
        log.info("catalog_stopping")
        await container.aclose()


def run() -> None:
    """Console-script entrypoint: ``uv run chartnexus-catalog``."""
    parser = argparse.ArgumentParser(description="Refresh the instrument catalog.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Sync once and exit instead of running the daily loop.",
    )
    args = parser.parse_args()
    asyncio.run(_run(get_settings(), once=args.once))


if __name__ == "__main__":
    run()
