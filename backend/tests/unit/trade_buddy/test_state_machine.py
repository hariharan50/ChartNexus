"""The state machine, driven by scripted tick sequences.

Every test asserts the *exact* events emitted, not merely that something was. A
test that accepts "at least one break alert" would pass while the engine sent
four, and spam is one of the two failure modes this module exists to prevent.

No sleeping anywhere: ``elapsed`` is supplied by the test, so a twenty-second
hold is three function calls.
"""

from __future__ import annotations

import pytest

from chartnexus.contexts.trade_buddy.domain.events import AlertKind
from chartnexus.contexts.trade_buddy.domain.level import LevelBands, LevelRole
from chartnexus.contexts.trade_buddy.domain.state import LevelState
from tests.unit.trade_buddy.conftest import at, watcher

pytestmark = pytest.mark.unit

# R1 sits at 24650 with a 12-point buffer, so a break needs > 24662, and a
# reclaim of that break needs < 24638.
LEVEL = 24_650.0
BREAK_ABOVE = 24_663.0
RECLAIM_BELOW = 24_637.0


def _feed(level_watcher, ticks):  # type: ignore[no-untyped-def]
    """Replay ``(price, elapsed)`` pairs and collect every event emitted."""
    collected = []
    for price, elapsed in ticks:
        collected.extend(level_watcher.observe(price, elapsed, at(elapsed)))
    return collected


class TestApproachAndTouch:
    def test_approach_then_touch_each_fire_once(self):
        level = watcher(LEVEL)

        events = _feed(
            level,
            [
                (24_600.0, 0),  # 50 away — outside both bands
                (24_630.0, 1),  # 20 away — inside approach
                (24_632.0, 2),  # still inside approach, no repeat
                (24_647.0, 3),  # 3 away — inside touch
                (24_648.0, 4),  # still touching, no repeat
            ],
        )

        assert [event.kind for event in events] == [
            AlertKind.APPROACHING,
            AlertKind.TOUCHED,
        ]

    def test_falling_back_from_touch_into_approach_is_not_a_new_approach(self):
        """The reader already knows price is here; saying so again is noise."""
        level = watcher(LEVEL)

        events = _feed(
            level,
            [
                (24_630.0, 0),  # approach
                (24_648.0, 1),  # touch
                (24_630.0, 2),  # back out to the approach band
                (24_628.0, 3),
            ],
        )

        assert [event.kind for event in events] == [
            AlertKind.APPROACHING,
            AlertKind.TOUCHED,
        ]

    def test_leaving_entirely_then_returning_approaches_again(self):
        level = watcher(LEVEL)

        events = _feed(
            level,
            [
                (24_630.0, 0),  # approach
                (24_500.0, 1),  # well clear — back to IDLE
                (24_630.0, 2),  # a genuinely new approach
            ],
        )

        assert [event.kind for event in events] == [
            AlertKind.APPROACHING,
            AlertKind.APPROACHING,
        ]


class TestCleanBreak:
    def test_break_confirms_only_after_the_full_hold(self):
        level = watcher(LEVEL)

        # Past the buffer at t=0, held continuously; hold is 20s.
        events = _feed(
            level,
            [
                (BREAK_ABOVE, 0.0),
                (24_665.0, 10.0),  # 10s in — not yet
                (24_670.0, 19.9),  # 19.9s in — still not yet
            ],
        )
        assert events == []
        assert level.state is LevelState.BREAK_PENDING

        # Crossing the hold boundary is what confirms it.
        confirmed = level.observe(24_672.0, 20.0, at(20.0))
        assert [event.kind for event in confirmed] == [AlertKind.BREAK_CONFIRMED]
        assert level.state is LevelState.BROKEN

    def test_a_confirmed_break_fires_exactly_once_however_long_price_stays(self):
        level = watcher(LEVEL)

        events = _feed(
            level,
            [(BREAK_ABOVE, 0.0), (24_672.0, 20.0)] + [(24_680.0 + n, 30.0 + n) for n in range(25)],
        )

        assert [event.kind for event in events] == [AlertKind.BREAK_CONFIRMED]

    def test_resistance_becomes_support_and_the_event_says_so(self):
        level = watcher(LEVEL, LevelRole.RESISTANCE)

        _feed(level, [(BREAK_ABOVE, 0.0)])
        (event,) = level.observe(24_672.0, 20.0, at(20.0))

        assert event.kind is AlertKind.BREAK_CONFIRMED
        assert event.role_before is LevelRole.RESISTANCE
        assert event.role_after is LevelRole.SUPPORT
        assert event.flipped
        assert level.role is LevelRole.SUPPORT

    def test_support_breaks_downward_not_upward(self):
        """The sign must follow the role, or every support alert is inverted."""
        level = watcher(LEVEL, LevelRole.SUPPORT)

        # Well *above* a support is not a break of it, however far.
        assert _feed(level, [(24_800.0, 0.0), (24_900.0, 30.0)]) == []

        # Below the buffer, held, is.
        _feed(level, [(24_637.0, 40.0)])
        (event,) = level.observe(24_630.0, 60.0, at(60.0))
        assert event.kind is AlertKind.BREAK_CONFIRMED
        assert event.role_after is LevelRole.RESISTANCE


