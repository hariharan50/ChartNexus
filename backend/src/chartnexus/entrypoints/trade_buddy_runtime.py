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
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from chartnexus.bootstrap.container import Container
from chartnexus.bootstrap.settings import Settings
from chartnexus.contexts.trade_buddy.application.ports import AlertSink, FeedHealth
from chartnexus.contexts.trade_buddy.application.watch import WatchEngine
from chartnexus.contexts.trade_buddy.domain.events import AlertEvent
from chartnexus.contexts.trade_buddy.domain.level import MarkSet
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

#: Reported when the feed cannot be built at all — a missing SDK, a bad
#: credential, anything that leaves the watch with nothing to listen to.
FEED_UNAVAILABLE = "feed_unavailable"

#: How long an *unchanged* feed problem stays quiet before it is restated.
#: The retry loop reconsiders the feed every minute, so without this a fault
#: that cannot clear on its own — a missing SDK, a revoked token — delivers one
#: identical message per minute for the whole session. Thirty minutes still
#: says "this is ongoing" a handful of times a day, which is the most a phone
#: can usefully be told about a fact that has not changed.
_HEALTH_REPEAT_SECONDS = 30 * 60.0


@dataclass(slots=True)
class HealthGate:
    """An :class:`AlertSink` that will not say the same thing twice in a row.

    It wraps the real sink and sits *outside* the watch session, because the
    repetition it exists to stop spans sessions: a feed that cannot be built is
    reported, slept on, and reported again by the next pass, each pass with its
    own freshly built router. State held anywhere inside the pass is state that
    is thrown away before the duplicate is sent.

    Only the health path is gated. Level alerts pass straight through — those
    are observations about a price that has moved, so two in a row are two
    facts, not one fact said twice, and the engine already owns their budget.

    The signature is reason *and* detail together: "disconnected, retrying" and
    "disconnected, token refused" are the same reason and different news.
    """

    sink: AlertSink
    repeat_after_seconds: float = _HEALTH_REPEAT_SECONDS
    _last: tuple[str, str] | None = field(default=None, init=False)
    _last_at: datetime | None = field(default=None, init=False)

    async def deliver(self, event: AlertEvent) -> tuple[str, ...]:
        return await self.sink.deliver(event)

    async def deliver_health(self, health: FeedHealth) -> None:
        signature = (health.reason, health.detail)
        if (
            signature == self._last
            and self._last_at is not None
            and (health.at - self._last_at).total_seconds() < self.repeat_after_seconds
        ):
            # Deliberately logged rather than dropped silently: the operator
            # looking at why their phone went quiet needs to see that the fault
            # is still live, even though nothing was sent for it.
            log.info("trade_buddy_health_suppressed", reason=health.reason)
            return
        self._last = signature
        self._last_at = health.at
        await self.sink.deliver_health(health)

    def clear(self) -> None:
        """Forget what was last reported, so the next fault alerts at once.

        Called when the feed comes up. Without it a problem that cleared and
        then returned within the repeat window would be swallowed — which is
        the one case where silence is genuinely misleading.
        """
        if self._last is not None:
            log.info("trade_buddy_health_recovered", reason=self._last[0])
        self._last = None
        self._last_at = None


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

    # Owned by the loop rather than the session: a feed that cannot be built
    # is reported once per pass, and every pass builds a fresh router, so the
    # only place a "have I already said this?" can survive is out here.
    health: HealthGate | None = None

    try:
        while not stop.is_set():
            now = datetime.now(UTC)
            if not window.is_open(now):
                await _sleep(stop, _MAX_IDLE_SLEEP_SECONDS)
                continue
            health = await _watch_session(
                container, symbols, window=window, stop=stop, health=health
            )
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
    health: HealthGate | None = None,
) -> HealthGate:
    """Hold the feed open for as long as the market is, then tear it down.

    Takes and returns the caller's :class:`HealthGate` so that what has already
    been reported outlives this session — the retry loop runs this function
    once a minute while a feed is down, and each run is otherwise amnesiac.
    """
    store = build_store(container)
    # One router for every instrument. The WhatsApp ceiling is per account, so
    # three engines each holding their own budget would permit three times the
    # configured send rate.
    router = await build_router(container)
    # Re-pointed at this pass's router, keeping the memory of what was sent.
    if health is None:
        health = HealthGate(sink=router)
    else:
        health.sink = router

    engines: dict[str, WatchEngine] = {}
    #: The mark set each engine was last loaded with. Held so that replacing
    #: an instrument's levels mid-session is *noticed*: without it an engine
    #: kept whatever it read at startup, and the page's own instruction —
    #: "re-mark them" — could not take effect until the process restarted.
    loaded: dict[str, MarkSet] = {}

    async def reconcile() -> tuple[str, ...]:
        return await reconcile_engines(
            symbols=symbols,
            store=store,
            feed=feed,
            engines=engines,
            loaded=loaded,
            build=lambda symbol: build_watch_engine(container, symbol, router=router),
        )

    try:
        feed = await build_feed(container, health)
    except Exception as exc:
        # Building the feed imports the broker SDK lazily, so a packaging or
        # credential fault surfaces here rather than at startup. Unhandled it
        # escapes the session, ends the watch loop and leaves no trace on the
        # page — the loudest possible failure reported as silence. One health
        # alert and a retry next pass instead.
        log.error("trade_buddy_feed_unavailable", error=repr(exc))
        await health.deliver_health(
            FeedHealth(
                reason=FEED_UNAVAILABLE,
                detail=f"Could not open the market feed: {exc}. No alerts until this clears.",
                at=datetime.now(UTC),
            )
        )
        await _sleep(stop, _MAX_IDLE_SLEEP_SECONDS)
        return health

    if feed is None:
        # No broker connected. Not an error and not a crash loop: the caller
        # sleeps and tries again, so connecting through the UI mid-session is
        # enough to bring the watch up without touching the process.
        log.info("trade_buddy_no_feed", reason="no_connected_broker")
        await _sleep(stop, _MAX_IDLE_SLEEP_SECONDS)
        return health

    # The feed is open. Whatever was last complained about is over, so the
    # next fault — including the same one returning — is news again.
    health.clear()

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
    return health


