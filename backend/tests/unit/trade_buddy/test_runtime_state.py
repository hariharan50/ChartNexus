"""Does the watch survive a restart without lying or repeating itself?

These pin the three things that were wrong when the module was first called
done: the status route reported `last_tick_at: null` and a full alert allowance
forever, and a restart handed every level a fresh daily cap and a fresh WhatsApp
window. Each was worse than reporting nothing, because each looked like an
answer.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta

import pytest

from chartnexus.contexts.trade_buddy.application.ports import RuntimeState, Tick
from chartnexus.contexts.trade_buddy.application.watch import WatchEngine
from chartnexus.contexts.trade_buddy.domain.budget import LevelBudget, WhatsAppBudget
from chartnexus.contexts.trade_buddy.domain.events import AlertEvent, AlertKind
from chartnexus.contexts.trade_buddy.domain.level import LevelMark, LevelRole
from chartnexus.infrastructure.trade_buddy.clock import FakeClock
from chartnexus.infrastructure.trade_buddy.json_level_store import JsonLevelStore
from tests.unit.trade_buddy.conftest import (
    SESSION_START,
    MemoryLevelStore,
    RecordingSink,
    alert_event,
    at,
    bands,
    policy,
    window,
)

pytestmark = pytest.mark.unit

SYMBOL = "NSE:NIFTY50-INDEX"
#: The session the fixtures mark for.
SESSION = SESSION_START.date()
R1 = LevelMark(label="R1", price=24_700.0, role=LevelRole.RESISTANCE)


def build(
    store,
    sink,
    *,
    clock: FakeClock | None = None,
    budget: LevelBudget | None = None,
    whatsapp: WhatsAppBudget | None = None,
) -> tuple[WatchEngine, FakeClock]:
    the_clock = clock or FakeClock(SESSION_START)
    engine = WatchEngine(
        symbol=SYMBOL,
        policy=policy(),
        window=window(),
        store=store,
        sink=sink,
        clock=the_clock,
        budget=budget or LevelBudget(),
        whatsapp_budget=whatsapp,
    )
    return engine, the_clock


async def feed(engine: WatchEngine, clock: FakeClock, prices: list[tuple[float, float]]) -> None:
    for price, offset in prices:
        clock.set(at(offset))
        while clock.monotonic() < offset:
            clock.advance(min(1.0, offset - clock.monotonic()))
        await engine.on_tick(Tick(symbol=SYMBOL, price=price, at=at(offset)))


class TestLastTickAt:
    async def test_the_last_tick_time_is_persisted(self, store, sink):
        """The field that distinguishes a dead watcher from a quiet market."""
        store.mark(SYMBOL, R1)
        engine, clock = build(store, sink)
        await engine.load()

        await feed(engine, clock, [(24_650.0, 0.0), (24_655.0, 30.0)])

        saved = await store.load_runtime(SYMBOL)
        assert saved.last_tick_at == at(30.0)

    async def test_it_is_none_before_the_first_tick(self, store, sink):
        store.mark(SYMBOL, R1)
        engine, _ = build(store, sink)
        await engine.load()

        assert (await store.load_runtime(SYMBOL)).last_tick_at is None

    async def test_it_survives_a_restart(self, store, sink):
        store.mark(SYMBOL, R1)
        first, clock = build(store, sink)
        await first.load()
        await feed(first, clock, [(24_650.0, 0.0)])

        second, _ = build(store, RecordingSink())
        await second.load()

        assert (await store.load_runtime(SYMBOL)).last_tick_at == at(0.0)


class TestLevelBudgetPersistence:
    async def test_the_daily_cap_is_not_reset_by_a_restart(self, store, sink):
        """The spec's "don't re-fire for ground already covered", at the cap level."""
        store.mark(SYMBOL, R1)
        engine, clock = build(store, sink, budget=LevelBudget(cooldown=timedelta(0), daily_cap=2))
        await engine.load()

        # Burn both of R1's observation alerts.
        await feed(
            engine,
            clock,
            [(24_698.0, 0.0), (24_500.0, 10.0), (24_698.0, 20.0), (24_500.0, 30.0)],
        )
        assert sink.kinds.count(AlertKind.TOUCHED) == 2

        # Restart mid-session. The cap must still be spent.
        resumed_sink = RecordingSink()
        second, clock2 = build(
            store,
            resumed_sink,
            clock=FakeClock(at(40.0), monotonic=40.0),
            budget=LevelBudget(cooldown=timedelta(0), daily_cap=2),
        )
        await second.load()
        await feed(second, clock2, [(24_698.0, 50.0)])

        assert resumed_sink.kinds.count(AlertKind.TOUCHED) == 0

    async def test_a_cooldown_survives_a_restart(self, store, sink):
        store.mark(SYMBOL, R1)
        engine, clock = build(
            store, sink, budget=LevelBudget(cooldown=timedelta(minutes=20), daily_cap=9)
        )
        await engine.load()
        await feed(engine, clock, [(24_698.0, 0.0), (24_500.0, 10.0)])
        assert sink.kinds.count(AlertKind.TOUCHED) == 1

        resumed_sink = RecordingSink()
        second, clock2 = build(
            store,
            resumed_sink,
            clock=FakeClock(at(60.0), monotonic=60.0),
            budget=LevelBudget(cooldown=timedelta(minutes=20), daily_cap=9),
        )
        await second.load()
        # One minute later — well inside the 20-minute cooldown.
        await feed(second, clock2, [(24_698.0, 70.0)])

        assert resumed_sink.kinds.count(AlertKind.TOUCHED) == 0

    async def test_a_confirmed_break_still_lands_after_a_restart(self, store, sink):
        """Restoring the budget must not restore it over the break exemption."""
        store.mark(SYMBOL, R1)
        engine, clock = build(store, sink, budget=LevelBudget(cooldown=timedelta(0), daily_cap=1))
        await engine.load()
        await feed(engine, clock, [(24_698.0, 0.0)])  # spends the only allowance

        resumed_sink = RecordingSink()
        second, clock2 = build(
            store,
            resumed_sink,
            clock=FakeClock(at(100.0), monotonic=100.0),
            budget=LevelBudget(cooldown=timedelta(0), daily_cap=1),
        )
        await second.load()
        await feed(second, clock2, [(24_715.0, 110.0), (24_720.0, 131.0)])

        assert resumed_sink.kinds.count(AlertKind.BREAK_CONFIRMED) == 1