class TestWickRejection:
    def test_a_wick_that_retreats_before_the_hold_does_not_confirm(self):
        level = watcher(LEVEL)

        events = _feed(
            level,
            [
                (BREAK_ABOVE, 0.0),  # past the buffer — pending
                (24_670.0, 5.0),  # still past, 5s in
                (24_655.0, 8.0),  # back inside before 20s — rejected
            ],
        )

        assert [event.kind for event in events] == [AlertKind.WICK_REJECTED]
        assert level.state is LevelState.TOUCHED
        assert level.pending_since is None
        assert level.break_sign is None

    def test_repeated_pokes_do_not_accumulate_into_a_hold(self):
        """Twenty one-second pokes are not a twenty-second hold.

        This is the test that pins the timer *reset*. An implementation that
        paused and resumed the hold instead of dropping it would confirm a
        break here, which is the false alert that matters most.
        """
        level = watcher(LEVEL)
        ticks = []
        elapsed = 0.0
        for _ in range(20):
            ticks.append((BREAK_ABOVE, elapsed))  # out past the buffer
            ticks.append((24_655.0, elapsed + 1.0))  # and straight back in
            elapsed += 2.0

        events = _feed(level, ticks)

        assert all(event.kind is AlertKind.WICK_REJECTED for event in events)
        assert AlertKind.BREAK_CONFIRMED not in [event.kind for event in events]
        assert level.state is LevelState.TOUCHED

    def test_a_wick_then_a_genuine_break_still_confirms(self):
        level = watcher(LEVEL)

        events = _feed(
            level,
            [
                (BREAK_ABOVE, 0.0),
                (24_650.0, 3.0),  # rejected
                (BREAK_ABOVE, 10.0),  # new attempt, timer restarts here
                (24_670.0, 29.0),  # only 19s into the new attempt
            ],
        )
        assert [event.kind for event in events] == [AlertKind.WICK_REJECTED]

        (confirmed,) = level.observe(24_675.0, 30.0, at(30.0))
        assert confirmed.kind is AlertKind.BREAK_CONFIRMED


class TestWhipsawHysteresis:
    def test_oscillating_on_a_broken_level_emits_nothing(self):
        """The spam case. A broken level must stay broken until decisively reclaimed."""
        level = watcher(LEVEL)
        _feed(level, [(BREAK_ABOVE, 0.0)])
        level.observe(24_672.0, 20.0, at(20.0))  # confirmed

        # Now chop across the level itself, inside the buffer on both sides.
        chop = []
        elapsed = 30.0
        for offset in (5.0, -5.0, 8.0, -8.0, 2.0, -2.0, 10.0, -10.0):
            chop.append((LEVEL + offset, elapsed))
            elapsed += 1.0

        assert _feed(level, chop) == []
        assert level.state is LevelState.BROKEN

    def test_oscillating_before_any_break_does_not_repeat_touches(self):
        level = watcher(LEVEL)
        chop = []
        elapsed = 0.0
        for offset in (3.0, -3.0, 4.0, -4.0, 1.0, -1.0):
            chop.append((LEVEL + offset, elapsed))
            elapsed += 1.0

        events = _feed(level, chop)

        assert [event.kind for event in events] == [AlertKind.TOUCHED]


class TestReclaim:
    def test_break_then_reclaim_fires_once_each(self):
        level = watcher(LEVEL)

        _feed(level, [(BREAK_ABOVE, 0.0)])
        (broken,) = level.observe(24_672.0, 20.0, at(20.0))
        (reclaimed,) = level.observe(RECLAIM_BELOW, 60.0, at(60.0))

        assert broken.kind is AlertKind.BREAK_CONFIRMED
        assert reclaimed.kind is AlertKind.RECLAIMED
        assert reclaimed.role_before is LevelRole.SUPPORT
        assert reclaimed.role_after is LevelRole.RESISTANCE
        assert level.role is LevelRole.RESISTANCE

    def test_reclaim_needs_the_full_buffer_not_just_the_level(self):
        level = watcher(LEVEL)
        _feed(level, [(BREAK_ABOVE, 0.0)])
        level.observe(24_672.0, 20.0, at(20.0))

        # Just below the level, but inside the buffer — not a reclaim.
        assert level.observe(24_645.0, 30.0, at(30.0)) == []
        assert level.observe(24_639.0, 31.0, at(31.0)) == []
        assert level.state is LevelState.BROKEN

        # Past it — reclaimed.
        (event,) = level.observe(24_637.0, 32.0, at(32.0))
        assert event.kind is AlertKind.RECLAIMED

    def test_a_reclaimed_level_can_break_again(self):
        """Hysteresis must not latch permanently — a second genuine break counts."""
        level = watcher(LEVEL)
        _feed(level, [(BREAK_ABOVE, 0.0)])
        level.observe(24_672.0, 20.0, at(20.0))  # broken
        level.observe(RECLAIM_BELOW, 60.0, at(60.0))  # reclaimed, now resistance again

        _feed(level, [(BREAK_ABOVE, 100.0)])
        (again,) = level.observe(24_675.0, 120.0, at(120.0))

        assert again.kind is AlertKind.BREAK_CONFIRMED
        assert level.role is LevelRole.SUPPORT


class TestBandValidation:
    def test_a_touch_band_wider_than_the_approach_band_is_rejected(self):
        with pytest.raises(ValueError, match="touch band"):
            LevelBands(touch=30.0, approach=25.0)

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"touch": 0.0},
            {"approach": -1.0},
            {"break_buffer": 0.0},
        ],
    )
    def test_non_positive_bands_are_rejected(self, kwargs):
        with pytest.raises(ValueError, match="positive"):
            LevelBands(**kwargs)

    def test_a_negative_hold_is_rejected(self):
        with pytest.raises(ValueError, match="confirm_hold_seconds"):
            LevelBands(confirm_hold_seconds=-1.0)
