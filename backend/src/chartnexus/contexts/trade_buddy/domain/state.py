"""The per-level state machine. This is the module the whole feature rests on.

One :class:`LevelWatcher` per marked level. It is fed ``(price, elapsed)`` and
returns the events that price justified — nothing more. No clock, no I/O, no
settings: ``elapsed`` is a monotonic second count supplied by the caller, which
is what makes a twenty-second hold testable in microseconds and immune to an
NTP step mid-session.

The states::

    IDLE ──within approach──> APPROACHING ──within touch──> TOUCHED
                                                               │
                                                   past break threshold
                                                               ▼
                                                        BREAK_PENDING
                                              ┌────────────────┴────────────────┐
                                   held for confirm_hold            back inside before hold
                                              ▼                                ▼
                                           BROKEN                      WICK_REJECTED
                                      (role flips)                   (returns to TOUCHED)
                                              │
                                 back past buffer the other way
                                              ▼
                                         RECLAIMED
                                      (role flips back)

Three properties this is built to guarantee, each pinned by a test:

**A wick cannot confirm.** The hold is measured from the moment price first
passed the threshold and is *reset* the instant price comes back inside it.
Accumulated time is never carried across a re-entry, so twenty separate
one-second pokes do not add up to a twenty-second hold.

**Oscillation cannot spam.** Leaving ``BROKEN`` requires crossing the buffer on
the *opposite* side, not merely re-touching the level. Price chopping on the
level itself therefore produces no further events at all, because ``BROKEN`` has
no transition back to ``TOUCHED``.

**A break is never silently dropped.** Throttling lives entirely outside this
module — the watcher reports what happened and the budget decides what is sent.
Mixing the two is how a cap on approach alerts ends up swallowing a real break.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from chartnexus.contexts.trade_buddy.domain.events import AlertEvent, AlertKind
from chartnexus.contexts.trade_buddy.domain.level import LevelBands, LevelMark, LevelRole


class LevelState(StrEnum):
    """Where one level currently stands relative to price."""

    IDLE = "idle"
    APPROACHING = "approaching"
    TOUCHED = "touched"
    BREAK_PENDING = "break_pending"
    BROKEN = "broken"


@dataclass(slots=True)
class LevelWatcher:
    """One marked level's live state. Mutated by :meth:`observe`.

    Serialisable by design — :mod:`infrastructure.trade_buddy.json_level_store`
    round-trips these fields so a restart mid-session resumes with the same
    states rather than re-firing everything it already reported.
    """

    symbol: str
    mark: LevelMark
    bands: LevelBands
    #: Current role. Starts as marked, flips on every confirmed break/reclaim.
    role: LevelRole = field(init=False)
    state: LevelState = LevelState.IDLE
    #: Monotonic second at which price first passed the break threshold, or
    #: ``None`` whenever no break is in progress. Reset — never accumulated —
    #: when price returns inside the threshold.
    pending_since: float | None = None
    #: The direction of the break that is pending or confirmed. Held because a
    #: confirmed break flips ``role``, so the role can no longer tell us which
    #: way price went. ``None`` when nothing is pending or broken.
    break_sign: int | None = None

    def __post_init__(self) -> None:
        self.role = self.mark.role

    # -- queries ------------------------------------------------------------

    @property
    def broken(self) -> bool:
        return self.state is LevelState.BROKEN

    def _within(self, price: float, band: float) -> bool:
        return abs(price - self.mark.price) <= band

    def _past_break(self, price: float, sign: int) -> bool:
        """True when ``price`` is strictly beyond the break threshold."""
        threshold = self.mark.break_threshold(self.bands, sign)
        return (price > threshold) if sign > 0 else (price < threshold)

    def _past_reclaim(self, price: float, sign: int) -> bool:
        """True when ``price`` is strictly beyond the reclaim threshold."""
        threshold = self.mark.reclaim_threshold(self.bands, sign)
        return (price < threshold) if sign > 0 else (price > threshold)

    # -- the machine --------------------------------------------------------

    def observe(self, price: float, elapsed: float, at: datetime) -> list[AlertEvent]:
        """Feed one tick in. Returns the events it justified, in order.

        ``elapsed`` is monotonic seconds from any fixed origin; only differences
        are ever used. ``at`` is the wall-clock instant, carried onto events for
        display and never used for timing.
        """
        if self.state is LevelState.BROKEN:
            return self._observe_broken(price, at)
        if self.state is LevelState.BREAK_PENDING:
            return self._observe_pending(price, elapsed, at)
        return self._observe_open(price, elapsed, at)

    def _observe_open(self, price: float, elapsed: float, at: datetime) -> list[AlertEvent]:
        """IDLE / APPROACHING / TOUCHED — the level has not been broken."""
        sign = self.role.break_sign

        # A break outranks a touch: price beyond the buffer is also, strictly,
        # within no band at all, and checking it first keeps a fast move from
        # being reported as a touch it has already left behind.
        if self._past_break(price, sign):
            self.state = LevelState.BREAK_PENDING
            self.pending_since = elapsed
            self.break_sign = sign
            # Nothing is emitted yet. A pending break is not a finding until it
            # survives the hold, and announcing it here is precisely the false
            # alert this module exists to avoid.
            return []

        if self._within(price, self.bands.touch):
            if self.state is LevelState.TOUCHED:
                return []
            self.state = LevelState.TOUCHED
            return [self._event(AlertKind.TOUCHED, price, at)]

        if self._within(price, self.bands.approach):
            # Coming *back* from a touch into the wider band is not a new
            # approach — the reader already knows price is here.
            if self.state in (LevelState.APPROACHING, LevelState.TOUCHED):
                return []
            self.state = LevelState.APPROACHING
            return [self._event(AlertKind.APPROACHING, price, at)]

        self.state = LevelState.IDLE
        return []

    def _observe_pending(self, price: float, elapsed: float, at: datetime) -> list[AlertEvent]:
        """BREAK_PENDING — price is beyond the buffer; is it staying there?"""
        sign = self.break_sign
        started = self.pending_since
        if sign is None or started is None:  # pragma: no cover — guarded by construction
            raise AssertionError("BREAK_PENDING without a sign or a start time")

        if not self._past_break(price, sign):
            # Came back inside before the hold completed. The timer is dropped,
            # not paused: a wick is a wick however many times it recurs.
            self.state = LevelState.TOUCHED
            self.pending_since = None
            self.break_sign = None
            return [self._event(AlertKind.WICK_REJECTED, price, at)]

        if elapsed - started < self.bands.confirm_hold_seconds:
            return []

        return [self._confirm_break(price, at)]

    def _observe_broken(self, price: float, at: datetime) -> list[AlertEvent]:
        """BROKEN — the only way out is a decisive move back the other way."""
        sign = self.break_sign
        if sign is None:  # pragma: no cover — guarded by construction
            raise AssertionError("BROKEN without a break sign")

        if not self._past_reclaim(price, sign):
            # Includes price sitting right on the level. Deliberately silent:
            # this is the oscillation case, and any event here would be the
            # spam the hysteresis exists to prevent.
            return []

        before = self.role
        self.role = self.role.inverted
        self.state = LevelState.TOUCHED
        self.pending_since = None
        self.break_sign = None
        return [self._event(AlertKind.RECLAIMED, price, at, role_before=before)]

    # -- transitions shared with the gap path -------------------------------

    def _confirm_break(self, price: float, at: datetime) -> AlertEvent:
        before = self.role
        self.role = self.role.inverted
        self.state = LevelState.BROKEN
        self.pending_since = None
        return self._event(AlertKind.BREAK_CONFIRMED, price, at, role_before=before)

    def gap_through(self, price: float, at: datetime) -> AlertEvent:
        """Record that the session *opened* beyond this level.

        No touch ever happened and no hold can be measured, so the normal path
        would sit in ``IDLE`` and report nothing at all — the level would be
        silently skipped for the whole session. The first price of the day is
        treated as a completed break: it is already past the buffer and there is
        no earlier state for it to have passed through.
        """
        sign = self.role.break_sign
        before = self.role
        self.role = self.role.inverted
        self.state = LevelState.BROKEN
        self.break_sign = sign
        self.pending_since = None
        return self._event(AlertKind.GAPPED_THROUGH, price, at, role_before=before)

    def _event(
        self,
        kind: AlertKind,
        price: float,
        at: datetime,
        *,
        role_before: LevelRole | None = None,
    ) -> AlertEvent:
        return AlertEvent(
            kind=kind,
            symbol=self.symbol,
            label=self.mark.label,
            level_price=self.mark.price,
            price=price,
            role_before=role_before if role_before is not None else self.role,
            role_after=self.role,
            at=at,
        )
