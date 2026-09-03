"""Option-chain archive maintenance: ``seed`` and ``prune``.

Two operator commands over the snapshot archive the Open Interest tool reads.

``seed`` fabricates a full trading session so the intraday timeline can be
scrubbed on a developer machine — at 07:41, on a Sunday, with no broker
connected. Without it the tool has at most two data points and the time slider
has nothing to slide over.

``prune`` applies the retention window, and is the same use case the ingest
worker runs once a day.

Seeding *today* stops at the current minute, exactly where a real ingest worker
would be. Seeding a past date writes the whole 09:15-15:30 session. Re-running
later in the day with ``--replace`` reproduces the earlier frames unchanged and
adds the ones since, so the archive only ever grows forwards.

Seeding writes rows that are *indistinguishable from real captures* to every
reader — only the ``source`` column tells them apart, and nothing filters on it.
That is acceptable on a laptop and unacceptable anywhere shared, so the command
guards itself four ways: it refuses a deployed environment, refuses to touch a
symbol-day that already holds a live capture, refuses a future session date, and
only ever deletes its own ``mock`` rows.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, date, datetime, timedelta, timezone

from marketcompass.bootstrap.container import Container
from marketcompass.bootstrap.logging import configure_logging
from marketcompass.bootstrap.settings import Settings, get_settings
from marketcompass.contexts.market_ingestion.application.retention import (
    PruneSnapshots,
    RetentionError,
)
from marketcompass.contexts.market_ingestion.application.rollup import RollupDailyIv
from marketcompass.infrastructure.ingestion.daily_iv_rollup import (
    SqlAlchemyDailyIvWriter,
    SqlAlchemySessionIvSource,
)
from marketcompass.infrastructure.ingestion.synthetic_session import build_synthetic_session
from marketcompass.infrastructure.observability.structured_logging import get_logger
from marketcompass.infrastructure.persistence.postgresql.repositories.market_data.option_chain_snapshot_repository import (
    SqlAlchemyOptionChainSnapshotRepository,
)

log = get_logger(__name__)

_IST = timezone(timedelta(hours=5, minutes=30))
_MOCK = "mock"
_LIVE = "live"
# Snapshots per flush. Three symbols x 126 frames x ~82 legs is ~31k inserts;
# flushing per snapshot is needlessly chatty and never flushing holds it all.
_FLUSH_EVERY = 20


class SeedRefusedError(RuntimeError):
    """A guard said no. The message is written to be read by a human."""


def _today_ist() -> date:
    return datetime.now(_IST).date()


# -- seed -------------------------------------------------------------------


async def _seed(
    container: Container,
    settings: Settings,
    *,
    symbols: tuple[str, ...],
    session_date: date,
    interval_seconds: int,
    replace: bool,
    force: bool,
) -> int:
    if settings.environment.is_deployed and not force:
        raise SeedRefusedError(
            f"refusing to seed fabricated open interest in {settings.environment.value}; "
            "these rows are indistinguishable from real captures on read"
        )
    if session_date > _today_ist():
        raise SeedRefusedError(f"refusing to seed a future session date: {session_date}")

    written = 0
    async with container.database.session() as session:
        repo = SqlAlchemyOptionChainSnapshotRepository(session)

        for symbol in symbols:
            if await repo.has_source(symbol, session_date, _LIVE) and not force:
                raise SeedRefusedError(
                    f"{symbol} already has a real capture on {session_date}; "
                    "seeding would mix fabricated interest into it (--force to override)"
                )

            if replace:
                removed = await repo.delete_session(symbol, session_date, _MOCK)
                if removed:
                    log.info("oi_seed_replaced", symbol=symbol, snapshots=removed)
            elif await repo.has_source(symbol, session_date, _MOCK):
                log.info("oi_seed_skipped", symbol=symbol, reason="already_seeded")
                continue

            snapshots = build_synthetic_session(
                symbol=symbol,
                session_date=session_date,
                interval_seconds=interval_seconds,
                # Today stops at the current minute — the archive must not claim
                # captures that have not happened yet. A past date gets the whole
                # session, because for that day they all did.
                until=datetime.now(UTC) if session_date == _today_ist() else None,
            )
            for index, snapshot in enumerate(snapshots, start=1):
                await repo.save(snapshot)
                if index % _FLUSH_EVERY == 0:
                    session.expunge_all()

            written += len(snapshots)
            log.info("oi_seed_written", symbol=symbol, snapshots=len(snapshots))

    return written


# -- prune ------------------------------------------------------------------


async def _prune(container: Container, *, retention_days: int) -> int:
    async with container.database.session() as session:
        use_case = PruneSnapshots(
            pruner=SqlAlchemyOptionChainSnapshotRepository(session),
            clock=_SystemClock(),
            retention_days=retention_days,
        )
        result = await use_case()
    log.info("oi_prune", cutoff=result.cutoff.isoformat(), deleted=result.deleted)
    return result.deleted


async def _rollup(container: Container, *, symbols: tuple[str, ...], lookback_days: int) -> int:
    async with container.database.session() as session:
        use_case = RollupDailyIv(
            source=SqlAlchemySessionIvSource(session),
            writer=SqlAlchemyDailyIvWriter(session),
            clock=_SystemClock(),
        )
        result = await use_case(list(symbols), lookback_days=lookback_days)
    log.info("oi_iv_rollup", written=result.written, skipped=result.skipped)
    return result.written


class _SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


# -- cli --------------------------------------------------------------------


def _parser(default_retention: int) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="marketcompass-oi", description="Option-chain archive maintenance."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed", help="fabricate a full trading session of snapshots")
    seed.add_argument("--symbol", action="append", dest="symbols", metavar="SYMBOL")
    seed.add_argument("--date", dest="session_date", metavar="YYYY-MM-DD")
    seed.add_argument("--interval", dest="interval_seconds", type=int, default=180)
    seed.add_argument(
        "--replace",
        action="store_true",
        help="delete this command's own previous rows for the day first (idempotent re-seed)",
    )
    seed.add_argument(
        "--force",
        action="store_true",
        help="override the environment and live-capture guards. Rarely what you want.",
    )
    seed.set_defaults(symbols=None)

    prune = sub.add_parser("prune", help="apply the retention window")
    prune.add_argument("--days", dest="retention_days", type=int, default=default_retention)

    rollup = sub.add_parser(
        "rollup-iv",
        help="persist one closing IV reading per archived session (idempotent)",
    )
    rollup.add_argument("--symbol", action="append", dest="symbols", metavar="SYMBOL")
    rollup.add_argument("--days", dest="lookback_days", type=int, default=default_retention)
    rollup.set_defaults(symbols=None)

    return parser


async def _main(argv: list[str]) -> int:
    settings = get_settings()
    configure_logging(settings)
    args = _parser(settings.market.snapshot_retention_days).parse_args(argv)

    container = Container.create(settings, use_db_pool=False)
    try:
        if args.command == "seed":
            symbols = tuple(args.symbols) if args.symbols else tuple(settings.market.ingest_symbols)
            session_date = (
                date.fromisoformat(args.session_date) if args.session_date else _today_ist()
            )
            written = await _seed(
                container,
                settings,
                symbols=symbols,
                session_date=session_date,
                interval_seconds=args.interval_seconds,
                replace=args.replace,
                force=args.force,
            )
            print(f"seeded {written} snapshots for {session_date} ({', '.join(symbols)})")
            if written == 0 and session_date == _today_ist():
                print(
                    "note: today's session has not opened yet (09:15 IST). "
                    "Seed a past date to get a full day to scrub over.",
                    file=sys.stderr,
                )
        elif args.command == "rollup-iv":
            symbols = tuple(args.symbols) if args.symbols else tuple(settings.market.ingest_symbols)
            written = await _rollup(container, symbols=symbols, lookback_days=args.lookback_days)
            print(f"rolled up {written} sessions of IV ({', '.join(symbols)})")
            if written == 0:
                print(
                    "note: nothing archived in the window, or no capture quoted IV "
                    "at the money. Seed a session first.",
                    file=sys.stderr,
                )
        else:
            deleted = await _prune(container, retention_days=args.retention_days)
            print(f"pruned {deleted} snapshots")
    except (SeedRefusedError, RetentionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        await container.aclose()
    return 0


def run() -> None:
    """Console-script entrypoint: ``uv run marketcompass-oi seed``."""
    raise SystemExit(asyncio.run(_main(sys.argv[1:])))


if __name__ == "__main__":
    run()
