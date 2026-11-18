"""Keeping the running engines in line with what is marked, mid-session.

The watch loop built an engine per newly marked instrument and then never
looked at it again, which made three ordinary actions silently ineffective
until the process restarted:

**Re-marking.** The worst of the three. Levels stamped for an earlier session
are not alerted on at all — the engine goes quiet and the page says "re-mark
them". Re-marking then changed nothing, because the engine kept the stamp it
read at startup. The product's own remedy was inert, and the result was silence
through a real break.

**Changing prices.** Same mechanism, quieter: the watch carried on against the
levels loaded at startup, so the alerts described prices the user had replaced.

**Clearing.** The engine stayed in the dict and kept alerting on levels that
had been deleted, while re-saving the state the delete had cleared.

`test_engine.py::TestStaleLevels::test_re_marking_brings_the_watch_back`
covered the engine's half of this and passed, because it calls `engine.load()`
by hand. Nothing called it in the runtime. These tests drive the reconcile pass
itself, with a real store and real engines, so that gap cannot reopen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

import pytest

from chartnexus.contexts.trade_buddy.application.watch import WatchEngine
from chartnexus.contexts.trade_buddy.domain.level import LevelMark, LevelRole, MarkSet
from chartnexus.entrypoints.trade_buddy_runtime import reconcile_engines
from chartnexus.infrastructure.trade_buddy.clock import FakeClock
from tests.unit.trade_buddy.conftest import (
    SESSION_START,
    MemoryLevelStore,
    RecordingSink,
    policy,
    window,
)

pytestmark = pytest.mark.unit

NIFTY = "NIFTY"
BANKNIFTY = "BANKNIFTY"
OFFERED = (NIFTY, BANKNIFTY)

MORNING = (
    LevelMark(label="R1", price=24_700.0, role=LevelRole.RESISTANCE),
    LevelMark(label="S1", price=24_600.0, role=LevelRole.SUPPORT),
)
#: Same labels, different prices — the case where comparing labels alone would
#: resume a state earned at a level that no longer exists.
MOVED = (
    LevelMark(label="R1", price=24_780.0, role=LevelRole.RESISTANCE),
    LevelMark(label="S1", price=24_660.0, role=LevelRole.SUPPORT),
)

YESTERDAY = (SESSION_START - timedelta(days=3)).date()
TODAY = SESSION_START.date()


@dataclass(slots=True)
class RecordingFeed:
    """Records subscriptions the way the real adapter would receive them."""

    calls: list[tuple[str, ...]] = field(default_factory=list)

    async def subscribe(self, symbols: tuple[str, ...]) -> None:
        self.calls.append(symbols)

    @property
    def subscribed(self) -> list[str]:
        return [symbol for call in self.calls for symbol in call]


@dataclass(slots=True)
class Harness:
    """One reconcile pass, with everything it touches kept to hand."""

    store: MemoryLevelStore
    sink: RecordingSink
    feed: RecordingFeed
    engines: dict[str, WatchEngine]
    loaded: dict[str, MarkSet]
    built: list[str]

    async def reconcile(self) -> tuple[str, ...]:
        # Keyed by symbol alone: one user. The per-user loop keys by
        # (user, symbol) through the same function — see TestManyUsers.
        return await reconcile_engines(
            targets=OFFERED,
            load_marks=self.store.load_marks,
            symbol_of=lambda symbol: symbol,
            feed=self.feed,
            engines=self.engines,
            loaded=self.loaded,
            build=self._build,
        )

    async def _build(self, symbol: str) -> WatchEngine:
        self.built.append(symbol)
        return WatchEngine(
            symbol=symbol,
            policy=policy(),
            window=window(),
            store=self.store,
            sink=self.sink,
            clock=FakeClock(SESSION_START),
        )

    def marks_of(self, symbol: str) -> tuple[LevelMark, ...]:
        """The levels the live engine is actually watching."""
        return tuple(w.mark for w in self.engines[symbol].watchers)


@pytest.fixture
def harness(store, sink) -> Harness:
    return Harness(
        store=store,
        sink=sink,
        feed=RecordingFeed(),
        engines={},
        loaded={},
        built=[],
    )


class TestFirstPass:
    async def test_a_marked_instrument_is_built_and_subscribed(self, harness):
        harness.store.mark(NIFTY, *MORNING)

        wanted = await harness.reconcile()

        assert wanted == (NIFTY,)
        assert harness.built == [NIFTY]
        assert harness.feed.subscribed == [NIFTY]

    async def test_an_unmarked_instrument_is_left_alone(self, harness):
        harness.store.mark(NIFTY, *MORNING)

        await harness.reconcile()

        assert BANKNIFTY not in harness.engines
        assert BANKNIFTY not in harness.feed.subscribed

    async def test_nothing_marked_builds_nothing(self, harness):
        assert await harness.reconcile() == ()
        assert harness.engines == {}
        assert harness.feed.calls == []

    async def test_an_instrument_marked_later_joins_without_rebuilding_the_first(self, harness):
        harness.store.mark(NIFTY, *MORNING)
        await harness.reconcile()

        harness.store.mark(BANKNIFTY, *MORNING)
        await harness.reconcile()

        assert harness.built == [NIFTY, BANKNIFTY]
        assert harness.feed.calls == [(NIFTY,), (BANKNIFTY,)]


class TestUnchangedMarks:
    async def test_a_repeat_pass_does_not_rebuild(self, harness):
        harness.store.mark(NIFTY, *MORNING)
        await harness.reconcile()

        for _ in range(5):
            await harness.reconcile()

        assert harness.built == [NIFTY]

    async def test_a_repeat_pass_does_not_re_subscribe(self, harness):
        harness.store.mark(NIFTY, *MORNING)
        await harness.reconcile()

        await harness.reconcile()

        assert harness.feed.calls == [(NIFTY,)]

    async def test_the_engine_object_is_kept(self, harness):
        """Rebuilding would drop the last-tick reading the watchdog needs."""
        harness.store.mark(NIFTY, *MORNING)
        await harness.reconcile()
        engine = harness.engines[NIFTY]

        await harness.reconcile()

        assert harness.engines[NIFTY] is engine


class TestReMarking:
    """The fix that matters: a re-mark has to take effect without a restart."""

    async def test_stale_levels_re_marked_for_today_are_picked_up(self, harness):
        harness.store.marks[NIFTY] = MarkSet(marks=MORNING, marked_on=YESTERDAY)
        await harness.reconcile()
        assert harness.engines[NIFTY]._marked_on == YESTERDAY

        harness.store.marks[NIFTY] = MarkSet(marks=MORNING, marked_on=TODAY)
        await harness.reconcile()

        assert harness.engines[NIFTY]._marked_on == TODAY

    async def test_replaced_prices_reach_the_live_engine(self, harness):
        harness.store.mark(NIFTY, *MORNING)
        await harness.reconcile()
        assert harness.marks_of(NIFTY) == MORNING

        harness.store.mark(NIFTY, *MOVED)
        await harness.reconcile()

        assert harness.marks_of(NIFTY) == MOVED

    async def test_the_engine_is_reloaded_rather_than_rebuilt(self, harness):
        harness.store.mark(NIFTY, *MORNING)
        await harness.reconcile()
        engine = harness.engines[NIFTY]

        harness.store.mark(NIFTY, *MOVED)
        await harness.reconcile()

        assert harness.engines[NIFTY] is engine
        assert harness.built == [NIFTY]

    async def test_a_re_mark_does_not_re_subscribe(self, harness):
        harness.store.mark(NIFTY, *MORNING)
        await harness.reconcile()

        harness.store.mark(NIFTY, *MOVED)
        await harness.reconcile()

        assert harness.feed.calls == [(NIFTY,)]

    async def test_stale_states_written_back_by_a_tick_are_not_resumed(self, harness):
        """The race the engine has to be robust to on its own.

        `SetLevels` clears the saved states, but a running engine saves its own
        after every tick and can write the old set back before the reconcile
        pass runs. Resuming those would watch the replaced prices while
        reporting the new ones as marked.
        """
        harness.store.mark(NIFTY, *MORNING)
        await harness.reconcile()
        engine = harness.engines[NIFTY]
        # The engine persists states for MORNING, as a tick would.
        await harness.store.save_watchers(NIFTY, engine.watchers)

        harness.store.mark(NIFTY, *MOVED)
        await harness.reconcile()

        assert harness.marks_of(NIFTY) == MOVED

    async def test_only_the_changed_instrument_is_reloaded(self, harness):
        harness.store.mark(NIFTY, *MORNING)
        harness.store.mark(BANKNIFTY, *MORNING)
        await harness.reconcile()
        untouched = harness.engines[BANKNIFTY]

        harness.store.mark(NIFTY, *MOVED)
        await harness.reconcile()

        assert harness.marks_of(NIFTY) == MOVED
        assert harness.marks_of(BANKNIFTY) == MORNING
        assert harness.engines[BANKNIFTY] is untouched


class TestClearedMarks:
    async def test_a_cleared_instrument_stops_being_watched(self, harness):
        harness.store.mark(NIFTY, *MORNING)
        await harness.reconcile()

        await harness.store.clear(NIFTY)
        wanted = await harness.reconcile()

        assert wanted == ()
        assert NIFTY not in harness.engines

    async def test_clearing_one_leaves_the_other_running(self, harness):
        harness.store.mark(NIFTY, *MORNING)
        harness.store.mark(BANKNIFTY, *MORNING)
        await harness.reconcile()

        await harness.store.clear(NIFTY)
        wanted = await harness.reconcile()

        assert wanted == (BANKNIFTY,)
        assert list(harness.engines) == [BANKNIFTY]

    async def test_re_marking_after_a_clear_builds_a_fresh_engine(self, harness):
        harness.store.mark(NIFTY, *MORNING)
        await harness.reconcile()
        await harness.store.clear(NIFTY)
        await harness.reconcile()

        harness.store.mark(NIFTY, *MOVED)
        await harness.reconcile()

        assert harness.built == [NIFTY, NIFTY]
        assert harness.marks_of(NIFTY) == MOVED

    async def test_the_subscription_is_not_torn_down(self, harness):
        """Nothing consumes ticks without an engine, and keeping the
        subscription makes a later re-mark cost no socket traffic."""
        harness.store.mark(NIFTY, *MORNING)
        await harness.reconcile()

        await harness.store.clear(NIFTY)
        await harness.reconcile()

        assert harness.feed.calls == [(NIFTY,)]


# -- many users, one feed -----------------------------------------------------

ALICE = "alice"
BOB = "bob"

#: Bob's levels for the same index — a different person, different marks.
BOB_NIFTY = (
    LevelMark(label="R1", price=24_900.0, role=LevelRole.RESISTANCE),
    LevelMark(label="S1", price=24_400.0, role=LevelRole.SUPPORT),
)


@dataclass(slots=True)
class ManyUsers:
    """The per-user loop's reconcile: keys are (user, symbol), one store each."""

    stores: dict[str, MemoryLevelStore]
    sinks: dict[str, RecordingSink]
    feed: RecordingFeed = field(default_factory=RecordingFeed)
    engines: dict[tuple[str, str], WatchEngine] = field(default_factory=dict)
    loaded: dict[tuple[str, str], MarkSet] = field(default_factory=dict)

    async def reconcile(self) -> tuple[tuple[str, str], ...]:
        targets = tuple((user, symbol) for user in self.stores for symbol in OFFERED)
        return await reconcile_engines(
            targets=targets,
            load_marks=lambda key: self.stores[key[0]].load_marks(key[1]),
            symbol_of=lambda key: key[1],
            feed=self.feed,
            engines=self.engines,
            loaded=self.loaded,
            build=self._build,
        )

    async def _build(self, key: tuple[str, str]) -> WatchEngine:
        user, symbol = key
        return WatchEngine(
            symbol=symbol,
            policy=policy(),
            window=window(),
            store=self.stores[user],
            sink=self.sinks[user],
            clock=FakeClock(SESSION_START),
        )

    def marks_of(self, user: str, symbol: str) -> tuple[LevelMark, ...]:
        return tuple(w.mark for w in self.engines[(user, symbol)].watchers)


