"""The Trade Buddy watch loop, shared by the standalone process and the API.

**Per-user.** Every user marks their own levels and is alerted on their own
channels. The loop holds **one** market-feed socket (Kite first, then FYERS)
subscribed to the union of the instruments anyone has marked, and pushes each
tick to every user's engine for that instrument. A user is just a key: the
engine, its state row, its router (their Telegram/WhatsApp and their own
WhatsApp allowance) and its feed-health gate are all per user.

Through the session two concurrent jobs run, because they fail independently:
the pump drains the feed, and a watchdog checks for silence. The watchdog is the
half that matters most — the pump going quiet looks exactly like a quiet
market, and only something outside the tick path can tell the difference. It
also re-reads who has marked what, and each user's channels, every 15 seconds,
so marking levels or connecting a bot mid-session needs no restart.

Outside market hours the loop sleeps to the next open rather than spinning, and
it will not hold a socket open overnight: broker tokens expire daily, so a
connection left up is a connection that is dead by morning without saying so.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import Awaitable, Callable, Hashable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from chartnexus.bootstrap.container import Container
from chartnexus.bootstrap.settings import Settings
from chartnexus.contexts.trade_buddy.application.ports import AlertSink, FeedHealth
from chartnexus.contexts.trade_buddy.application.routing import AlertRouter
from chartnexus.contexts.trade_buddy.application.watch import WatchEngine
from chartnexus.contexts.trade_buddy.domain.events import AlertEvent
from chartnexus.contexts.trade_buddy.domain.level import MarkSet
from chartnexus.contexts.trade_buddy.domain.schedule import WatchWindow
from chartnexus.infrastructure.observability.structured_logging import get_logger
from chartnexus.infrastructure.persistence.postgresql.repositories.trade_buddy.watch_state_repository import (
    WatchTarget,
    find_watch_targets,
)
from chartnexus.infrastructure.trade_buddy.atr_cache import SessionAtrCache
from chartnexus.infrastructure.trade_buddy.build_trade_buddy import (
    build_atr_source,
    build_channel_repository,
    build_feed,
    build_notifiers,
    build_router,
    build_store,
    build_watch_engine,
    build_window,
)
from chartnexus.infrastructure.trade_buddy.coalescing_store import CoalescingLevelStore
from chartnexus.shared_kernel.types.identifiers import UserId

log = get_logger(__name__)

#: The server-wide alert credentials Trade Buddy used before it was per-user.
#: Now ignored; named here only so the worker can say so if they are still set.
LEGACY_CHANNEL_ENV = (
    "CN_TRADE_BUDDY_TELEGRAM_BOT_TOKEN",
    "CN_TRADE_BUDDY_TELEGRAM_CHAT_ID",
    "CN_TRADE_BUDDY_WHATSAPP_PHONE",
    "CN_TRADE_BUDDY_WHATSAPP_API_KEY",
)

#: A watched (user, instrument).
WatchKey = tuple[UserId, str]

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


@dataclass(slots=True)
class UserWatch:
    """Everything that is one user's during a watch: their channels, their
    allowance, their health gate and their state stores.

    Lives across sessions (the loop owns it), because the health gate's memory
    of what it already said, and the router's WhatsApp window, must survive the
    once-a-minute retry passes while a feed is down.
    """

    user_id: UserId
    tenant_id: Any
    router: AlertRouter
    health: HealthGate
    #: Which ready channels the router was built from, so a connect, disconnect
    #: or reconnect mid-session is picked up on the next reconcile.
    channels: tuple[object, ...] = ()
    stores: dict[str, CoalescingLevelStore] = field(default_factory=dict)

    def store_for(self, container: Container, symbol: str) -> CoalescingLevelStore:
        store = self.stores.get(symbol)
        if store is None:
            store = CoalescingLevelStore(
                build_store(container, user_id=self.user_id, tenant_id=self.tenant_id),
                interval_seconds=container.settings.trade_buddy.persist_interval_seconds,
            )
            self.stores[symbol] = store
        return store

    async def flush(self) -> None:
        for store in self.stores.values():
            with contextlib.suppress(Exception):
                await store.flush_all()


@dataclass(slots=True)
class FeedHealthFanOut:
    """The feed's health sink: a socket problem is every watching user's news.

    The feed is shared, so "disconnected" is a fact about all of them. Each
    user hears it through their own :class:`HealthGate`, so one user's
    repetition window never silences another's first report.
    """

    users: dict[UserId, UserWatch]
    #: Only users who currently have something watched are told.
    watched: Callable[[], set[UserId]]

    async def deliver(self, event: AlertEvent) -> tuple[str, ...]:  # noqa: ARG002 — port shape
        # Level alerts never come through the feed's sink.
        return ()

    async def deliver_health(self, health: FeedHealth) -> None:
        for user_id in self.watched():
            watch = self.users.get(user_id)
            if watch is None:
                continue
            try:
                await watch.health.deliver_health(health)
            except Exception as exc:
                log.error("trade_buddy_health_failed", user_id=str(user_id), error=repr(exc))

    def clear(self) -> None:
        for watch in self.users.values():
            watch.health.clear()


def warn_legacy_channel_env() -> tuple[str, ...]:
    """Name any old server-wide alert credentials still set. They are ignored."""
    present = tuple(name for name in LEGACY_CHANNEL_ENV if os.environ.get(name))
    if present:
        log.warning(
            "trade_buddy_legacy_channel_env_ignored",
            variables=list(present),
            detail="Alert channels are per user now. Connect them in Trade Buddy → "
            "Alert channels, and remove these from the environment.",
        )
    return present


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
    warn_legacy_channel_env()

    # Owned by the loop rather than the session: what each user's health gate
    # has already said, and each user's WhatsApp window, must survive the
    # retry passes. ATR is cached here too — one fetch per instrument per day
    # however many users watch it.
    users: dict[UserId, UserWatch] = {}
    atr = SessionAtrCache(build_atr_source(container))

    try:
        while not stop.is_set():
            now = datetime.now(UTC)
            if not window.is_open(now):
                await _sleep(stop, _MAX_IDLE_SLEEP_SECONDS)
                continue
            await _watch_session(container, symbols, window=window, stop=stop, users=users, atr=atr)
    except asyncio.CancelledError:
        raise
    finally:
        for watch in users.values():
            await watch.flush()
        log.info("trade_buddy_loop_stopped")


async def _sync_users(
    container: Container,
    targets: Sequence[WatchTarget],
    users: dict[UserId, UserWatch],
) -> None:
    """Make sure every user with marks has a watch, with their current channels.

    A user's router is built from their own ready channels and rebuilt *in
    place* when those change — same object, so the engines already pointing at
    it, and the WhatsApp window it carries, are kept.
    """
    repository = build_channel_repository(container)
    for target in {t.user_id: t for t in targets}.values():
        ready = await repository.find_ready(target.user_id)
        fingerprint = tuple((c.channel, c.id, c.updated_at) for c in ready)
        watch = users.get(target.user_id)
        if watch is None:
            router = await build_router(container, target.user_id)
            users[target.user_id] = UserWatch(
                user_id=target.user_id,
                tenant_id=target.tenant_id,
                router=router,
                health=HealthGate(sink=router),
                channels=fingerprint,
            )
            log.info(
                "trade_buddy_user_watching",
                user_id=str(target.user_id),
                channels=[c.channel.value for c in ready],
            )
        elif watch.channels != fingerprint:
            watch.router.telegram, watch.router.whatsapp = await build_notifiers(
                container, target.user_id
            )
            watch.channels = fingerprint
            log.info(
                "trade_buddy_user_channels_changed",
                user_id=str(target.user_id),
                channels=[c.channel.value for c in ready],
            )


async def _open_feed(
    container: Container,
    symbols: tuple[str, ...],
    *,
    users: dict[UserId, UserWatch],
    health: FeedHealthFanOut,
    stop: asyncio.Event,
) -> Any:
    """The session's shared feed, or ``None`` after reporting and sleeping."""
    # Who to tell if the feed cannot be opened at all: everyone with marks.
    try:
        await _sync_users(container, await find_watch_targets(container.database, symbols), users)
    except Exception as exc:
        log.error("trade_buddy_user_sync_failed", error=repr(exc))
    initially_watched = set(users)
    opening = FeedHealthFanOut(users=users, watched=lambda: initially_watched)

    try:
        feed = await build_feed(container, health)
    except Exception as exc:
        # Building the feed imports the broker SDK lazily, so a packaging or
        # credential fault surfaces here rather than at startup. Unhandled it
        # escapes the session, ends the watch loop and leaves no trace on the
        # page — the loudest possible failure reported as silence. One health
        # alert per watching user and a retry next pass instead.
        log.error("trade_buddy_feed_unavailable", error=repr(exc))
        await opening.deliver_health(
            FeedHealth(
                reason=FEED_UNAVAILABLE,
                detail=f"Could not open the market feed: {exc}. No alerts until this clears.",
                at=datetime.now(UTC),
            )
        )
        await _sleep(stop, _MAX_IDLE_SLEEP_SECONDS)
        return None

    if feed is None:
        # No broker connected. Not an error and not a crash loop: the caller
        # sleeps and tries again, so connecting through the UI mid-session is
        # enough to bring the watch up without touching the process.
        log.info("trade_buddy_no_feed", reason="no_connected_broker")
        await _sleep(stop, _MAX_IDLE_SLEEP_SECONDS)
        return None

    # The feed is open. Whatever was last complained about is over, so the
    # next fault — including the same one returning — is news again.
    health.clear()
    return feed


