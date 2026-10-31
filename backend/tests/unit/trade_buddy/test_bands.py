"""Band scaling, and the bug it exists to fix.

The centrepiece is `TestTheBugThisFixes`: the same BANKNIFTY tick sequence
replayed twice, once with NIFTY-sized point bands and once with bands scaled to
BANKNIFTY's own volatility. The first confirms a break that never happened; the
second stays silent. That difference is the whole reason this module exists.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from chartnexus.contexts.trade_buddy.application.ports import RuntimeState, Tick
from chartnexus.contexts.trade_buddy.application.watch import WatchEngine
from chartnexus.contexts.trade_buddy.domain.bands import (
    AlertOverrides,
    BandMultiples,
    BandOverrides,
    BandPolicy,
    BandSource,
    resolve_bands,
)
from chartnexus.contexts.trade_buddy.domain.budget import LevelBudget
from chartnexus.contexts.trade_buddy.domain.events import AlertKind
from chartnexus.contexts.trade_buddy.domain.level import LevelBands, LevelMark, LevelRole
from chartnexus.infrastructure.trade_buddy.clock import FakeClock
from tests.unit.trade_buddy.conftest import (
    SESSION_START,
    FixedAtr,
    MemoryLevelStore,
    RecordingSink,
    at,
    window,
)

pytestmark = pytest.mark.unit

FALLBACK = LevelBands(touch=6.0, approach=25.0, break_buffer=12.0, confirm_hold_seconds=20.0)
MULTIPLES = BandMultiples(touch=0.03, approach=0.125, break_buffer=0.06)

#: Representative ATR(14) on daily candles.
NIFTY_ATR = 200.0
BANKNIFTY_ATR = 700.0


def resolve(atr: float | None, overrides: BandOverrides | None = None):
    return resolve_bands(
        atr=atr,
        multiples=MULTIPLES,
        fallback=FALLBACK,
        overrides=overrides,
        confirm_hold_seconds=20.0,
    )


class TestScaling:
    def test_nifty_resolves_to_the_numbers_it_always_had(self):
        """The defaults are chosen so this module changes nothing for NIFTY."""
        resolved = resolve(NIFTY_ATR)

        assert resolved.bands.touch == pytest.approx(6.0)
        assert resolved.bands.approach == pytest.approx(25.0)
        assert resolved.bands.break_buffer == pytest.approx(12.0)
        assert resolved.source is BandSource.ATR

    def test_banknifty_gets_proportionally_wider_bands(self):
        resolved = resolve(BANKNIFTY_ATR)

        assert resolved.bands.touch == pytest.approx(21.0)
        assert resolved.bands.approach == pytest.approx(87.5)
        assert resolved.bands.break_buffer == pytest.approx(42.0)

    def test_the_ratio_between_instruments_matches_the_ratio_of_their_ranges(self):
        nifty = resolve(NIFTY_ATR).bands
        banknifty = resolve(BANKNIFTY_ATR).bands

        assert banknifty.break_buffer / nifty.break_buffer == pytest.approx(
            BANKNIFTY_ATR / NIFTY_ATR
        )

    def test_the_hold_does_not_scale(self):
        """A duration, not a distance. Twenty seconds is twenty seconds."""
        assert resolve(NIFTY_ATR).bands.confirm_hold_seconds == 20.0
        assert resolve(BANKNIFTY_ATR).bands.confirm_hold_seconds == 20.0


class TestDegradedMode:
    @pytest.mark.parametrize("atr", [None, 0.0, -5.0])
    def test_an_unusable_atr_falls_back_to_points(self, atr):
        resolved = resolve(atr)

        assert resolved.bands.break_buffer == FALLBACK.break_buffer
        assert resolved.source is BandSource.POINTS
        assert resolved.atr is None

    def test_the_fallback_is_reported_rather_than_hidden(self):
        """Silently applying NIFTY-sized bands to BANKNIFTY is the original bug."""
        assert resolve(None).scaled is False
        assert resolve(BANKNIFTY_ATR).scaled is True


class TestOverrides:
    def test_an_override_wins_over_the_scaled_value(self):
        resolved = resolve(BANKNIFTY_ATR, BandOverrides(break_buffer=60.0))

        assert resolved.bands.break_buffer == 60.0
        # ...and the fields left alone are still scaled.
        assert resolved.bands.touch == pytest.approx(21.0)

    def test_the_hold_can_be_overridden_too(self):
        assert (
            resolve(NIFTY_ATR, BandOverrides(confirm_hold_seconds=45.0)).bands.confirm_hold_seconds
            == 45.0
        )

    def test_an_unusable_override_degrades_instead_of_raising(self):
        """A watcher that dies over a hand-edited file has turned a cosmetic
        problem into a missed break."""
        resolved = resolve(NIFTY_ATR, BandOverrides(touch=500.0))  # touch > approach

        assert resolved.bands.touch == pytest.approx(6.0)  # the scaled value stands
        assert resolved.note is not None
        assert "ignored" in resolved.note.lower()

    def test_an_empty_override_set_changes_nothing(self):
        assert resolve(NIFTY_ATR, BandOverrides()).bands == resolve(NIFTY_ATR).bands


class TestMultiplesValidation:
    def test_a_touch_multiple_above_the_approach_multiple_is_rejected(self):
        with pytest.raises(ValueError, match="touch multiple"):
            BandMultiples(touch=0.2, approach=0.1)

    @pytest.mark.parametrize("kwargs", [{"touch": 0.0}, {"approach": -1.0}, {"break_buffer": 0.0}])
    def test_non_positive_multiples_are_rejected(self, kwargs):
        with pytest.raises(ValueError, match="positive"):
            BandMultiples(**kwargs)


# ---------------------------------------------------------------------------


BANKNIFTY_LEVEL = 52_000.0


async def replay_banknifty_chop(policy: BandPolicy, atr: float | None) -> RecordingSink:
    """BANKNIFTY loitering 13-35 points above a level for a minute.

    This is the shape that matters, and it is not a flicker: price drifts just
    over the level and *stays* in a narrow band there, which is what an index
    does all day. A 22-point wander on a 52,000 index with a ~650-point daily
    range is the spread breathing — it is not a break of anything.

    But it sits continuously above a 12-point buffer, so a NIFTY-sized band
    confirms it. A 42-point band never even registers it as pending.
    """
    store = MemoryLevelStore()
    store.mark("BANKNIFTY", LevelMark(label="R1", price=BANKNIFTY_LEVEL, role=LevelRole.RESISTANCE))
    sink = RecordingSink()
    clock = FakeClock(SESSION_START)
    engine = WatchEngine(
        symbol="BANKNIFTY",
        policy=policy,
        window=window(),
        store=store,
        sink=sink,
        clock=clock,
        atr_source=FixedAtr(atr),
    )
    await engine.load()

    # Open below the level so this is a break path, not an opening gap.
    offset = 0.0
    await engine.on_tick(Tick(symbol="BANKNIFTY", price=51_900.0, at=at(offset)))

    # Then wander between +13 and +35 for a minute. Never far enough from the
    # level to mean anything, never back below it either.
    for step in range(30):
        offset += 2.0
        price = BANKNIFTY_LEVEL + (13.0 if step % 2 == 0 else 35.0)
        clock.set(at(offset))
        while clock.monotonic() < offset:
            clock.advance(1.0)
        await engine.on_tick(Tick(symbol="BANKNIFTY", price=price, at=at(offset)))

    return sink


class TestTheBugThisFixes:
    async def test_nifty_sized_bands_confirm_a_break_that_never_happened(self):
        """The bug, demonstrated. A 12-point buffer on BANKNIFTY is noise-width.

        Price never moves more than 15 points from the level — well inside the
        spread's daily wander — yet it clears a 12-point buffer and holds past
        the confirmation window, so the engine reports a confirmed break.
        """
        points_only = BandPolicy(multiples=MULTIPLES, fallback=FALLBACK, confirm_hold_seconds=20.0)
        sink = await replay_banknifty_chop(points_only, atr=None)

        assert AlertKind.BREAK_CONFIRMED in sink.kinds

    async def test_banknifty_scaled_bands_stay_silent_through_the_same_chop(self):
        """The fix. A 42-point buffer is wider than the noise, so nothing fires."""
        scaled = BandPolicy(multiples=MULTIPLES, fallback=FALLBACK, confirm_hold_seconds=20.0)
        sink = await replay_banknifty_chop(scaled, atr=BANKNIFTY_ATR)

        assert AlertKind.BREAK_CONFIRMED not in sink.kinds
        assert AlertKind.WICK_REJECTED not in sink.kinds

    async def test_the_scaled_run_still_reports_the_level_as_touched(self):
        """Silent about the break, not silent about the level.

        A wider buffer must not blind the watcher: +13 is inside BANKNIFTY's
        21-point touch band, so the level is still reported as touched. The
        point-band run never says this at all — it jumps straight to a break,
        which is the missed-touch half of the same bug.
        """
        scaled = BandPolicy(multiples=MULTIPLES, fallback=FALLBACK, confirm_hold_seconds=20.0)
        sink = await replay_banknifty_chop(scaled, atr=BANKNIFTY_ATR)

        assert AlertKind.TOUCHED in sink.kinds

    async def test_a_real_banknifty_break_still_confirms(self):
        """The other half: scaling up must not make breaks unreachable."""
        store = MemoryLevelStore()
        store.mark(
            "BANKNIFTY", LevelMark(label="R1", price=BANKNIFTY_LEVEL, role=LevelRole.RESISTANCE)
        )
        sink = RecordingSink()
        clock = FakeClock(SESSION_START)
        engine = WatchEngine(
            symbol="BANKNIFTY",
            policy=BandPolicy(multiples=MULTIPLES, fallback=FALLBACK, confirm_hold_seconds=20.0),
            window=window(),
            store=store,
            sink=sink,
            clock=clock,
            atr_source=FixedAtr(BANKNIFTY_ATR),
        )
        await engine.load()

        # 51,900 → 52,100: a 200-point move, decisively past the 42-point buffer.
        for price, offset in [(51_900.0, 0.0), (52_100.0, 10.0), (52_120.0, 31.0)]:
            clock.set(at(offset))
            while clock.monotonic() < offset:
                clock.advance(1.0)
            await engine.on_tick(Tick(symbol="BANKNIFTY", price=price, at=at(offset)))

        assert sink.kinds.count(AlertKind.BREAK_CONFIRMED) == 1


class TestEngineIntegration:
    async def test_the_engine_reports_how_its_bands_were_derived(self, store, sink):
        store.mark("NIFTY", LevelMark(label="R1", price=24_700.0, role=LevelRole.RESISTANCE))
        engine = WatchEngine(
            symbol="NIFTY",
            policy=BandPolicy(multiples=MULTIPLES, fallback=FALLBACK, confirm_hold_seconds=20.0),
            window=window(),
            store=store,
            sink=sink,
            clock=FakeClock(SESSION_START),
            atr_source=FixedAtr(NIFTY_ATR),
        )
        await engine.load()

        assert engine.resolved.source is BandSource.ATR
        assert engine.resolved.atr == NIFTY_ATR

    async def test_a_cached_atr_is_used_instead_of_a_fetch(self, store, sink):
        """A restart must not drop to point bands because the provider was slow."""
        store.mark("NIFTY", LevelMark(label="R1", price=24_700.0, role=LevelRole.RESISTANCE))
        store.runtime["NIFTY"] = RuntimeState(atr=NIFTY_ATR)
        source = FixedAtr(None)

        engine = WatchEngine(
            symbol="NIFTY",
            policy=BandPolicy(multiples=MULTIPLES, fallback=FALLBACK, confirm_hold_seconds=20.0),
            window=window(),
            store=store,
            sink=sink,
            clock=FakeClock(SESSION_START),
            atr_source=source,
        )
        await engine.load()

        assert source.calls == 0
        assert engine.resolved.atr == NIFTY_ATR

    async def test_bands_are_pushed_onto_resumed_watchers(self, store, sink):
        """A watcher rebuilt from disk must not keep the store's placeholder bands."""
        store.mark(
            "BANKNIFTY", LevelMark(label="R1", price=BANKNIFTY_LEVEL, role=LevelRole.RESISTANCE)
        )
        engine = WatchEngine(
            symbol="BANKNIFTY",
            policy=BandPolicy(multiples=MULTIPLES, fallback=FALLBACK, confirm_hold_seconds=20.0),
            window=window(),
            store=store,
            sink=sink,
            clock=FakeClock(SESSION_START),
            atr_source=FixedAtr(BANKNIFTY_ATR),
        )
        await engine.load()

        assert all(w.bands.break_buffer == pytest.approx(42.0) for w in engine.watchers)

    async def test_a_per_instrument_override_is_loaded_from_the_store(self, store, sink):
        store.mark(
            "BANKNIFTY", LevelMark(label="R1", price=BANKNIFTY_LEVEL, role=LevelRole.RESISTANCE)
        )
        store.overrides["BANKNIFTY"] = AlertOverrides(bands=BandOverrides(break_buffer=75.0))
        engine = WatchEngine(
            symbol="BANKNIFTY",
            policy=BandPolicy(multiples=MULTIPLES, fallback=FALLBACK, confirm_hold_seconds=20.0),
            window=window(),
            store=store,
            sink=sink,
            clock=FakeClock(SESSION_START),
            atr_source=FixedAtr(BANKNIFTY_ATR),
        )
        await engine.load()

        assert engine.bands.break_buffer == 75.0


