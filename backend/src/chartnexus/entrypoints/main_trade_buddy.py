"""Trade Buddy watcher process.

Holds one market-feed socket open through the session and alerts every user on
their own marked levels, on their own channels. Its own process so a stalled
socket never occupies an API worker, and so the watch survives an API restart —
a redeploy at 11:00 must not be a gap in the watch. The loop lives in
:mod:`entrypoints.trade_buddy_runtime`, shared with the API's local in-process
task so the two cannot drift.

``import-legacy --email <user>`` instead copies a single-operator install's old
JSON state files into that user's account, once, and exits.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import signal
import sys
from pathlib import Path

from chartnexus.bootstrap.container import Container
from chartnexus.bootstrap.logging import configure_logging
from chartnexus.bootstrap.settings import Settings, get_settings
from chartnexus.entrypoints.catalog_runtime import load_registry, registry_kept_current
from chartnexus.entrypoints.trade_buddy_import import LegacyImportError, import_legacy
from chartnexus.entrypoints.trade_buddy_runtime import run_trade_buddy_loop
from chartnexus.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)


async def _import(settings: Settings, *, email: str, directory: Path, force: bool) -> int:
    configure_logging(settings)
    container = Container.create(settings, use_db_pool=False)
    try:
        result = await import_legacy(container, email=email, directory=directory, force=force)
    except LegacyImportError as exc:
        print(f"import-legacy: {exc}", file=sys.stderr)
        return 1
    finally:
        await container.aclose()
    print(
        f"imported: {', '.join(result.imported) or 'nothing'}"
        f"; skipped: {', '.join(result.skipped) or 'nothing'}"
    )
    return 0


async def _run(settings: Settings) -> None:
    configure_logging(settings)
    # A pool is needed: every user's levels, channels and broker connection
    # live in Postgres, and the worker reads them all session long.
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
    parser = argparse.ArgumentParser(description="Trade Buddy level watcher.")
    commands = parser.add_subparsers(dest="command")
    legacy = commands.add_parser(
        "import-legacy",
        help="Copy a single-operator install's JSON state files into one user's account.",
    )
    legacy.add_argument("--email", required=True, help="The user who should own the state.")
    legacy.add_argument(
        "--directory",
        type=Path,
        default=None,
        help="Where the old files are (default: CN_TRADE_BUDDY_STATE_DIRECTORY).",
    )
    legacy.add_argument(
        "--force", action="store_true", help="Overwrite instruments the user already has."
    )
    args = parser.parse_args()

    settings = get_settings()
    if args.command == "import-legacy":
        directory = args.directory or Path(settings.trade_buddy.state_directory)
        sys.exit(
            asyncio.run(_import(settings, email=args.email, directory=directory, force=args.force))
        )
    asyncio.run(_run(settings))


if __name__ == "__main__":
    run()