async def _watch_session(
    container: Container,
    symbols: tuple[str, ...],
    *,
    window: WatchWindow,
    stop: asyncio.Event,
    users: dict[UserId, UserWatch],
    atr: SessionAtrCache,
) -> None:
    """Hold the feed open for as long as the market is, then tear it down."""
    engines: dict[WatchKey, WatchEngine] = {}
    #: The mark set each engine was last loaded with. Held so that replacing
    #: an instrument's levels mid-session is *noticed*: without it an engine
    #: kept whatever it read at startup, and the page's own instruction —
    #: "re-mark them" — could not take effect until the process restarted.
    loaded: dict[WatchKey, MarkSet] = {}
    #: Engines per instrument, rebuilt on every reconcile, so a tick finds its
    #: watchers without scanning every user's.
    by_symbol: dict[str, list[WatchEngine]] = {}
    health = FeedHealthFanOut(users=users, watched=lambda: {key[0] for key in engines})

    async def reconcile() -> tuple[WatchKey, ...]:
        targets = await find_watch_targets(container.database, symbols)
        await _sync_users(container, targets, users)

        def store_of(key: WatchKey) -> CoalescingLevelStore:
            return users[key[0]].store_for(container, key[1])

        async def build(key: WatchKey) -> WatchEngine:
            watch = users[key[0]]
            return await build_watch_engine(
                container, key[1], store=store_of(key), router=watch.router, atr_source=atr
            )

        wanted = await reconcile_engines(
            targets=tuple((t.user_id, t.symbol) for t in targets),
            load_marks=lambda key: store_of(key).load_marks(key[1]),
            symbol_of=lambda key: key[1],
            feed=feed,
            engines=engines,
            loaded=loaded,
            build=build,
        )
        by_symbol.clear()
        for (_, symbol), engine in engines.items():
            by_symbol.setdefault(symbol, []).append(engine)
        return wanted

    feed = await _open_feed(container, symbols, users=users, health=health, stop=stop)
    if feed is None:
        return

    if not await reconcile():
        log.info("trade_buddy_nothing_marked", offered=list(symbols))

    async def on_tick(engine: WatchEngine, tick: Any) -> None:
        try:
            await engine.on_tick(tick)
        except Exception as exc:
            log.error("trade_buddy_tick_failed", symbol=tick.symbol, error=repr(exc))

    async def fan_out() -> None:
        async for tick in feed.ticks():
            if stop.is_set():
                break
            watchers = by_symbol.get(tick.symbol)
            if not watchers:
                continue
            # Concurrently: one user's slow Telegram send must not delay the
            # next user's tick — a break's hold is measured in seconds.
            await asyncio.gather(*(on_tick(engine, tick) for engine in watchers))

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
        for watch in users.values():
            await watch.flush()