class TestInstrumentIsolation:
    async def test_one_instruments_ticks_never_touch_anothers_state(self, sink):
        """Three indices, one store, no leakage between them."""
        store = MemoryLevelStore()
        store.mark("NIFTY", LevelMark(label="R1", price=24_700.0, role=LevelRole.RESISTANCE))
        store.mark("BANKNIFTY", LevelMark(label="R1", price=52_000.0, role=LevelRole.RESISTANCE))
        clock = FakeClock(SESSION_START)

        sinks = {name: RecordingSink() for name in ("NIFTY", "BANKNIFTY")}
        engines = {}
        for name, atr in (("NIFTY", NIFTY_ATR), ("BANKNIFTY", BANKNIFTY_ATR)):
            engines[name] = WatchEngine(
                symbol=name,
                policy=BandPolicy(
                    multiples=MULTIPLES, fallback=FALLBACK, confirm_hold_seconds=20.0
                ),
                window=window(),
                store=store,
                sink=sinks[name],
                clock=clock,
                atr_source=FixedAtr(atr),
            )
            await engines[name].load()

        await engines["NIFTY"].on_tick(Tick(symbol="NIFTY", price=24_698.0, at=at(0.0)))

        assert sinks["NIFTY"].kinds == [AlertKind.TOUCHED]
        assert sinks["BANKNIFTY"].kinds == []

    async def test_each_instrument_keeps_its_own_bands(self, sink):
        store = MemoryLevelStore()
        for name, price in (("NIFTY", 24_700.0), ("BANKNIFTY", 52_000.0)):
            store.mark(name, LevelMark(label="R1", price=price, role=LevelRole.RESISTANCE))

        resolved = {}
        for name, atr in (("NIFTY", NIFTY_ATR), ("BANKNIFTY", BANKNIFTY_ATR)):
            engine = WatchEngine(
                symbol=name,
                policy=BandPolicy(
                    multiples=MULTIPLES, fallback=FALLBACK, confirm_hold_seconds=20.0
                ),
                window=window(),
                store=store,
                sink=RecordingSink(),
                clock=FakeClock(SESSION_START),
                atr_source=FixedAtr(atr),
            )
            await engine.load()
            resolved[name] = engine.bands.break_buffer

        assert resolved["NIFTY"] == pytest.approx(12.0)
        assert resolved["BANKNIFTY"] == pytest.approx(42.0)


