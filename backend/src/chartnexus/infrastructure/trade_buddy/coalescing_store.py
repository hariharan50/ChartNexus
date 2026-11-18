"""A ``LevelStore`` wrapper that stops per-tick saves becoming per-tick writes.

The engine saves its watcher states and runtime counters after **every tick**.
That was cheap with one user and a local file. Per-user, in Postgres, it is
``users x instruments`` row updates a tick — and almost all of them change
nothing but the last-tick time and price.

So this writes **immediately** whenever something that matters across a
restart changed, and otherwise at most every ``interval_seconds``:

* a watcher's state, role or break direction — a restart must resume it;
* the runtime's alert counters, WhatsApp window, session or ATR — losing an
  alert counter would let a restart send the same alert again.

What waits is only the last-tick time and price, which the status page shows
and which a restart re-learns from the next tick anyway. ``flush`` writes
anything held (the worker calls it at the end of each session and on shutdown).

Everything else — marks, overrides, resets, the alert history — passes straight
through: those are rare and every one of them matters.

Worker-side only. The API writes through the plain store.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from chartnexus.contexts.trade_buddy.application.ports import (
    AlertRecord,
    LevelStore,
    RuntimeState,
)
from chartnexus.contexts.trade_buddy.domain.bands import AlertOverrides
from chartnexus.contexts.trade_buddy.domain.level import LevelMark, MarkSet
from chartnexus.contexts.trade_buddy.domain.state import LevelWatcher

DEFAULT_INTERVAL_SECONDS = 5.0


def _watcher_signature(watchers: tuple[LevelWatcher, ...]) -> tuple[object, ...]:
    return tuple((w.mark.label, w.mark.price, w.role, w.state, w.break_sign) for w in watchers)


def _runtime_signature(state: RuntimeState) -> tuple[object, ...]:
    """Everything in the runtime except the per-tick time and price."""
    return (
        repr(sorted(state.level_budget.items())),
        state.whatsapp_sends,
        state.session,
        state.atr,
    )


@dataclass(slots=True)
class CoalescingLevelStore:
    """Implements ``LevelStore`` over another, holding back no-change saves."""

    inner: LevelStore
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS
    monotonic: Callable[[], float] = time.monotonic

    _watchers: dict[str, tuple[LevelWatcher, ...]] = field(default_factory=dict)
    _runtime: dict[str, RuntimeState] = field(default_factory=dict)
    _written_watchers: dict[str, tuple[object, ...]] = field(default_factory=dict)
    _written_runtime: dict[str, tuple[object, ...]] = field(default_factory=dict)
    _last_flush: dict[str, float] = field(default_factory=dict)

    # -- the two held writes ------------------------------------------------

    async def save_watchers(self, symbol: str, watchers: tuple[LevelWatcher, ...]) -> None:
        self._watchers[symbol] = watchers
        if _watcher_signature(watchers) != self._written_watchers.get(symbol):
            await self.flush(symbol)
        else:
            await self._flush_if_due(symbol)

    async def save_runtime(self, symbol: str, state: RuntimeState) -> None:
        self._runtime[symbol] = state
        if _runtime_signature(state) != self._written_runtime.get(symbol):
            await self.flush(symbol)
        else:
            await self._flush_if_due(symbol)

    async def _flush_if_due(self, symbol: str) -> None:
        last = self._last_flush.get(symbol)
        if last is None or self.monotonic() - last >= self.interval_seconds:
            await self.flush(symbol)

    async def flush(self, symbol: str) -> None:
        """Write whatever is held for ``symbol``."""
        watchers = self._watchers.pop(symbol, None)
        runtime = self._runtime.pop(symbol, None)
        if watchers is not None:
            await self.inner.save_watchers(symbol, watchers)
            self._written_watchers[symbol] = _watcher_signature(watchers)
        if runtime is not None:
            await self.inner.save_runtime(symbol, runtime)
            self._written_runtime[symbol] = _runtime_signature(runtime)
        self._last_flush[symbol] = self.monotonic()

    async def flush_all(self) -> None:
        for symbol in {*self._watchers, *self._runtime}:
            await self.flush(symbol)

    # -- reads: never behind what this process has said ---------------------

    async def load_watchers(self, symbol: str) -> tuple[LevelWatcher, ...]:
        await self.flush(symbol)
        return await self.inner.load_watchers(symbol)

    async def load_runtime(self, symbol: str) -> RuntimeState:
        await self.flush(symbol)
        return await self.inner.load_runtime(symbol)

    async def load_marks(self, symbol: str) -> MarkSet:
        return await self.inner.load_marks(symbol)

    async def load_overrides(self, symbol: str) -> AlertOverrides:
        return await self.inner.load_overrides(symbol)

    async def load_alerts(self, symbol: str, session: date) -> tuple[AlertRecord, ...]:
        return await self.inner.load_alerts(symbol, session)

    # -- write-through ------------------------------------------------------

    async def save_marks(self, symbol: str, marks: tuple[LevelMark, ...], marked_on: date) -> None:
        await self.inner.save_marks(symbol, marks, marked_on)

    async def save_overrides(self, symbol: str, overrides: AlertOverrides) -> None:
        await self.inner.save_overrides(symbol, overrides)

    async def append_alert(self, symbol: str, record: AlertRecord) -> None:
        await self.inner.append_alert(symbol, record)

    async def clear(self, symbol: str) -> None:
        self._forget(symbol)
        await self.inner.clear(symbol)

    async def reset_day(self, symbol: str) -> None:
        self._forget(symbol)
        await self.inner.reset_day(symbol)

    def _forget(self, symbol: str) -> None:
        """Drop held writes, so a reset is not undone by a late flush."""
        self._watchers.pop(symbol, None)
        self._runtime.pop(symbol, None)
        self._written_watchers.pop(symbol, None)
        self._written_runtime.pop(symbol, None)
