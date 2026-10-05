"""The futures-board capture, shared by every caller that runs it.

Lives in entrypoints — not infrastructure — because it wires a ``Container``,
which adapters are forbidden to import. The same loop runs from the standalone
``chartnexus-futures-history`` process and, in local development only, as a
background task in the API's lifespan.

**Why a worker at all.** The broker only ever answers "now"; it will not say
what a contract was priced at an hour ago. Every intraday reading Future Lab
wants — the Price vs OI line, the dashboard's comparison windows, Historical
and Replay — needs an archive the application keeps itself. This is that
archive for futures, mirroring what the ingest worker already does for option
chains.

**Why it is separate from the open-interest sweep.** Price comes from the quote
endpoint, which takes fifty symbols per request: the whole universe costs five
calls, so capturing every minute is about 1,900 requests a day. Open interest
comes from the depth endpoint, which takes one contract per request, so its
sweep costs 219 and runs on five minutes. Forcing them onto one cadence would
either waste the price resolution or blow the quota. Each frame here therefore
carries a fresh price and whatever open interest the last sweep left in the
cache — a staircase against a smooth line, which is how open interest actually
moves.

**Live frames only.** When no broker is connected the board degrades to
generated numbers, and those must never enter the archive: a stored row outlives
the process that wrote it, and a mislabelled one cannot be detected later. The
seeder is the only writer permitted to produce ``mock`` frames, and it says so
in the column.

**Session hours only.** The broker keeps answering after the bell — it returns
the last traded price all evening — so a worker that simply ran would archive
hours of flat frames that no trading produced, and every chart would trail off
into a straight line to midnight. The calendar gate is what stops that, exactly
as it does for the option-chain ingest.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, date, datetime, timedelta, timezone

from chartnexus.bootstrap.container import Container
from chartnexus.bootstrap.settings import Settings
from chartnexus.contexts.broker_connections.domain.value_objects import BrokerName
from chartnexus.contexts.futures_analytics.application.ports import (
    BoardFrame,
    BoardSnapshot,
)
from chartnexus.infrastructure.brokers.fyers.quota_manager import QuotaPolicy
from chartnexus.infrastructure.brokers.mock.provider import MockMarketDataProvider
from chartnexus.infrastructure.brokers.provider_resolver import TenantProviderResolver
from chartnexus.infrastructure.futures.board_source import CatalogFuturesBoardSource
from chartnexus.infrastructure.futures.oi_cache import RedisOpenInterestCache
from chartnexus.infrastructure.observability.structured_logging import get_logger
from chartnexus.infrastructure.persistence.postgresql.repositories.integration.broker_connection_repository import (
    SqlAlchemyBrokerConnectionRepository,
)
from chartnexus.infrastructure.persistence.postgresql.repositories.market_data.futures_board_snapshot_repository import (
    SqlAlchemyFuturesBoardSnapshotRepository,
)
from chartnexus.infrastructure.time.clock import SystemClock
from chartnexus.infrastructure.time.market_calendar import ExchangeCalendar

log = get_logger(__name__)

#: Exchange-local time. Matches ``ingest_runtime``'s own constant rather than
#: reaching for a shared one that does not exist.
_IST = timezone(timedelta(hours=5, minutes=30))

#: Provenance the archive will accept from this worker. Anything else is
#: dropped rather than stored under a label that would later be believed.
_LIVE = "live"


async def capture_once(container: Container, settings: Settings) -> int:
    """One frame per contract. Never propagates — the loop must survive it.

    Returns how many frames were stored, so a caller can tell a quiet capture
    from a broken one.
    """
    try:
        return await _capture(container, settings)
    except Exception as exc:
        log.error("futures_board_capture_failed", error=repr(exc))
        return 0


async def _capture(container: Container, settings: Settings) -> int:
    now = datetime.now(UTC)
    if not _calendar(settings).is_open(now):
        # Not a failure: the bell has rung, or it is a weekend. Logged at debug
        # so an overnight process does not fill the log with one line a minute.
        log.debug("futures_board_capture_skipped", reason="market_closed")
        return 0

    async with container.database.session() as session:
        connections = SqlAlchemyBrokerConnectionRepository(session, container.token_cipher)
        # The board is a fact about the market, not about a tenant, so any
        # working connection can read it and one capture serves everybody.
        connection = await connections.find_any_active(BrokerName.FYERS)
        if connection is None:
            log.info("futures_board_capture_skipped", reason="no_connected_broker")
            return 0

        source = CatalogFuturesBoardSource(
            _resolver(container, settings, connections),
            MockMarketDataProvider(SystemClock()),
            oi_cache=RedisOpenInterestCache(
                container.redis, ttl_seconds=settings.futures_oi.ttl_seconds
            ),
        )
        snapshot = await source.read(connection.tenant_id)

        captured_at = _bucket(now, settings.futures_history.interval_seconds)
        frames = frames_from(snapshot, captured_at)
        if not frames:
            log.info("futures_board_capture_skipped", reason=_skip_reason(snapshot))
            return 0

        # ``session()`` commits on a clean exit, so the write lands with it.
        stored = await SqlAlchemyFuturesBoardSnapshotRepository(session).save_frames(frames)

    log.info(
        "futures_board_captured",
        stored=stored,
        priced=len(frames),
        with_open_interest=sum(1 for frame in frames if frame.open_interest is not None),
        at=captured_at.isoformat(),
    )
    return stored


def frames_from(snapshot: BoardSnapshot, captured_at: datetime) -> list[BoardFrame]:
    """The archivable frames in one board read.

    Empty for a board that degraded to generated numbers. That check lives here
    rather than at the call site because it is the rule the whole archive rests
    on: a stored row outlives the process that wrote it, and nothing
    downstream can tell a mislabelled one from a real one.

    Contracts the board could not price are dropped rather than stored at zero,
    for the same reason the board itself omits them.
    """
    if snapshot.source != _LIVE:
        return []
    return [
        BoardFrame(
            symbol=reading.symbol,
            session_date=session_date_of(captured_at),
            captured_at=captured_at,
            price=reading.price,
            open_interest=reading.open_interest,
            volume=reading.volume,
            expiry=reading.expiry,
            source=_LIVE,
        )
        for reading in snapshot.readings
        if reading.price > 0
    ]


def _skip_reason(snapshot: BoardSnapshot) -> str:
    return "board_not_live" if snapshot.source != _LIVE else "nothing_priced"


def session_date_of(moment: datetime) -> date:
    """The IST trading date a UTC instant belongs to.

    Stored explicitly so day-scoped reads never have to reason about the
    five-and-a-half-hour offset — the same reason the option-chain archive
    keeps it.
    """
    return moment.astimezone(_IST).date()


def _bucket(moment: datetime, interval_seconds: int) -> datetime:
    """Floor an instant onto the capture cadence.

    Frames land on interval boundaries so that a restarted worker re-capturing
    the same interval collides with what is already stored and is discarded,
    rather than crowding the series with a near-duplicate a few seconds off.
    """
    step = max(interval_seconds, 1)
    seconds = int(moment.timestamp()) // step * step
    return datetime.fromtimestamp(seconds, tz=UTC)


def _calendar(settings: Settings) -> ExchangeCalendar:
    """The same calendar the option-chain ingest gates on.

    Its close carries a few minutes' grace past the bell so the final ticks of
    a session are not lost to a worker that woke up a moment late. Display
    clips to the bell itself — that is the series' job, not this one's.
    """
    return ExchangeCalendar(
        timezone=settings.market.timezone,
        session_open=settings.market.session_open,
        session_close=settings.market.session_close,
    )


def _resolver(
    container: Container,
    settings: Settings,
    connections: SqlAlchemyBrokerConnectionRepository,
) -> TenantProviderResolver:
    return TenantProviderResolver(
        connections=connections,
        http=container.http,
        redis=container.redis,
        rest_base_url=settings.broker.rest_base_url,
        quota=QuotaPolicy(
            requests_per_second=settings.broker.quota_requests_per_second,
            requests_per_day=settings.broker.quota_requests_per_day,
        ),
        request_timeout_seconds=settings.broker.request_timeout_seconds,
        circuit_breaker_failure_threshold=settings.broker.circuit_breaker_failure_threshold,
        circuit_breaker_reset_seconds=settings.broker.circuit_breaker_reset_seconds,
    )


async def prune_once(container: Container, settings: Settings) -> int:
    """Drop sessions past the retention window. Never propagates."""
    cutoff = session_date_of(datetime.now(UTC)) - timedelta(
        days=settings.futures_history.retention_days
    )
    try:
        async with container.database.session() as session:
            dropped = await SqlAlchemyFuturesBoardSnapshotRepository(
                session
            ).delete_sessions_before(cutoff)
    except Exception as exc:
        log.error("futures_board_prune_failed", error=repr(exc))
        return 0

    if dropped:
        log.info("futures_board_pruned", cutoff=cutoff.isoformat(), deleted=dropped)
    return dropped


async def run_futures_board_loop(
    container: Container, settings: Settings, *, stop: asyncio.Event
) -> None:
    history = settings.futures_history
    if not history.enabled:
        log.info("futures_board_loop_disabled")
        return

    log.info("futures_board_loop_starting", interval_seconds=history.interval_seconds)
    pruned_on: date | None = None
    try:
        while not stop.is_set():
            await capture_once(container, settings)
            # Once per trading date, not once per capture: the prune is a whole
            # table scan and nothing changes between two frames a minute apart.
            today = session_date_of(datetime.now(UTC))
            if pruned_on != today:
                await prune_once(container, settings)
                pruned_on = today
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=history.interval_seconds)
    finally:
        log.info("futures_board_loop_stopping")


__all__ = [
    "capture_once",
    "frames_from",
    "prune_once",
    "run_futures_board_loop",
    "session_date_of",
]
