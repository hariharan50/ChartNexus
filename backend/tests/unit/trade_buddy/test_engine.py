"""The engine around the state machine: gaps, throttling, resume, feed health.

These are the behaviours that need more than one level or more than one session
to express, so they sit here rather than in the state-machine suite.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from chartnexus.contexts.trade_buddy.application.ports import Tick
from chartnexus.contexts.trade_buddy.application.watch import STALE, WatchEngine
from chartnexus.contexts.trade_buddy.domain.budget import LevelBudget
from chartnexus.contexts.trade_buddy.domain.events import AlertKind
from chartnexus.contexts.trade_buddy.domain.level import LevelMark, LevelRole, MarkSet
from chartnexus.contexts.trade_buddy.domain.schedule import IST, WatchWindow
from chartnexus.contexts.trade_buddy.domain.state import LevelState
from chartnexus.infrastructure.trade_buddy.clock import FakeClock
from tests.unit.trade_buddy.conftest import (
    SESSION_START,
    MemoryLevelStore,
    RecordingSink,
    at,
    policy,
    window,
)

pytestmark = pytest.mark.unit

SYMBOL = "NSE:NIFTY50-INDEX"

#: Three resistances and three supports around a 24650 spot, as marked at 09:00.
MARKS = (
    LevelMark(label="R3", price=24_900.0, role=LevelRole.RESISTANCE),
    LevelMark(label="R2", price=24_800.0, role=LevelRole.RESISTANCE),
    LevelMark(label="R1", price=24_700.0, role=LevelRole.RESISTANCE),
    LevelMark(label="S1", price=24_600.0, role=LevelRole.SUPPORT),
    LevelMark(label="S2", price=24_500.0, role=LevelRole.SUPPORT),
    LevelMark(label="S3", price=24_400.0, role=LevelRole.SUPPORT),
)


def build(
    store: MemoryLevelStore,
    sink: RecordingSink,
    *,
    clock: FakeClock | None = None,
    budget: LevelBudget | None = None,
    watch_window: WatchWindow | None = None,
) -> tuple[WatchEngine, FakeClock]:
    the_clock = clock or FakeClock(SESSION_START)
    engine = WatchEngine(
        symbol=SYMBOL,
        policy=policy(),
        window=watch_window or window(),
        store=store,
        sink=sink,
        clock=the_clock,
        budget=budget or LevelBudget(),
    )
    return engine, the_clock


async def feed(engine: WatchEngine, clock: FakeClock, prices: list[tuple[float, float]]) -> None:
    """Replay ``(price, seconds-into-session)`` through the engine."""
    for price, offset in prices:
        clock.set(at(offset))
        while clock.monotonic() < offset:
            clock.advance(min(1.0, offset - clock.monotonic()))
        await engine.on_tick(Tick(symbol=SYMBOL, price=price, at=at(offset)))


class TestGapThrough:
    async def test_opening_beyond_two_levels_reports_both_once(self, store, sink):
        """The scenario the plain state machine cannot see.

        Price was never near R1 or R2, so neither has a transition to make and
        both would sit silently in IDLE for the whole session.
        """
        store.mark(SYMBOL, *MARKS)
        engine, clock = build(store, sink)
        await engine.load()

        # Opens at 24830 — above R1 (24700) and R2 (24800), below R3 (24900).
        await feed(engine, clock, [(24_830.0, 0.0)])

        gapped = sink.of_kind(AlertKind.GAPPED_THROUGH)
        assert sorted(event.label for event in gapped) == ["R1", "R2"]
        assert len(gapped) == 2

    async def test_a_gapped_level_flips_role_and_does_not_repeat(self, store, sink):
        store.mark(SYMBOL, *MARKS)
        engine, clock = build(store, sink)
        await engine.load()

        await feed(engine, clock, [(24_830.0, 0.0), (24_835.0, 1.0), (24_840.0, 2.0)])

        assert len(sink.of_kind(AlertKind.GAPPED_THROUGH)) == 2
        r1 = next(w for w in engine.watchers if w.mark.label == "R1")
        assert r1.role is LevelRole.SUPPORT
        assert r1.state is LevelState.BROKEN

    async def test_a_gapped_level_can_still_be_reclaimed(self, store, sink):
        """Reclaims land one level at a time, in the order price crosses them.

        R2 (24800) reclaims below 24788; R1 (24700) below 24688. Falling past
        the nearer line must not pre-emptively reclaim the further one.
        """
        store.mark(SYMBOL, *MARKS)
        engine, clock = build(store, sink)
        await engine.load()

        # Gap above both, then fall back through R2's line only.
        await feed(engine, clock, [(24_830.0, 0.0), (24_750.0, 60.0)])
        assert [event.label for event in sink.of_kind(AlertKind.RECLAIMED)] == ["R2"]

        # Falling further reclaims R1 as well.
        await feed(engine, clock, [(24_680.0, 120.0)])
        assert [event.label for event in sink.of_kind(AlertKind.RECLAIMED)] == ["R2", "R1"]

    async def test_no_gap_is_reported_when_the_open_is_between_levels(self, store, sink):
        store.mark(SYMBOL, *MARKS)
        engine, clock = build(store, sink)
        await engine.load()

        await feed(engine, clock, [(24_650.0, 0.0)])

        assert sink.of_kind(AlertKind.GAPPED_THROUGH) == []


class TestCooldownAndCap:
    async def test_cooldown_suppresses_a_repeat_observation(self, store, sink):
        store.mark(SYMBOL, MARKS[2])  # R1 only
        engine, clock = build(store, sink, budget=LevelBudget(cooldown=timedelta(minutes=20)))
        await engine.load()

        # Touch, leave, come back inside the cooldown window.
        await feed(
            engine,
            clock,
            [
                (24_698.0, 0.0),  # TOUCHED
                (24_500.0, 10.0),  # clear away, resets state to IDLE
                (24_698.0, 20.0),  # touches again, 20s later — inside cooldown
            ],
        )

        assert sink.kinds.count(AlertKind.TOUCHED) == 1

    async def test_cooldown_expiry_allows_the_next_observation(self, store, sink):
        store.mark(SYMBOL, MARKS[2])
        engine, clock = build(store, sink, budget=LevelBudget(cooldown=timedelta(minutes=20)))
        await engine.load()

        await feed(
            engine,
            clock,
            [
                (24_698.0, 0.0),  # TOUCHED
                (24_500.0, 10.0),
                (24_698.0, 21 * 60.0),  # 21 minutes later — cooldown expired
            ],
        )

        assert sink.kinds.count(AlertKind.TOUCHED) == 2

    async def test_daily_cap_stops_observations_at_the_limit(self, store, sink):
        store.mark(SYMBOL, MARKS[2])
        engine, clock = build(store, sink, budget=LevelBudget(cooldown=timedelta(0), daily_cap=3))
        await engine.load()

        # Six touches, cooldown disabled so only the cap can bite.
        prices = []
        for n in range(6):
            prices.append((24_698.0, n * 100.0))
            prices.append((24_500.0, n * 100.0 + 50.0))
        await feed(engine, clock, prices)

        assert sink.kinds.count(AlertKind.TOUCHED) == 3

    async def test_a_confirmed_break_is_never_suppressed_by_a_spent_budget(self, store, sink):
        """The policy decision, pinned.

        Three approach alerts exhaust R1's daily cap. The afternoon break
        through R1 must still arrive — a cap that can swallow a real break has
        made the alerting worse than none.
        """
        store.mark(SYMBOL, MARKS[2])  # R1 at 24700
        engine, clock = build(store, sink, budget=LevelBudget(cooldown=timedelta(0), daily_cap=3))
        await engine.load()

        burn = []
        for n in range(4):
            burn.append((24_698.0, n * 100.0))
            burn.append((24_500.0, n * 100.0 + 50.0))
        await feed(engine, clock, burn)
        assert sink.kinds.count(AlertKind.TOUCHED) == 3  # cap reached

        # Now break it: past 24712, held for 20s.
        await feed(engine, clock, [(24_715.0, 1_000.0), (24_720.0, 1_021.0)])

        assert sink.kinds.count(AlertKind.BREAK_CONFIRMED) == 1

    async def test_the_cap_is_per_level_not_global(self, store, sink):
        store.mark(SYMBOL, *MARKS)
        engine, clock = build(store, sink, budget=LevelBudget(cooldown=timedelta(0), daily_cap=1))
        await engine.load()

        # Touch R1, then touch S1. Separate labels, separate budgets.
        await feed(engine, clock, [(24_698.0, 0.0), (24_602.0, 100.0)])

        touched = {event.label for event in sink.of_kind(AlertKind.TOUCHED)}
        assert touched == {"R1", "S1"}


class TestMarketHours:
    async def test_ticks_outside_the_window_are_ignored(self, store, sink):
        store.mark(SYMBOL, *MARKS)
        engine, clock = build(store, sink)
        await engine.load()

        # 15:45 IST — past the 15:20 close.
        late = SESSION_START.replace(hour=15, minute=45)
        clock.set(late)
        await engine.on_tick(Tick(symbol=SYMBOL, price=24_830.0, at=late))

        assert sink.events == []

    async def test_a_holiday_closes_the_window(self, store, sink):
        store.mark(SYMBOL, *MARKS)
        holiday = SESSION_START.date()
        closed = WatchWindow.from_config("09:15", "15:20", frozenset({holiday}))
        engine, clock = build(store, sink, watch_window=closed)
        await engine.load()

        await feed(engine, clock, [(24_830.0, 0.0)])

        assert sink.events == []

    async def test_a_weekend_closes_the_window(self, store, sink):
        store.mark(SYMBOL, *MARKS)
        engine, clock = build(store, sink)
        await engine.load()

        saturday = SESSION_START.replace(day=31)  # 2026-10-31 is a Saturday
        clock.set(saturday)
        await engine.on_tick(Tick(symbol=SYMBOL, price=24_830.0, at=saturday))

        assert sink.events == []


class TestResume:
    async def test_saved_states_are_resumed_rather_than_re_fired(self, store, sink):
        """A restart at 14:00 must not replay the morning."""
        store.mark(SYMBOL, *MARKS)
        first, clock = build(store, sink)
        await first.load()
        await feed(first, clock, [(24_830.0, 0.0)])
        assert len(sink.of_kind(AlertKind.GAPPED_THROUGH)) == 2

        # Restart: a fresh engine and sink, same store.
        resumed_sink = RecordingSink()
        second, clock2 = build(store, resumed_sink)
        await second.load()
        await feed(second, clock2, [(24_835.0, 100.0)])

        assert resumed_sink.events == []
        assert {w.mark.label for w in second.watchers if w.broken} == {"R1", "R2"}

    async def test_a_fresh_session_builds_watchers_from_the_marks(self, store, sink):
        store.mark(SYMBOL, *MARKS)
        engine, _ = build(store, sink)
        await engine.load()

        assert len(engine.watchers) == len(MARKS)
        assert all(w.state is LevelState.IDLE for w in engine.watchers)

    async def test_state_is_persisted_after_every_tick(self, store, sink):
        store.mark(SYMBOL, *MARKS)
        engine, clock = build(store, sink)
        await engine.load()

        await feed(engine, clock, [(24_650.0, 0.0), (24_655.0, 1.0)])

        assert store.saves == 2


class TestFeedHealth:
    async def test_silence_during_market_hours_raises_a_health_alert(self, store, sink):
        store.mark(SYMBOL, *MARKS)
        engine, clock = build(store, sink)
        engine.stale_after_seconds = 90.0
        await engine.load()

        await feed(engine, clock, [(24_650.0, 0.0)])
        clock.advance(120.0)  # two minutes of nothing
        await engine.check_staleness()

        assert [h.reason for h in sink.health] == [STALE]
        assert "NIFTY" in sink.health[0].detail

    async def test_a_fresh_tick_clears_the_staleness_concern(self, store, sink):
        store.mark(SYMBOL, *MARKS)
        engine, clock = build(store, sink)
        await engine.load()

        await feed(engine, clock, [(24_650.0, 0.0)])
        clock.advance(30.0)
        await engine.check_staleness()

        assert sink.health == []

    async def test_silence_outside_market_hours_is_not_an_alert(self, store, sink):
        store.mark(SYMBOL, *MARKS)
        engine, clock = build(store, sink)
        await engine.load()

        await feed(engine, clock, [(24_650.0, 0.0)])
        clock.set(SESSION_START.replace(hour=20, minute=0))
        clock.advance(600.0)
        await engine.check_staleness()

        assert sink.health == []

    async def test_a_disconnect_is_reported_with_its_reason(self, store, sink):
        engine, _ = build(store, sink)
        await engine.report_disconnect("socket closed", reason="token_rejected")

        assert [h.reason for h in sink.health] == ["token_rejected"]


class TestSessionRollover:
    async def test_a_new_session_re_evaluates_gaps(self, store, sink):
        """Day two must settle its own gaps against day two's open."""
        store.mark(SYMBOL, *MARKS)
        engine, clock = build(store, sink)
        await engine.load()

        await feed(engine, clock, [(24_650.0, 0.0)])
        assert sink.of_kind(AlertKind.GAPPED_THROUGH) == []

        # Next trading day, opening above R1 and R2.
        # Re-marked for Tuesday, as a trader would each morning. Without
        # this the levels are Monday's and nothing is alerted on at all —
        # see TestStaleLevels.
        tuesday = SESSION_START + timedelta(days=1)
        store.mark(SYMBOL, *MARKS, on=tuesday.date())
        await engine.load()
        clock.set(tuesday)
        await engine.on_tick(Tick(symbol=SYMBOL, price=24_830.0, at=tuesday))

        assert len(sink.of_kind(AlertKind.GAPPED_THROUGH)) == 2

    async def test_the_daily_cap_resets_on_a_new_session(self, store, sink):
        store.mark(SYMBOL, MARKS[2])
        engine, clock = build(store, sink, budget=LevelBudget(cooldown=timedelta(0), daily_cap=1))
        await engine.load()

        await feed(engine, clock, [(24_698.0, 0.0), (24_500.0, 10.0), (24_698.0, 20.0)])
        assert sink.kinds.count(AlertKind.TOUCHED) == 1

        tuesday = SESSION_START + timedelta(days=1)
        store.mark(SYMBOL, MARKS[2], on=tuesday.date())
        await engine.load()
        clock.set(tuesday)
        await engine.on_tick(Tick(symbol=SYMBOL, price=24_698.0, at=tuesday))

        assert sink.kinds.count(AlertKind.TOUCHED) == 2

    async def test_a_level_left_touched_at_the_close_reports_again_next_session(self, store, sink):
        """Regression: within-session memory must not leak into the next session.

        Without the rollover reset, a level sitting in TOUCHED at Monday's close
        stayed there, and the repeat-suppression then silenced it for the whole
        of Tuesday — the daily cap resetting made no difference because no event
        was ever generated to spend it.
        """
        store.mark(SYMBOL, MARKS[2])
        engine, clock = build(store, sink)
        await engine.load()

        # Monday closes with price sitting on R1.
        await feed(engine, clock, [(24_698.0, 0.0)])
        monday_touches = sink.kinds.count(AlertKind.TOUCHED)
        assert monday_touches == 1
        assert next(iter(engine.watchers)).state is LevelState.TOUCHED

        # Tuesday opens on it again. That is a new fact about a new session.
        tuesday = SESSION_START + timedelta(days=1)
        store.mark(SYMBOL, MARKS[2], on=tuesday.date())
        await engine.load()
        clock.set(tuesday)
        await engine.on_tick(Tick(symbol=SYMBOL, price=24_698.0, at=tuesday))

        assert sink.kinds.count(AlertKind.TOUCHED) == 2

    async def test_a_broken_level_stays_broken_across_the_session_boundary(self, store, sink):
        """The other half of the rollover rule: broken-ness is durable.

        A resistance broken on Monday is still acting as support on Tuesday. It
        stays flipped until price reclaims it, so the reset must not clear it.
        """
        store.mark(SYMBOL, MARKS[2])  # R1 at 24700
        engine, clock = build(store, sink)
        await engine.load()

        # Open below the level (so this is a break, not an opening gap), then
        # push through the 24712 threshold and hold past the 20s confirmation.
        await feed(engine, clock, [(24_650.0, 0.0), (24_715.0, 10.0), (24_720.0, 31.0)])
        assert sink.kinds.count(AlertKind.BREAK_CONFIRMED) == 1
        assert sink.kinds.count(AlertKind.GAPPED_THROUGH) == 0

        tuesday = SESSION_START + timedelta(days=1)
        store.mark(SYMBOL, MARKS[2], on=tuesday.date())
        clock.set(tuesday)
        await engine.on_tick(Tick(symbol=SYMBOL, price=24_730.0, at=tuesday))

        r1 = next(iter(engine.watchers))
        assert r1.state is LevelState.BROKEN
        assert r1.role is LevelRole.SUPPORT
        # And no duplicate break alert for ground already covered.
        assert sink.kinds.count(AlertKind.BREAK_CONFIRMED) == 1