class TestSessionPersistence:
    """Gap settlement happens once per *session*, not once per process."""

    async def test_a_mid_session_restart_does_not_re_settle_gaps(self, store, sink):
        """Regression: the restart used to shortcut the confirmation hold.

        A new engine instance starts with no session, so the first tick it saw
        ran gap settlement — and a price already past the buffer was reported as
        GAPPED_THROUGH, instantly and with the role flipped. That bypassed the
        20-second hold that the store's BREAK_PENDING downgrade had just gone to
        the trouble of making the break re-earn.
        """
        store.mark(SYMBOL, R1)
        first, clock = build(store, sink)
        await first.load()
        await feed(first, clock, [(24_650.0, 0.0)])  # establishes the session

        resumed_sink = RecordingSink()
        second, clock2 = build(store, resumed_sink, clock=FakeClock(at(100.0), monotonic=100.0))
        await second.load()

        # Price is now past R1's 24712 threshold. This must open a *pending*
        # break, not a confirmed gap.
        await feed(second, clock2, [(24_715.0, 110.0)])
        assert resumed_sink.events == []

        # And it still has to hold for the full 20 seconds.
        await feed(second, clock2, [(24_716.0, 125.0)])
        assert resumed_sink.events == []

        await feed(second, clock2, [(24_717.0, 131.0)])
        assert resumed_sink.kinds == [AlertKind.BREAK_CONFIRMED]

    async def test_the_session_date_is_persisted(self, store, sink):
        store.mark(SYMBOL, R1)
        engine, clock = build(store, sink)
        await engine.load()
        await feed(engine, clock, [(24_650.0, 0.0)])

        assert (await store.load_runtime(SYMBOL)).session == SESSION_START.date()

    async def test_a_genuinely_new_session_still_settles_gaps(self, store, sink):
        """The fix must not disable gap detection for the next trading day."""
        store.mark(SYMBOL, R1)
        first, clock = build(store, sink)
        await first.load()
        await feed(first, clock, [(24_650.0, 0.0)])

        tuesday = SESSION_START + timedelta(days=1)
        store.mark(SYMBOL, R1, on=tuesday.date())
        resumed_sink = RecordingSink()
        second, _ = build(store, resumed_sink, clock=FakeClock(tuesday))
        await second.load()
        await second.on_tick(Tick(symbol=SYMBOL, price=24_830.0, at=tuesday))

        assert resumed_sink.kinds == [AlertKind.GAPPED_THROUGH]


