"""Commands the HTTP layer issues: mark levels, read them, clear them, test-fire.

Thin on purpose. The interesting behaviour is in the domain and the engine; these
exist so the router never touches a store or a watcher directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from chartnexus.contexts.trade_buddy.application.ports import AlertSink, Clock, LevelStore
from chartnexus.contexts.trade_buddy.domain.bands import AlertOverrides
from chartnexus.contexts.trade_buddy.domain.errors import NoLevelsMarkedError
from chartnexus.contexts.trade_buddy.domain.events import AlertEvent, AlertKind
from chartnexus.contexts.trade_buddy.domain.level import LevelMark, LevelRole, MarkSet
from chartnexus.contexts.trade_buddy.domain.schedule import WatchWindow


@dataclass(frozen=True, slots=True)
class SetLevelsCommand:
    symbol: str
    marks: tuple[LevelMark, ...]


@dataclass(slots=True)
class SetLevels:
    """Replace the marked levels for one instrument.

    Stamped with the session they are for. Levels are a daily artefact, and
    without the stamp nothing could tell today's from Friday's — a watcher
    would compare live price against stale numbers and alert on them with full
    confidence, which is a worse failure than saying nothing.

    Clears any saved watcher states as a deliberate side effect: the states
    describe price's journey past the *old* levels, and keeping them against new
    marks would resume a session that never happened.
    """

    store: LevelStore
    window: WatchWindow
    clock: Clock

    async def __call__(self, command: SetLevelsCommand) -> tuple[LevelMark, ...]:
        _reject_duplicate_labels(command.marks)
        # The session the marks belong to, not the calendar date. The boundary
        # is the closing bell, so marking on Friday evening stamps Monday —
        # which is the whole point, since pivots are computed from a close and
        # so levels get marked after one.
        session = self.window.session_date(self.clock.now())
        await self.store.save_marks(command.symbol, command.marks, session)
        await self.store.save_watchers(command.symbol, ())
        return command.marks


@dataclass(slots=True)
class GetLevels:
    store: LevelStore

    async def __call__(self, symbol: str) -> MarkSet:
        return await self.store.load_marks(symbol)


@dataclass(slots=True)
class ClearLevels:
    store: LevelStore

    async def __call__(self, symbol: str) -> None:
        await self.store.clear(symbol)


@dataclass(frozen=True, slots=True)
class SetOverridesCommand:
    symbol: str
    overrides: AlertOverrides


@dataclass(slots=True)
class SetOverrides:
    """Replace one instrument's alert overrides.

    Shape is checked at the HTTP boundary, where a bad value can be refused
    with a message. Whether an override *combines* badly with the ATR-scaled
    values it does not replace cannot be known here — that depends on an ATR
    this path has no reason to fetch — so `resolve_bands` makes the final call
    at watch time and reports an unusable set through `ResolvedBands.note`
    rather than failing the watch.
    """

    store: LevelStore

    async def __call__(self, command: SetOverridesCommand) -> AlertOverrides:
        await self.store.save_overrides(command.symbol, command.overrides)
        return command.overrides


@dataclass(slots=True)
class GetOverrides:
    store: LevelStore

    async def __call__(self, symbol: str) -> AlertOverrides:
        return await self.store.load_overrides(symbol)


@dataclass(slots=True)
class FireTestAlert:
    """Send one synthetic alert, to prove the channels work before they matter.

    Uses a real :class:`AlertEvent` through the real sink rather than a bespoke
    "ping" path, because the thing worth testing is the routing policy and the
    credentials — and a test that bypasses them proves nothing.
    """

    sink: AlertSink
    clock: Clock
    store: LevelStore

    async def __call__(self, symbol: str, kind: AlertKind) -> AlertEvent:
        marked = await self.store.load_marks(symbol)
        if not marked:
            raise NoLevelsMarkedError(symbol)
        mark = marked.marks[0]
        event = AlertEvent(
            kind=kind,
            symbol=symbol,
            label=mark.label,
            level_price=mark.price,
            price=mark.price,
            role_before=mark.role,
            role_after=mark.role.inverted if kind is AlertKind.BREAK_CONFIRMED else mark.role,
            at=_aware(self.clock.now()),
        )
        await self.sink.deliver(event)
        return event


def _reject_duplicate_labels(marks: tuple[LevelMark, ...]) -> None:
    """Two levels sharing a label would collide in the budget's per-label counters."""
    labels = [mark.label for mark in marks]
    duplicates = sorted({label for label in labels if labels.count(label) > 1})
    if duplicates:
        raise ValueError(f"duplicate level labels: {', '.join(duplicates)}")


def _aware(moment: datetime) -> datetime:
    if moment.tzinfo is None:  # pragma: no cover — the real clock is always aware
        raise ValueError("clock returned a naive datetime")
    return moment


__all__ = [
    "AlertOverrides",
    "ClearLevels",
    "FireTestAlert",
    "GetLevels",
    "GetOverrides",
    "LevelRole",
    "SetLevels",
    "SetLevelsCommand",
    "SetOverrides",
    "SetOverridesCommand",
]
