"""A level the user marked by hand, and the bands that surround it.

Six of these per instrument per morning: S1/S2/S3 below, R1/R2/R3 above. The
marked price is the only input the user gives; everything else here is a band
derived from configuration.

The role (support or resistance) is *mutable state*, not a property of the
label. ``R2`` names which level it is; after price breaks and holds above it,
that same level is support. Keeping the label and the role separate is what lets
an alert say "R2 broken — now acting as support" without renaming anything.

Pure: no settings, no clock, no I/O. The bands arrive as plain floats so the
same level can be replayed under different thresholds in a test.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class LevelRole(StrEnum):
    """What a level is currently expected to do to price."""

    SUPPORT = "support"
    RESISTANCE = "resistance"

    @property
    def inverted(self) -> LevelRole:
        """The role this one becomes after a confirmed break."""
        return LevelRole.RESISTANCE if self is LevelRole.SUPPORT else LevelRole.SUPPORT

    @property
    def break_sign(self) -> int:
        """Which direction counts as breaking *through* this level.

        Resistance breaks upward (+1), support breaks downward (-1). Every
        comparison in the state machine is written once against this sign
        rather than twice with the inequality flipped, because two mirrored
        branches is where a sign error hides.
        """
        return 1 if self is LevelRole.RESISTANCE else -1


@dataclass(frozen=True, slots=True)
class LevelBands:
    """The three distances that turn a price into an event.

    All in index points, all config-driven. Validated on construction because a
    nonsensical band set (a touch band wider than the approach band, say) would
    produce events in an order no reader could interpret.
    """

    #: Inside ±this many points of the level → TOUCHED.
    touch: float = 6.0
    #: Inside this many points of the level → APPROACHING.
    approach: float = 25.0
    #: Price must pass this many points *beyond* the level to start a break.
    break_buffer: float = 12.0
    #: ...and stay beyond it continuously for this long to confirm one.
    confirm_hold_seconds: float = 20.0

    def __post_init__(self) -> None:
        if self.touch <= 0 or self.approach <= 0 or self.break_buffer <= 0:
            raise ValueError("touch, approach and break_buffer must all be positive")
        if self.confirm_hold_seconds < 0:
            raise ValueError("confirm_hold_seconds cannot be negative")
        if self.touch > self.approach:
            raise ValueError(
                f"touch band ({self.touch}) must not exceed approach band ({self.approach}); "
                "price would register TOUCHED before it ever registered APPROACHING"
            )


@dataclass(frozen=True, slots=True)
class LevelMark:
    """One marked level: its label, its price, and the role it starts the day in."""

    label: str
    price: float
    role: LevelRole

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("a level needs a label")
        if self.price <= 0:
            raise ValueError(f"level {self.label!r} has a non-positive price: {self.price}")

    def break_threshold(self, bands: LevelBands, sign: int) -> float:
        """The price beyond which a break in direction ``sign`` begins.

        ``sign`` is taken explicitly rather than read off a role, because a
        confirmed break *flips* the role: after resistance breaks upward the
        level is support, and asking the new role which way it breaks would
        give the opposite of the move actually in progress. The state machine
        therefore records the sign when the break starts and keeps using it.
        """
        return self.price + sign * bands.break_buffer

    def reclaim_threshold(self, bands: LevelBands, sign: int) -> float:
        """The price beyond which a level broken in direction ``sign`` is reclaimed.

        The mirror of :meth:`break_threshold`, against the *same* sign: a
        resistance that broke upward (``+1``) is reclaimed by falling back below
        ``level - buffer``. Requiring the full buffer on the way back is the
        hysteresis — price hovering on the level itself can never flip the
        state, only a decisive move can.
        """
        return self.price - sign * bands.break_buffer


@dataclass(frozen=True, slots=True)
class MarkSet:
    """One morning's marked levels, and the session they were marked for.

    The date is the whole point. Levels are a daily artefact — the prices that
    matter today are not the prices that mattered on Friday — but nothing in
    the storage expired them, so a watcher restarted on Monday would compare
    live price against Friday's numbers and alert on them with full
    confidence. That is the worst failure this module has: not silence, which
    is at least visible, but assured alerts about prices nobody is watching.

    ``marked_on`` is ``None`` for marks saved before this was recorded. Those
    are treated as stale rather than current: assuming a set of levels is
    today's when nothing says so is exactly the mistake being fixed.
    """

    marks: tuple[LevelMark, ...] = ()
    marked_on: date | None = None

    def __bool__(self) -> bool:
        return bool(self.marks)

    def __len__(self) -> int:
        return len(self.marks)

    def __iter__(self) -> Iterator[LevelMark]:
        return iter(self.marks)

    def is_current(self, session: date) -> bool:
        """True when these levels were marked for the session being watched."""
        return self.marked_on is not None and self.marked_on == session

    def is_stale(self, session: date) -> bool:
        """True when levels exist but belong to an earlier session.

        An empty set is not stale — it is unmarked, which the page reports
        differently because the fix is different: mark some, versus re-mark
        the ones you have.
        """
        return bool(self.marks) and not self.is_current(session)