async def reconcile_engines(
    *,
    symbols: tuple[str, ...],
    store: Any,
    feed: Any,
    engines: dict[str, WatchEngine],
    loaded: dict[str, MarkSet],
    build: Callable[[str], Awaitable[WatchEngine]],
) -> tuple[str, ...]:
    """Bring engines and the subscription in line with what is marked.

    Three things can have changed since the last pass, and each used to need a
    restart:

    **Newly marked.** Build an engine and subscribe. Watching is derived from
    what is marked rather than configured, so adding SENSEX is marking SENSEX
    levels rather than editing an env var.

    **Re-marked.** Reload the engine. This is the one that mattered most:
    levels stamped for an earlier session are not alerted on at all, so an
    engine that started the morning with stale marks went quiet, said
    "re-mark them", and then ignored the re-marking for the rest of the day —
    silence on a real break, which is the failure this feature exists to
    prevent. A changed set of prices had the same problem more quietly: the
    watch carried on against the levels it read at startup.

    **Cleared.** Drop the engine, so a deleted level set stops being watched
    rather than carrying on from memory.

    Staleness itself is the engine's call, not this one's: an instrument with
    stale levels stays watched so that it can say so rather than vanish from
    the strip.

    A module-level function taking its collaborators rather than a closure over
    them, because this is where a missed reload is invisible and it has to be
    reachable from a test without a container or a socket.
    """
    current = {symbol: await store.load_marks(symbol) for symbol in symbols}
    wanted = tuple(symbol for symbol, marks in current.items() if marks)

    for symbol in [s for s in engines if s not in wanted]:
        # The subscription is deliberately left in place. Nothing consumes
        # ticks for an instrument with no engine (`fan_out` skips them), and
        # keeping it means re-marking later costs no socket traffic.
        del engines[symbol]
        loaded.pop(symbol, None)
        log.info("trade_buddy_unwatched", symbol=symbol, reason="levels_cleared")

    fresh: list[str] = []
    for symbol in wanted:
        marks = current[symbol]
        if symbol in engines and loaded.get(symbol) == marks:
            continue

        engine = engines.get(symbol)
        if engine is None:
            engine = await build(symbol)
            engines[symbol] = engine
            fresh.append(symbol)
        # Reloaded in place rather than rebuilt: a fresh object would lose the
        # last-tick reading the staleness watchdog measures silence from, and
        # re-arming that mid-session is a window in which a dead feed raises
        # nothing.
        await engine.load()
        loaded[symbol] = marks
        if symbol not in fresh:
            log.info(
                "trade_buddy_reloaded",
                symbol=symbol,
                levels=len(marks),
                marked_on=marks.marked_on.isoformat() if marks.marked_on else None,
            )

    if fresh:
        # `subscribe` is additive and idempotent, so a newly marked instrument
        # joins mid-session without dropping the socket.
        await feed.subscribe(tuple(fresh))
        log.info("trade_buddy_watching", symbols=fresh)
    return wanted


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
