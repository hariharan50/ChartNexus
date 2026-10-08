"""Futures-board capture process.

Fills the archive behind Future Lab's intraday charts, Historical and Replay.
Its own process for the same reason the other workers have one: a loop that
runs all day has no business occupying an API worker. The loop lives in
:mod:`entrypoints.futures_board_runtime`, shared with the API's local
in-process task so the two cannot drift.

``--once`` captures a single frame and exits — for a release job, or for
checking the board is live before trusting what lands in the table.
``--prune`` drops sessions past the retention window and exits.

``--seed DATE`` fabricates a whole session, for a machine with no broker
connected where the archive would otherwise be empty and every intraday page
would look broken rather than unconfigured. It refuses to run in a deployed
environment, refuses a future date, and refuses a day the real worker has
already touched — fabricated frames mixed into real ones cannot be separated
again.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import signal
from datetime import UTC, date, datetime

from chartnexus.bootstrap.container import Container
from chartnexus.bootstrap.logging import configure_logging
from chartnexus.bootstrap.settings import Settings, get_settings
from chartnexus.entrypoints.catalog_runtime import load_registry, registry_kept_current
from chartnexus.entrypoints.futures_board_runtime import (
    capture_once,
    prune_once,
    run_futures_board_loop,
    session_date_of,
)
from chartnexus.infrastructure.catalog import registry
from chartnexus.infrastructure.ingestion.synthetic_board_session import (
    MOCK,
    build_synthetic_board_session,
)
from chartnexus.infrastructure.observability.structured_logging import get_logger
from chartnexus.infrastructure.persistence.postgresql.repositories.market_data.futures_board_snapshot_repository import (
    SqlAlchemyFuturesBoardSnapshotRepository,
)

log = get_logger(__name__)

_LIVE = "live"


class SeedRefusedError(RuntimeError):
    """The seed would have produced rows nobody could later trust."""


async def seed(
    container: Container,
    settings: Settings,
    *,
    session_date: date,
    interval_seconds: int,
    replace: bool,
    force: bool,
) -> int:
    """Fabricate one session of board frames. Refuses rather than risks the archive."""
    if settings.environment.is_deployed and not force:
        raise SeedRefusedError(
            f"refusing to seed fabricated frames in {settings.environment.value}; "
            "these rows are indistinguishable from real captures on read"
        )
    if session_date > session_date_of(datetime.now(UTC)):
        raise SeedRefusedError(f"refusing to seed a future session date: {session_date}")

    rows = registry.current().all()
    if not rows:
        raise SeedRefusedError("the instrument catalog is empty; nothing to seed")

    written = 0
    async with container.database.session() as session:
        repo = SqlAlchemyFuturesBoardSnapshotRepository(session)
        for row in rows:
            if await repo.has_source(row.symbol, session_date, _LIVE) and not force:
                raise SeedRefusedError(
                    f"{row.symbol} already has a real capture on {session_date}; "
                    "seeding would mix fabricated frames into it (--force to override)"
                )
            if replace:
                await repo.delete_session(row.symbol, session_date, MOCK)
            elif await repo.has_source(row.symbol, session_date, MOCK):
                continue

            frames = build_synthetic_board_session(
                symbol=row.symbol,
                session_date=session_date,
                expiry=row.front_expiry.isoformat() if row.front_expiry else None,
                interval_seconds=interval_seconds,
                # Today stops at the current minute — the archive must not claim
                # captures that have not happened yet.
                until=(
                    datetime.now(UTC)
                    if session_date == session_date_of(datetime.now(UTC))
                    else None
                ),
            )
            written += await repo.save_frames(frames)

    log.info(
        "futures_history_seeded",
        session_date=session_date.isoformat(),
        instruments=len(rows),
        frames=written,
    )
    return written


async def _run(settings: Settings, *, once: bool, prune: bool, args: argparse.Namespace) -> None:
    configure_logging(settings)
    container = Container.create(settings, use_db_pool=False)
    # The capture reads the whole catalog, so it has to be warm first.
    await load_registry(container)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    try:
        if args.seed:
            await seed(
                container,
                settings,
                session_date=date.fromisoformat(args.seed),
                interval_seconds=args.interval,
                replace=args.replace,
                force=args.force,
            )
        elif prune:
            await prune_once(container, settings)
        elif once:
            await capture_once(container, settings)
        else:
            async with registry_kept_current(container, settings, stop=stop):
                await run_futures_board_loop(container, settings, stop=stop)
    finally:
        log.info("futures_history_stopping")
        await container.aclose()


def run() -> None:
    """Console-script entrypoint: ``uv run chartnexus-futures-history``."""
    parser = argparse.ArgumentParser(description="Capture the futures board.")
    parser.add_argument(
        "--once", action="store_true", help="Capture one frame and exit instead of looping."
    )
    parser.add_argument(
        "--prune", action="store_true", help="Drop sessions past the retention window and exit."
    )
    parser.add_argument(
        "--seed", metavar="YYYY-MM-DD", help="Fabricate a session for this date and exit."
    )
    parser.add_argument("--interval", type=int, default=60, help="Seconds between seeded frames.")
    parser.add_argument(
        "--replace", action="store_true", help="Drop previously seeded frames first."
    )
    parser.add_argument(
        "--force", action="store_true", help="Override the seed refusals. Rarely right."
    )
    args = parser.parse_args()
    asyncio.run(_run(get_settings(), once=args.once, prune=args.prune, args=args))


if __name__ == "__main__":
    run()