class TestThrottleOverrides:
    """Cooldown and cap are per-instrument too.

    They do not *scale* with volatility — a cap is about the reader's patience,
    not about price — but a day spent in BANKNIFTY is a good reason to want it
    noisier there and unchanged elsewhere.
    """

    async def test_a_cooldown_override_reaches_the_budget(self, store, sink):
        store.mark(
            "BANKNIFTY", LevelMark(label="R1", price=BANKNIFTY_LEVEL, role=LevelRole.RESISTANCE)
        )
        store.overrides["BANKNIFTY"] = AlertOverrides(cooldown_minutes=5.0)
        engine = WatchEngine(
            symbol="BANKNIFTY",
            policy=BandPolicy(multiples=MULTIPLES, fallback=FALLBACK, confirm_hold_seconds=20.0),
            window=window(),
            store=store,
            sink=sink,
            clock=FakeClock(SESSION_START),
            budget=LevelBudget(cooldown=timedelta(minutes=20), daily_cap=3),
            atr_source=FixedAtr(BANKNIFTY_ATR),
        )
        await engine.load()

        assert engine.budget.cooldown == timedelta(minutes=5)

    async def test_a_cap_override_reaches_the_budget(self, store, sink):

        store.mark("NIFTY", LevelMark(label="R1", price=24_700.0, role=LevelRole.RESISTANCE))
        store.overrides["NIFTY"] = AlertOverrides(daily_alert_cap=9)
        engine = WatchEngine(
            symbol="NIFTY",
            policy=BandPolicy(multiples=MULTIPLES, fallback=FALLBACK, confirm_hold_seconds=20.0),
            window=window(),
            store=store,
            sink=sink,
            clock=FakeClock(SESSION_START),
            budget=LevelBudget(daily_cap=3),
            atr_source=FixedAtr(NIFTY_ATR),
        )
        await engine.load()

        assert engine.budget.daily_cap == 9

    async def test_an_absent_override_leaves_the_global_value(self, store, sink):
        store.mark("NIFTY", LevelMark(label="R1", price=24_700.0, role=LevelRole.RESISTANCE))
        engine = WatchEngine(
            symbol="NIFTY",
            policy=BandPolicy(multiples=MULTIPLES, fallback=FALLBACK, confirm_hold_seconds=20.0),
            window=window(),
            store=store,
            sink=sink,
            clock=FakeClock(SESSION_START),
            budget=LevelBudget(cooldown=timedelta(minutes=20), daily_cap=3),
            atr_source=FixedAtr(NIFTY_ATR),
        )
        await engine.load()

        assert engine.budget.cooldown == timedelta(minutes=20)
        assert engine.budget.daily_cap == 3

    async def test_a_zero_cooldown_is_honoured_rather_than_treated_as_unset(self, store, sink):
        """Zero means "no cooldown", which is a setting, not a blank field."""
        store.mark("NIFTY", LevelMark(label="R1", price=24_700.0, role=LevelRole.RESISTANCE))
        store.overrides["NIFTY"] = AlertOverrides(cooldown_minutes=0.0)
        engine = WatchEngine(
            symbol="NIFTY",
            policy=BandPolicy(multiples=MULTIPLES, fallback=FALLBACK, confirm_hold_seconds=20.0),
            window=window(),
            store=store,
            sink=sink,
            clock=FakeClock(SESSION_START),
            budget=LevelBudget(cooldown=timedelta(minutes=20)),
            atr_source=FixedAtr(NIFTY_ATR),
        )
        await engine.load()

        assert engine.budget.cooldown == timedelta(0)


class TestAlertOverridesShape:
    def test_an_empty_set_is_empty(self):
        assert AlertOverrides().empty is True

    @pytest.mark.parametrize(
        "overrides",
        [
            AlertOverrides(bands=BandOverrides(touch=5.0)),
            AlertOverrides(cooldown_minutes=5.0),
            AlertOverrides(daily_alert_cap=1),
            AlertOverrides(cooldown_minutes=0.0),
        ],
    )
    def test_any_set_field_makes_it_non_empty(self, overrides):
        assert overrides.empty is False
