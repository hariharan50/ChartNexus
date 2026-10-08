"""Daily-report worker process.

Generates the branded daily market PDF per enrolled tenant each morning and
delivers it to their channels. Its own process so a slow render/LLM call never
occupies an API worker. The loop lives in :mod:`entrypoints.report_runtime`,
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
from chartnexus.entrypoints.report_runtime import run_report_loop
from chartnexus.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)


async def _run(settings: Settings) -> None:
    configure_logging(settings)
    container = Container.create(settings, use_db_pool=False)
    # Adapters resolve symbols through the catalog registry, so it has to
    # be warm before this process does any instrument work.
    await load_registry(container)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    try:
        async with registry_kept_current(container, settings, stop=stop):
            await run_report_loop(container, settings, stop=stop)
    finally:
        log.info("report_stopping")
        await container.aclose()


def run() -> None:
    """Console-script entrypoint: ``uv run chartnexus-report``."""
    asyncio.run(_run(get_settings()))


if __name__ == "__main__":
    run()
