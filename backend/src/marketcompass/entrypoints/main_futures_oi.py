"""Open-interest sweep process.

Fills the Future Lab's build-up columns. Its own process because the sweep is
two hundred-odd sequential broker calls spread over minutes, which has no
business occupying an API worker. The loop lives in
:mod:`entrypoints.futures_oi_runtime`, shared with the API's local in-process
task so the two cannot drift.

``--once`` runs a single sweep and exits — for a release job, or for checking
the broker actually returns open interest before trusting the board.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import signal

from marketcompass.bootstrap.container import Container
from marketcompass.bootstrap.logging import configure_logging
from marketcompass.bootstrap.settings import Settings, get_settings
from marketcompass.entrypoints.catalog_runtime import load_registry
from marketcompass.entrypoints.futures_oi_runtime import run_futures_oi_loop, sweep_once
from marketcompass.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)


async def _run(settings: Settings, *, once: bool) -> None:
    configure_logging(settings)
    container = Container.create(settings, use_db_pool=False)
    # The sweep iterates the catalog, so it has to be warm first.
    await load_registry(container)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    try:
        if once:
            await sweep_once(container, settings)
        else:
            await run_futures_oi_loop(container, settings, stop=stop)
    finally:
        log.info("futures_oi_stopping")
        await container.aclose()


def run() -> None:
    """Console-script entrypoint: ``uv run marketcompass-futures-oi``."""
    parser = argparse.ArgumentParser(description="Sweep futures open interest.")
    parser.add_argument(
        "--once", action="store_true", help="Sweep once and exit instead of looping."
    )
    args = parser.parse_args()
    asyncio.run(_run(get_settings(), once=args.once))


if __name__ == "__main__":
    run()
