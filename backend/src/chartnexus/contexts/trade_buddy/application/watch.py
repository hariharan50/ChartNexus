"""The engine: ticks in, alerts out.

Holds one :class:`LevelWatcher` per marked level and does four things the pure
domain cannot: it decides when a session has started (and therefore when a gap
has happened), it applies the budget, it persists state, and it notices when the
feed has gone quiet.

The gap check deserves its word. The state machine is driven by *transitions*,
and a level the market opened beyond has no transition to make — price was never
near it, so ``IDLE`` is where it would stay for the entire session while the
level sat silently broken. The first tick of a session is therefore handled
specially: any level already beyond its buffer is reported as gapped through,
once, before the normal path ever sees a price.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from chartnexus.contexts.trade_buddy.application.ports import (
    AlertSink,
    AtrSource,
    Clock,
    FeedHealth,
    LevelStore,
    RuntimeState,
    Tick,
)
from chartnexus.contexts.trade_buddy.domain.bands import (
    AlertOverrides,
    BandPolicy,
    ResolvedBands,
    resolve_bands,
)
from chartnexus.contexts.trade_buddy.domain.budget import LevelBudget, WhatsAppBudget
from chartnexus.contexts.trade_buddy.domain.events import AlertEvent
from chartnexus.contexts.trade_buddy.domain.level import LevelBands
from chartnexus.contexts.trade_buddy.domain.schedule import WatchWindow
from chartnexus.contexts.trade_buddy.domain.state import LevelState, LevelWatcher

#: Reasons reported through ``FeedHealth``. Strings rather than an enum because
#: they are read by humans in a message, never branched on.
STALE = "feed_stale"
DISCONNECTED = "feed_disconnected"
CREDENTIAL_REJECTED = "token_rejected"
STALE_LEVELS = "levels_stale"


@dataclass(slots=True)
class WatchEngine:
    """One instrument's live level watch."""

    symbol: str
    policy: BandPolicy
    window: WatchWindow
    store: LevelStore
    sink: AlertSink
    clock: Clock
    budget: LevelBudget = field(default_factory=LevelBudget)
    #: Seconds without a tick, during market hours, before the feed is suspect.
    stale_after_seconds: float = 90.0
    #: The WhatsApp send window, when the sink owns one. Held here only so it
    #: can be persisted and restored with the rest of the runtime state — the
    #: engine never reads it, because the channel policy is the router's job.
    #: A restart must not hand the process a fresh allowance the provider is
    #: still counting against us.
    whatsapp_budget: WhatsAppBudget | None = None
    #: Supplies the ATR the bands scale from. `None` means point bands,
    #: which is the degraded mode the page reports rather than hides.
    atr_source: AtrSource | None = None
    overrides: AlertOverrides = field(default_factory=AlertOverrides)

    _watchers: list[LevelWatcher] = field(default_factory=list)
    _session: date | None = None
    _last_tick_monotonic: float | None = None
    #: Wall-clock time of the last tick. Distinct from the monotonic reading:
    #: that one measures silence, this one is what the status route shows.
    _last_tick_at: datetime | None = None
    _last_price: float | None = None
    _resolved: ResolvedBands | None = None
    #: The session the marked levels were marked for. `None` when nothing
    #: is marked, or when they predate the stamp being recorded.
    _marked_on: date | None = None
    #: One stale-levels notice per session, not one per tick.
    _warned_stale_for: date | None = None
    _atr: float | None = None

    # -- lifecycle ----------------------------------------------------------

    async def load(self) -> None:
        """Resume saved watcher states, or build fresh ones from the marks.

        Resuming matters more than it looks: without it, a restart at 14:00
        re-reports every level price has already passed today, which trains the
        reader to ignore the channel.
        """
        runtime = await self.store.load_runtime(self.symbol)
        self._last_tick_at = runtime.last_tick_at
        self._last_price = runtime.last_price
        # Resuming the session is what keeps a mid-session restart from
        # re-running gap settlement over ground already covered.
        self._session = runtime.session
        if runtime.level_budget:
            # Without this a restart hands every level a fresh cap and an
            # expired cooldown, and the afternoon replays the morning's alerts.
            self.budget.restore(runtime.level_budget)
        if runtime.whatsapp_sends and self.whatsapp_budget is not None:
            self.whatsapp_budget.reload(list(runtime.whatsapp_sends))

        self.overrides = await self.store.load_overrides(self.symbol)
        # The throttles are per-instrument too, so a day spent in one index
        # can be noisier there without loosening the others.
        if self.overrides.cooldown_minutes is not None:
            self.budget.cooldown = timedelta(minutes=self.overrides.cooldown_minutes)
        if self.overrides.daily_alert_cap is not None:
            self.budget.daily_cap = self.overrides.daily_alert_cap
        await self._refresh_bands(cached=runtime.atr)

        marked = await self.store.load_marks(self.symbol)
        self._marked_on = marked.marked_on

        resumed = await self.store.load_watchers(self.symbol)
        if resumed:
            self._watchers = list(resumed)
        else:
            self._watchers = [
                LevelWatcher(symbol=self.symbol, mark=mark, bands=self.bands)
                for mark in marked.marks
            ]
        # Watchers restored from disk carry whatever bands the store rebuilt
        # them with; the resolved set is the authority.
        self._apply_bands()

    @property
    def bands(self) -> LevelBands:
        """The bands currently in force for this instrument."""
        return self.resolved.bands

    @property
    def resolved(self) -> ResolvedBands:
        """Bands plus the story of where they came from, for the status route."""
        if self._resolved is None:
            self._resolved = resolve_bands(
                atr=None,
                multiples=self.policy.multiples,
                fallback=self.policy.fallback,
                overrides=self.overrides.bands,
                confirm_hold_seconds=self.policy.confirm_hold_seconds,
            )
        return self._resolved

    async def _refresh_bands(self, *, cached: float | None = None) -> None:
        """Re-scale the bands for this instrument.

        ATR is a daily figure, so this runs once at load and again when the
        session rolls — not per tick. A cached value from the store is used in
        preference to a fetch, so a restart does not silently drop to point
        bands just because the provider was slow at that moment.
        """
        value = cached
        if value is None and self.atr_source is not None:
            value = await self.atr_source.atr(self.symbol, period=self.policy.atr_period)

        self._resolved = resolve_bands(
            atr=value,
            multiples=self.policy.multiples,
            fallback=self.policy.fallback,
            overrides=self.overrides.bands,
            confirm_hold_seconds=self.policy.confirm_hold_seconds,
        )
        self._atr = self._resolved.atr
        self._apply_bands()

    def _apply_bands(self) -> None:
        """Push the resolved bands onto every watcher.

        `LevelWatcher.bands` is read on every comparison, so a stale set on a
        resumed watcher would measure today's prices with yesterday's ruler.
        """
        for watcher in self._watchers:
            watcher.bands = self.bands

    @property
    def watchers(self) -> tuple[LevelWatcher, ...]:
        """Live state, for the status route."""
        return tuple(self._watchers)

    async def _save_runtime(self) -> None:
        """Persist the counters and last-tick time for the status route.

        Written every tick, beside the watcher states, because the API answers
        ``GET /state`` from a different process and has no other way to know
        when a tick last arrived or how much budget is left.
        """
        await self.store.save_runtime(
            self.symbol,
            RuntimeState(
                last_tick_at=self._last_tick_at,
                last_price=self._last_price,
                atr=self._atr,
                session=self._session,
                level_budget=self.budget.snapshot(),
                whatsapp_sends=(
                    tuple(self.whatsapp_budget.snapshot())
                    if self.whatsapp_budget is not None
                    else ()
                ),
            ),
        )

    # -- the tick path ------------------------------------------------------

    async def on_tick(self, tick: Tick) -> list[AlertEvent]:
        """Feed one tick through every level. Returns what was delivered."""
        self._last_tick_monotonic = self.clock.monotonic()
        self._last_tick_at = tick.at
        self._last_price = tick.price

        if not self.window.is_open(tick.at):
            return []

        session = self.window.session_date(tick.at)

        # Levels are a daily artefact. Comparing live price against Friday's
        # numbers and alerting on them is the worst outcome this module has —
        # worse than silence, which is at least visibly wrong. So a stale set
        # is watched by nobody until it is re-marked, and the reader is told
        # once rather than left to wonder why it has gone quiet.
        if self._watchers and not self._is_current(session):
            await self._warn_stale(session, tick)
            return []

        if session != self._session:
            # First tick of a new session. Two things happen, in this order.
            self._session = session
            # A new session means a new ATR. Re-scale before any comparison,
            # or the first day's ruler measures every day after it.
            await self._refresh_bands()
            self._reset_observations()
            # Then settle gaps, so a level the market opened beyond is reported
            # rather than silently skipped for the whole day.
            events = self._settle_gaps(tick)
        else:
            events = []

        elapsed = self.clock.monotonic()
        for watcher in self._watchers:
            # A level just reported as gapped is safe to observe on this same
            # tick: it is now BROKEN and far from its reclaim line, so the
            # broken branch returns nothing. No special case needed — and a
            # guard here would have to be unwound again the moment price came
            # back, which is exactly when reclaim detection must still work.
            events.extend(watcher.observe(tick.price, elapsed, tick.at))

        delivered = [event for event in events if self.budget.allow(event)]
        for event in delivered:
            await self.sink.deliver(event)

        await self.store.save_watchers(self.symbol, tuple(self._watchers))
        await self._save_runtime()
        return delivered

    def _is_current(self, session: date) -> bool:
        """Whether the marked levels belong to the session being watched.

        Marks with no stamp at all count as stale: assuming a set is today's
        when nothing says so is exactly the mistake this guards against.
        """
        return self._marked_on is not None and self._marked_on == session

    async def _warn_stale(self, session: date, tick: Tick) -> None:
        """Say once per session that the levels are out of date.

        Through the feed-health path rather than the level-alert path: this is
        a statement about the watch itself, not about a price, and it must not
        be throttled by a budget meant for observations.
        """
        if self._warned_stale_for == session:
            return
        self._warned_stale_for = session

        marked = self._marked_on.isoformat() if self._marked_on else "an unknown session"
        await self.sink.deliver_health(
            FeedHealth(
                reason=STALE_LEVELS,
                detail=(
                    f"{self.symbol}: levels are from {marked}, not today. "
                    f"No alerts will be sent for {self.symbol} until they are re-marked."
                ),
                at=tick.at,
            )
        )

    def _reset_observations(self) -> None:
        """Clear within-session memory at the start of a new session.

        ``APPROACHING`` and ``TOUCHED`` mean "price is here and I have already
        said so" — a statement about today. Carried into tomorrow they go stale
        in the worst direction: a level left ``TOUCHED`` at Monday's close would
        never report a touch again, because the machine suppresses repeats.

        ``BROKEN`` is deliberately *not* reset. That one is a durable fact about
        the level, not about the session: a resistance broken on Monday is still
        acting as support on Tuesday, and it stays flipped until price reclaims
        it. Any pending break is dropped, since its hold was measured against a
        monotonic origin that no longer means anything.
        """
        for watcher in self._watchers:
            if watcher.broken:
                continue
            watcher.state = LevelState.IDLE
            watcher.pending_since = None
            watcher.break_sign = None

    def _settle_gaps(self, tick: Tick) -> list[AlertEvent]:
        """Report every level the session opened beyond, once."""
        gapped: list[AlertEvent] = []
        for watcher in self._watchers:
            if watcher.broken:
                continue
            sign = watcher.role.break_sign
            threshold = watcher.mark.break_threshold(watcher.bands, sign)
            beyond = tick.price > threshold if sign > 0 else tick.price < threshold
            if beyond:
                gapped.append(watcher.gap_through(tick.price, tick.at))
        return gapped

    # -- feed health --------------------------------------------------------

    async def check_staleness(self) -> None:
        """Alert if no tick has arrived for too long during market hours.

        Called on a timer by the runtime, not by the tick path — the whole point
        is to fire when the tick path has stopped running.
        """
        now = self.clock.now()
        if not self.window.is_open(now):
            return
        last = self._last_tick_monotonic
        if last is None:
            return
        silence = self.clock.monotonic() - last
        if silence < self.stale_after_seconds:
            return
        self._last_tick_monotonic = self.clock.monotonic()  # re-arm, don't spam
        await self.sink.deliver_health(
            FeedHealth(
                reason=STALE,
                detail=f"No tick for {silence:.0f}s on {self.symbol} during market hours.",
                at=now,
            )
        )

    async def report_disconnect(self, detail: str, *, reason: str = DISCONNECTED) -> None:
        """Called by the feed adapter when the socket drops or the token is refused."""
        await self.sink.deliver_health(
            FeedHealth(reason=reason, detail=detail, at=self.clock.now())
        )