async def reconcile_engines[K: Hashable](
    *,
    targets: Sequence[K],
    load_marks: Callable[[K], Awaitable[MarkSet]],
    symbol_of: Callable[[K], str],
    feed: Any,
    engines: dict[K, WatchEngine],
    loaded: dict[K, MarkSet],
    build: Callable[[K], Awaitable[WatchEngine]],
) -> tuple[K, ...]:
    """Bring engines and the subscription in line with what is marked.

    Generic over the key: a ``(user, instrument)`` pair in the per-user loop,
    which is what lets two people watch NIFTY with their own levels from one
    subscription. ``symbol_of`` says which instrument a key subscribes to.

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
    current = {key: await load_marks(key) for key in dict.fromkeys(targets)}
    wanted = tuple(key for key, marks in current.items() if marks)

    for key in [k for k in engines if k not in wanted]:
        # The subscription is deliberately left in place. Nothing consumes
        # ticks for an instrument with no engine (`fan_out` skips them), and
        # keeping it means re-marking later costs no socket traffic.
        del engines[key]
        loaded.pop(key, None)
        log.info("trade_buddy_unwatched", key=str(key), reason="levels_cleared")

    fresh: list[K] = []
    for key in wanted:
        marks = current[key]
        if key in engines and loaded.get(key) == marks:
            continue

        engine = engines.get(key)
        if engine is None:
            engine = await build(key)
            engines[key] = engine
            fresh.append(key)
        # Reloaded in place rather than rebuilt: a fresh object would lose the
        # last-tick reading the staleness watchdog measures silence from, and
        # re-arming that mid-session is a window in which a dead feed raises
        # nothing.
        await engine.load()
        loaded[key] = marks
        if key not in fresh:
            log.info(
                "trade_buddy_reloaded",
                key=str(key),
                levels=len(marks),
                marked_on=marks.marked_on.isoformat() if marks.marked_on else None,
            )

    # One subscription per instrument, however many users watch it.
    symbols = tuple(dict.fromkeys(symbol_of(key) for key in fresh))
    if symbols:
        # `subscribe` is additive and idempotent, so a newly marked instrument
        # joins mid-session without dropping the socket.
        await feed.subscribe(symbols)
        log.info("trade_buddy_watching", symbols=list(symbols), engines=len(fresh))
    return wanted


async def _watchdog(
    engines: dict[WatchKey, WatchEngine],
    reconcile: Callable[[], Awaitable[tuple[WatchKey, ...]]],
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