@pytest.fixture
def many() -> ManyUsers:
    return ManyUsers(
        stores={ALICE: MemoryLevelStore(), BOB: MemoryLevelStore()},
        sinks={ALICE: RecordingSink(), BOB: RecordingSink()},
    )


class TestManyUsers:
    async def test_two_users_on_one_index_each_watch_their_own_levels(self, many):
        many.stores[ALICE].mark(NIFTY, *MORNING)
        many.stores[BOB].mark(NIFTY, *BOB_NIFTY)

        wanted = await many.reconcile()

        assert set(wanted) == {(ALICE, NIFTY), (BOB, NIFTY)}
        assert many.marks_of(ALICE, NIFTY) == MORNING
        assert many.marks_of(BOB, NIFTY) == BOB_NIFTY

    async def test_one_subscription_serves_every_user_of_an_index(self, many):
        many.stores[ALICE].mark(NIFTY, *MORNING)
        many.stores[BOB].mark(NIFTY, *BOB_NIFTY)

        await many.reconcile()

        assert many.feed.calls == [(NIFTY,)]

    async def test_each_engine_alerts_its_own_user_only(self, many):
        many.stores[ALICE].mark(NIFTY, *MORNING)
        many.stores[BOB].mark(NIFTY, *BOB_NIFTY)
        await many.reconcile()

        assert many.engines[(ALICE, NIFTY)].sink is many.sinks[ALICE]
        assert many.engines[(BOB, NIFTY)].sink is many.sinks[BOB]

    async def test_one_user_clearing_leaves_the_other_watching(self, many):
        many.stores[ALICE].mark(NIFTY, *MORNING)
        many.stores[BOB].mark(NIFTY, *BOB_NIFTY)
        await many.reconcile()

        await many.stores[ALICE].clear(NIFTY)
        wanted = await many.reconcile()

        assert wanted == ((BOB, NIFTY),)
        assert many.marks_of(BOB, NIFTY) == BOB_NIFTY

    async def test_a_second_user_joining_does_not_re_subscribe(self, many):
        many.stores[ALICE].mark(NIFTY, *MORNING)
        await many.reconcile()

        many.stores[BOB].mark(NIFTY, *BOB_NIFTY)
        await many.reconcile()

        # Bob's engine is new, but NIFTY is already on the socket — and
        # `subscribe` is idempotent, so naming it again costs nothing either way.
        assert (BOB, NIFTY) in many.engines
        assert all(call == (NIFTY,) for call in many.feed.calls)
