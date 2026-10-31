"""Shared doubles for the Trade Buddy tests.

Everything here is a real port implementation, not a mock. The tests drive the
actual state machine, the actual budget and the actual router — only the clock,
the feed and the disk are substituted, because those are the three things that
would otherwise make the suite slow or non-deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import pytest

from chartnexus.contexts.trade_buddy.application.ports import FeedHealth, RuntimeState
from chartnexus.contexts.trade_buddy.application.routing import Notifier
from chartnexus.contexts.trade_buddy.domain.bands import (
    AlertOverrides,
    BandMultiples,
    BandPolicy,
)
from chartnexus.contexts.trade_buddy.domain.events import AlertEvent, AlertKind
from chartnexus.contexts.trade_buddy.domain.level import (
    LevelBands,
    LevelMark,
    LevelRole,
    MarkSet,
)
from chartnexus.contexts.trade_buddy.domain.schedule import IST, WatchWindow
from chartnexus.contexts.trade_buddy.domain.state import LevelWatcher

pytestmark = pytest.mark.unit

#: A Monday, mid-session, so the market-hours gate is open without any mocking.
SESSION_START = datetime(2026, 10, 26, 10, 0, tzinfo=IST)


@dataclass(slots=True)
class MemoryLevelStore:
    """The ``LevelStore`` port, in a dict. Round-trips like the JSON store."""

    marks: dict[str, MarkSet] = field(default_factory=dict)
    watchers: dict[str, tuple[LevelWatcher, ...]] = field(default_factory=dict)
    runtime: dict[str, RuntimeState] = field(default_factory=dict)
    overrides: dict[str, AlertOverrides] = field(default_factory=dict)
    saves: int = 0

    async def load_marks(self, symbol: str) -> MarkSet:
        return self.marks.get(symbol, MarkSet())

    async def save_marks(self, symbol: str, marks: tuple[LevelMark, ...], marked_on: date) -> None:
        self.marks[symbol] = MarkSet(marks=marks, marked_on=marked_on)

    def mark(self, symbol: str, *marks: LevelMark, on: date | None = None) -> None:
        """Test helper: mark levels for a session, defaulting to the one the
        fixtures run in, so a test that does not care about staleness does not
        have to think about it."""
        self.marks[symbol] = MarkSet(
            marks=marks, marked_on=on if on is not None else SESSION_START.date()
        )

    async def clear(self, symbol: str) -> None:
        self.marks.pop(symbol, None)
        self.watchers.pop(symbol, None)
        self.runtime.pop(symbol, None)
        self.overrides.pop(symbol, None)

    async def load_runtime(self, symbol: str) -> RuntimeState:
        return self.runtime.get(symbol, RuntimeState())

    async def save_runtime(self, symbol: str, state: RuntimeState) -> None:
        self.runtime[symbol] = state

    async def load_overrides(self, symbol: str) -> AlertOverrides:
        return self.overrides.get(symbol, AlertOverrides())

    async def save_overrides(self, symbol: str, overrides: AlertOverrides) -> None:
        self.overrides[symbol] = overrides

    async def load_watchers(self, symbol: str) -> tuple[LevelWatcher, ...]:
        return self.watchers.get(symbol, ())

    async def save_watchers(self, symbol: str, watchers: tuple[LevelWatcher, ...]) -> None:
        self.watchers[symbol] = watchers
        self.saves += 1


@dataclass(slots=True)
class RecordingSink:
    """Captures what the engine decided to deliver."""

    events: list[AlertEvent] = field(default_factory=list)
    health: list[FeedHealth] = field(default_factory=list)

    async def deliver(self, event: AlertEvent) -> None:
        self.events.append(event)

    async def deliver_health(self, health: FeedHealth) -> None:
        self.health.append(health)

    @property
    def kinds(self) -> list[AlertKind]:
        return [event.kind for event in self.events]

    def of_kind(self, kind: AlertKind) -> list[AlertEvent]:
        return [event for event in self.events if event.kind is kind]


@dataclass(slots=True)
class RecordingNotifier(Notifier):
    """A channel that records what it was asked to send, and can be told to fail."""

    name: str = "recording"
    rich: bool = True
    sent: list[str] = field(default_factory=list)
    #: Number of leading attempts to fail, to exercise the router's backoff.
    fail_times: int = 0
    attempts: int = 0

    async def send(self, text: str) -> None:
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise RuntimeError("channel unavailable")
        self.sent.append(text)


def alert_event(
    kind: AlertKind = AlertKind.TOUCHED,
    *,
    label: str = "R1",
    level_price: float = 24_700.0,
    price: float = 24_715.0,
    role_before: LevelRole = LevelRole.RESISTANCE,
    role_after: LevelRole | None = None,
    at_: datetime | None = None,
) -> AlertEvent:
    """One alert, for the budget and router tests. Lives here so neither test
    module has to import the other."""
    return AlertEvent(
        kind=kind,
        symbol="NSE:NIFTY50-INDEX",
        label=label,
        level_price=level_price,
        price=price,
        role_before=role_before,
        role_after=role_after or role_before,
        at=at_ or SESSION_START,
    )


def bands(
    *,
    touch: float = 6.0,
    approach: float = 25.0,
    buffer_: float = 12.0,
    hold: float = 20.0,
) -> LevelBands:
    return LevelBands(
        touch=touch, approach=approach, break_buffer=buffer_, confirm_hold_seconds=hold
    )


def policy(
    *,
    touch: float = 6.0,
    approach: float = 25.0,
    buffer_: float = 12.0,
    hold: float = 20.0,
) -> BandPolicy:
    """A policy whose point fallback is the old fixed band set.

    Engines built with no `atr_source` resolve to exactly these numbers, so
    tests written before bands were scaled still measure what they intended.
    """
    return BandPolicy(
        multiples=BandMultiples(),
        fallback=bands(touch=touch, approach=approach, buffer_=buffer_, hold=hold),
        confirm_hold_seconds=hold,
    )


@dataclass(slots=True)
class FixedAtr:
    """An `AtrSource` returning one number, or `None` to force point bands."""

    value: float | None = None
    calls: int = 0

    async def atr(self, symbol: str, *, period: int = 14) -> float | None:
        self.calls += 1
        return self.value


def watcher(
    price: float = 24_650.0,
    role: LevelRole = LevelRole.RESISTANCE,
    label: str = "R1",
    *,
    symbol: str = "NSE:NIFTY50-INDEX",
    level_bands: LevelBands | None = None,
) -> LevelWatcher:
    return LevelWatcher(
        symbol=symbol,
        mark=LevelMark(label=label, price=price, role=role),
        bands=level_bands or bands(),
    )


def window() -> WatchWindow:
    return WatchWindow.from_config("09:15", "15:20")


def at(seconds: float) -> datetime:
    """Wall-clock instant ``seconds`` into the session."""
    return SESSION_START + timedelta(seconds=seconds)


@pytest.fixture
def store() -> MemoryLevelStore:
    return MemoryLevelStore()


@pytest.fixture
def sink() -> RecordingSink:
    return RecordingSink()