class TestWhatsAppBudgetPersistence:
    async def test_the_rolling_window_is_persisted(self, store, sink):
        store.mark(SYMBOL, R1)
        whatsapp = WhatsAppBudget(limit=5)
        whatsapp.record(SESSION_START)
        whatsapp.record(SESSION_START)
        engine, clock = build(store, sink, whatsapp=whatsapp)
        await engine.load()

        await feed(engine, clock, [(24_650.0, 0.0)])

        assert len((await store.load_runtime(SYMBOL)).whatsapp_sends) == 2

    async def test_a_restart_does_not_hand_back_a_fresh_allowance(self, store, sink):
        """CallMeBot is counting whether or not we are."""
        store.mark(SYMBOL, R1)
        spent = WhatsAppBudget(limit=2)
        spent.record(SESSION_START)
        spent.record(SESSION_START)
        first, clock = build(store, sink, whatsapp=spent)
        await first.load()
        await feed(first, clock, [(24_650.0, 0.0)])
        assert not spent.available(SESSION_START)

        # Restart with a pristine budget object.
        fresh = WhatsAppBudget(limit=2)
        assert fresh.available(SESSION_START)  # it starts empty...
        second, _ = build(store, RecordingSink(), whatsapp=fresh)
        await second.load()

        # ...and load() must fill it from disk.
        assert fresh.used(SESSION_START) == 2
        assert not fresh.available(SESSION_START)

    def test_reload_keeps_the_limit_and_window(self):
        budget = WhatsAppBudget(limit=7, window=timedelta(hours=2))
        budget.reload([SESSION_START.isoformat()])

        assert budget.limit == 7
        assert budget.window == timedelta(hours=2)
        assert budget.used(SESSION_START) == 1

    def test_reload_replaces_rather_than_appends(self):
        budget = WhatsAppBudget(limit=5)
        budget.record(SESSION_START)
        budget.reload([SESSION_START.isoformat()])

        assert budget.used(SESSION_START) == 1

    def test_reload_skips_unparseable_stamps(self):
        budget = WhatsAppBudget(limit=5)
        budget.reload(["not-a-date", SESSION_START.isoformat()])

        assert budget.used(SESSION_START) == 1


class TestCooldownScope:
    """The cooldown is per (level, kind), not per level alone.

    A single per-level timer meant the APPROACHING alert silenced the TOUCHED
    that followed it a second later — losing the approach → touch → break
    escalation, which is the sequence actually worth reading. Repeats of the
    *same* observation are still throttled, which is the spam this guards.
    """

    def _event(self, kind: AlertKind, label: str, offset_seconds: float) -> AlertEvent:
        return replace(alert_event(kind), label=label, at=at(offset_seconds))

    def test_an_escalation_is_not_suppressed(self):
        budget = LevelBudget(cooldown=timedelta(minutes=20), daily_cap=9)

        assert budget.allow(self._event(AlertKind.APPROACHING, "R1", 0.0))
        # One second later, a different kind on the same level: new information.
        assert budget.allow(self._event(AlertKind.TOUCHED, "R1", 1.0))
        assert budget.allow(self._event(AlertKind.WICK_REJECTED, "R1", 2.0))

    def test_the_same_observation_repeating_is_suppressed(self):
        budget = LevelBudget(cooldown=timedelta(minutes=20), daily_cap=9)

        assert budget.allow(self._event(AlertKind.TOUCHED, "R1", 0.0))
        assert not budget.allow(self._event(AlertKind.TOUCHED, "R1", 60.0))
        assert not budget.allow(self._event(AlertKind.TOUCHED, "R1", 19 * 60.0))
        # ...until the cooldown expires.
        assert budget.allow(self._event(AlertKind.TOUCHED, "R1", 21 * 60.0))

    def test_levels_still_have_independent_cooldowns(self):
        budget = LevelBudget(cooldown=timedelta(minutes=20), daily_cap=9)

        assert budget.allow(self._event(AlertKind.TOUCHED, "R1", 0.0))
        assert budget.allow(self._event(AlertKind.TOUCHED, "S1", 1.0))

    def test_the_daily_cap_is_still_per_level_across_kinds(self):
        """The cap counts a level's total noise, whatever kind it arrives as."""
        budget = LevelBudget(cooldown=timedelta(0), daily_cap=2)

        assert budget.allow(self._event(AlertKind.APPROACHING, "R1", 0.0))
        assert budget.allow(self._event(AlertKind.TOUCHED, "R1", 1.0))
        assert not budget.allow(self._event(AlertKind.WICK_REJECTED, "R1", 2.0))
        assert budget.remaining("R1") == 0

    def test_the_composite_key_survives_a_snapshot(self):
        budget = LevelBudget(cooldown=timedelta(minutes=20), daily_cap=9)
        budget.allow(self._event(AlertKind.TOUCHED, "R1", 0.0))

        restored = LevelBudget(cooldown=timedelta(minutes=20), daily_cap=9)
        restored.restore(budget.snapshot())

        # The TOUCHED cooldown came back...
        assert not restored.allow(self._event(AlertKind.TOUCHED, "R1", 60.0))
        # ...without blocking a different kind on the same level.
        assert restored.allow(self._event(AlertKind.APPROACHING, "R1", 61.0))