class TestIstWindow:
    @pytest.mark.parametrize(
        ("hour", "minute", "expected"),
        [
            (9, 14, False),
            (9, 15, True),
            (12, 0, True),
            (15, 20, True),
            (15, 21, False),
        ],
    )
    def test_window_boundaries(self, hour, minute, expected):
        moment = SESSION_START.replace(hour=hour, minute=minute)
        assert window().is_open(moment) is expected

    def test_a_utc_instant_is_converted_before_comparison(self):
        """10:00 IST is 04:30 UTC; a naive UTC comparison would call it closed."""
        utc_moment = datetime(2026, 10, 26, 4, 30, tzinfo=UTC)
        assert window().is_open(utc_moment)
        assert not window().is_open(datetime(2026, 10, 26, 2, 0, tzinfo=UTC))

    def test_ist_offset_is_five_thirty(self):
        assert IST.utcoffset(None) == timedelta(hours=5, minutes=30)


class TestStaleLevels:
    """Levels are a daily artefact, and acting on yesterday's is the worst
    failure this module has.

    Not silence — silence is visibly wrong and gets investigated. Confident
    alerts about prices nobody is watching any more get acted on.
    """

    async def test_yesterdays_levels_produce_no_alerts(self, store, sink):
        store.mark(SYMBOL, *MARKS, on=(SESSION_START - timedelta(days=3)).date())
        engine, clock = build(store, sink)
        await engine.load()

        # Price sitting right on R1 — a touch, if the levels were current.
        await feed(engine, clock, [(24_698.0, 0.0), (24_699.0, 10.0)])

        assert sink.events == []

    async def test_it_says_so_rather_than_going_quiet(self, store, sink):
        """Silence with no explanation is the thing being avoided."""
        store.mark(SYMBOL, *MARKS, on=(SESSION_START - timedelta(days=3)).date())
        engine, clock = build(store, sink)
        await engine.load()

        await feed(engine, clock, [(24_698.0, 0.0)])

        assert [h.reason for h in sink.health] == ["levels_stale"]
        detail = sink.health[0].detail
        assert "2026-10-23" in detail
        assert "re-marked" in detail

    async def test_the_notice_is_sent_once_per_session_not_once_per_tick(self, store, sink):
        store.mark(SYMBOL, *MARKS, on=(SESSION_START - timedelta(days=3)).date())
        engine, clock = build(store, sink)
        await engine.load()

        await feed(engine, clock, [(24_698.0, n * 5.0) for n in range(12)])

        assert len(sink.health) == 1

    async def test_re_marking_brings_the_watch_back(self, store, sink):
        store.mark(SYMBOL, *MARKS, on=(SESSION_START - timedelta(days=3)).date())
        engine, clock = build(store, sink)
        await engine.load()
        await feed(engine, clock, [(24_698.0, 0.0)])
        assert sink.events == []

        # Re-marked for today, as the morning routine would.
        store.mark(SYMBOL, *MARKS, on=SESSION_START.date())
        await engine.load()
        await feed(engine, clock, [(24_500.0, 100.0), (24_698.0, 110.0)])

        assert AlertKind.TOUCHED in sink.kinds

    async def test_marks_with_no_stamp_at_all_are_treated_as_stale(self, store, sink):
        """Assuming an unstamped set is today's is precisely the mistake."""
        store.marks[SYMBOL] = MarkSet(marks=MARKS, marked_on=None)
        engine, clock = build(store, sink)
        await engine.load()

        await feed(engine, clock, [(24_698.0, 0.0)])

        assert sink.events == []
        assert [h.reason for h in sink.health] == ["levels_stale"]

    async def test_an_unmarked_instrument_is_quiet_without_complaining(self, store, sink):
        """Nothing marked is not the same as marked-and-stale: the fix differs
        (mark some, versus re-mark the ones you have), so it must not raise
        the same notice."""
        engine, clock = build(store, sink)
        await engine.load()

        await feed(engine, clock, [(24_698.0, 0.0)])

        assert sink.events == []
        assert sink.health == []
