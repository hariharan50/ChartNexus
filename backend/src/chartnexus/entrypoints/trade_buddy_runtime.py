"""The Trade Buddy watch loop, shared by the standalone process and the API.

Through the session it holds a Fyers socket open and pushes every tick through
the level engine. Two concurrent jobs, because they fail independently: the pump
drains the feed, and a watchdog checks for silence. The watchdog is the half
that matters most — the pump going quiet looks exactly like a quiet market, and
only something outside the tick path can tell the difference.

Outside market hours the loop sleeps to the next open rather than spinning, and
it will not hold a socket open overnight: Fyers tokens expire daily, so a
connection left up is a connection that is dead by morning without saying so.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from chartnexus.bootstrap.container import Container
from chartnexus.bootstrap.settings import Settings
from chartnexus.contexts.trade_buddy.application.watch import WatchEngine
from chartnexus.contexts.trade_buddy.domain.schedule import WatchWindow
from chartnexus.infrastructure.observability.structured_logging import get_logger
from chartnexus.infrastructure.trade_buddy.build_trade_buddy import (
    build_feed,
    build_router,
    build_store,
    build_watch_engine,
    build_window,
)

log = get_logger(__name__)

#: How often the watchdog checks for feed silence. Well under the staleness
#: threshold so the alert is timely rather than rounded up to the poll.
_WATCHDOG_INTERVAL_SECONDS = 15.0

#: Ceiling on the sleep between market-hours checks, so a config change or a
#: clock correction is picked up within the minute rather than at the next open.
_MAX_IDLE_SLEEP_SECONDS = 60.0


async def run_trade_buddy_loop(
    container: Container, settings: Settings, *, stop: asyncio.Event
) -> None:
    trade_buddy = settings.trade_buddy
    if not trade_buddy.enabled:
        log.info("trade_buddy_loop_disabled")
        return

    window = build_window(container)
    symbols = tuple(trade_buddy.symbols)
    log.info(
        "trade_buddy_loop_starting",
        symbols=list(symbols),
        watch_open=trade_buddy.watch_open,
        watch_close=trade_buddy.watch_close,
        holidays=len(window.holidays),
    )

    try:
        while not stop.is_set():
            now = datetime.now(UTC)
            if not window.is_open(now):
                await _sleep(stop, _MAX_IDLE_SLEEP_SECONDS)
                continue
            await _watch_session(container, symbols, window=window, stop=stop)
    except asyncio.CancelledError:
        raise
    finally:
        log.info("trade_buddy_loop_stopped")


async def _watch_session(
    container: Container,
    symbols: tuple[str, ...],
    *,
    window: WatchWindow,
    stop: asyncio.Event,
) -> None:
    """Hold the feed open for as long as the market is, then tear it down."""
    store = build_store(container)
    # One router for every instrument. The WhatsApp ceiling is per account, so
    # three engines each holding their own budget would permit three times the
    # configured send rate.
    router = await build_router(container)

    engines: dict[str, WatchEngine] = {}

    async def marked() -> tuple[str, ...]:
        """The instruments to watch: those with levels marked.

        Derived rather than configured, so adding SENSEX is marking SENSEX
        levels rather than editing an env var and restarting.
        """
        found = []
        for symbol in symbols:
            # Truthy when any level is marked. Staleness is the engine's
            # call, not this one's: an instrument with stale levels is
            # still watched, so it can say so rather than vanish.
            if await store.load_marks(symbol):
                found.append(symbol)
        return tuple(found)

    async def reconcile() -> tuple[str, ...]:
        """Bring engines and the subscription in line with what is marked."""
        wanted = await marked()
        fresh = tuple(s for s in wanted if s not in engines)
        for symbol in fresh:
            engine = await build_watch_engine(container, symbol, router=router)
            await engine.load()
            engines[symbol] = engine
        if fresh:
            # `subscribe` is additive and idempotent, so a newly marked
            # instrument joins mid-session without dropping the socket.
            await feed.subscribe(fresh)
            log.info("trade_buddy_watching", symbols=list(fresh))
        return wanted

    feed = await build_feed(container, router)
    if feed is None:
        # No broker connected. Not an error and not a crash loop: the caller
        # sleeps and tries again, so connecting through the UI mid-session is
        # enough to bring the watch up without touching the process.
        log.info("trade_buddy_no_feed", reason="no_connected_broker")
        await _sleep(stop, _MAX_IDLE_SLEEP_SECONDS)
        return

    if not await reconcile():
        log.info("trade_buddy_nothing_marked", offered=list(symbols))

    async def fan_out() -> None:
        async for tick in feed.ticks():
            if stop.is_set():
                break
            engine = engines.get(tick.symbol)
            if engine is None:
                continue
            try:
                await engine.on_tick(tick)
            except Exception as exc:
                log.error("trade_buddy_tick_failed", symbol=tick.symbol, error=repr(exc))

    tasks = [
        asyncio.create_task(fan_out(), name="trade-buddy-pump"),
        asyncio.create_task(_watchdog(engines, reconcile, stop=stop), name="trade-buddy-watchdog"),
        asyncio.create_task(_until_close(window, stop=stop), name="trade-buddy-session-end"),
    ]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        with contextlib.suppress(Exception):
            await feed.close()


async def _watchdog(
    engines: dict[str, WatchEngine],
    reconcile: Callable[[], Awaitable[tuple[str, ...]]],
    *,
    stop: asyncio.Event,
) -> None:
    """Ask each engine whether it has heard anything lately, and pick up new marks.

    The reconcile runs on the same timer because both are "what changed while
    nothing was arriving" questions, and the watchdog is the one loop
    guaranteed to keep running when the tick path has gone quiet.
    """
    while not stop.is_set():
        await _sleep(stop, _WATCHDOG_INTERVAL_SECONDS)
        if stop.is_set():
            return
        try:
            await reconcile()
        except Exception as exc:
            log.error("trade_buddy_reconcile_failed", error=repr(exc))
        for engine in list(engines.values()):
            try:
                await engine.check_staleness()
            except Exception as exc:
                log.error("trade_buddy_watchdog_failed", error=repr(exc))


async def _until_close(window: WatchWindow, *, stop: asyncio.Event) -> None:
    """Return once the session has closed, so the caller drops the socket.

    The socket is dropped rather than held overnight because Fyers tokens
    expire daily: a connection left up is one that is dead by morning without
    ever saying so.
    """
    while not stop.is_set():
        await _sleep(stop, _MAX_IDLE_SLEEP_SECONDS)
        if not window.is_open(datetime.now(UTC)):
            log.info("trade_buddy_session_closed")
            return


async def _sleep(stop: asyncio.Event, seconds: float) -> None:
    """Sleep, but wake immediately if asked to stop."""
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(stop.wait(), timeout=seconds)