class TestLevelBudgetSnapshot:
    def test_snapshot_round_trips(self):
        event = alert_event
        original = LevelBudget(cooldown=timedelta(minutes=20), daily_cap=3)
        assert original.allow(event(AlertKind.TOUCHED))
        assert original.remaining("R1") == 2

        restored = LevelBudget(cooldown=timedelta(minutes=20), daily_cap=3)
        restored.restore(original.snapshot())

        assert restored.remaining("R1") == 2
        # And the cooldown came with it.
        assert not restored.allow(event(AlertKind.TOUCHED))

    @pytest.mark.parametrize(
        "blob",
        [
            {},
            {"day": "not-a-date"},
            {"last_sent": "not-a-dict"},
            {"last_sent": {"R1": "not-a-date"}},
            {"sent_today": {"R1": "not-an-int"}},
            {"sent_today": "nonsense"},
        ],
    )
    def test_restore_tolerates_a_malformed_blob(self, blob):
        """Losing a cooldown is cosmetic; refusing to start the watcher is not."""
        budget = LevelBudget(daily_cap=3)
        budget.restore(blob)
        assert budget.remaining("R1") == 3


class TestJsonStoreRuntime:
    @pytest.fixture
    def disk(self, tmp_path) -> JsonLevelStore:
        return JsonLevelStore(directory=tmp_path, bands=bands())

    async def test_runtime_round_trips_on_disk(self, disk):
        state = RuntimeState(
            last_tick_at=SESSION_START,
            level_budget={"day": "2026-10-26", "sent_today": {"R1": 2}},
            whatsapp_sends=(SESSION_START.isoformat(),),
        )
        await disk.save_runtime(SYMBOL, state)

        back = await disk.load_runtime(SYMBOL)
        assert back.last_tick_at == SESSION_START
        assert back.level_budget["sent_today"] == {"R1": 2}
        assert back.whatsapp_sends == (SESSION_START.isoformat(),)

    async def test_an_unwritten_runtime_returns_defaults(self, disk):
        state = await disk.load_runtime(SYMBOL)
        assert state.last_tick_at is None
        assert state.level_budget == {}
        assert state.whatsapp_sends == ()

    async def test_runtime_coexists_with_marks_and_watchers(self, disk):
        await disk.save_marks(SYMBOL, (R1,), SESSION)
        await disk.save_runtime(SYMBOL, RuntimeState(last_tick_at=SESSION_START))

        assert (await disk.load_marks(SYMBOL)).marks == (R1,)
        assert (await disk.load_runtime(SYMBOL)).last_tick_at == SESSION_START

    async def test_clear_drops_the_runtime_too(self, disk):
        await disk.save_runtime(SYMBOL, RuntimeState(last_tick_at=SESSION_START))
        await disk.clear(SYMBOL)

        assert (await disk.load_runtime(SYMBOL)).last_tick_at is None

    async def test_a_garbage_runtime_section_degrades_to_defaults(self, disk, tmp_path):
        (tmp_path / "NSE_NIFTY50-INDEX.json").write_text(
            json.dumps({"version": 2, "runtime": "not-a-dict"}), encoding="utf-8"
        )
        assert (await disk.load_runtime(SYMBOL)).last_tick_at is None

    async def test_a_garbage_last_tick_degrades_to_none(self, disk, tmp_path):
        (tmp_path / "NSE_NIFTY50-INDEX.json").write_text(
            json.dumps({"version": 2, "runtime": {"last_tick_at": "nope"}}), encoding="utf-8"
        )
        assert (await disk.load_runtime(SYMBOL)).last_tick_at is None


class TestStoreContractParity:
    """The in-memory double and the disk store must agree, or the engine tests
    are verifying behaviour the real adapter does not have."""

    async def test_both_satisfy_the_same_runtime_contract(self, tmp_path):
        state = RuntimeState(
            last_tick_at=SESSION_START,
            level_budget={"sent_today": {"R1": 1}},
            whatsapp_sends=(SESSION_START.isoformat(),),
        )
        for store in (
            MemoryLevelStore(),
            JsonLevelStore(directory=tmp_path, bands=bands()),
        ):
            await store.save_runtime(SYMBOL, state)
            back = await store.load_runtime(SYMBOL)
            assert back.last_tick_at == SESSION_START
            assert back.whatsapp_sends == (SESSION_START.isoformat(),)
