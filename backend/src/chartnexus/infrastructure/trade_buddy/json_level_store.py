"""Marks and live states on disk, as JSON.

A file rather than a Postgres table because of what this data is: six numbers
per instrument per day, written by one process, read by one process, and
worthless by tomorrow morning. A migration and a repository would be real cost
for no benefit the file does not already provide.

What *is* load-bearing is that the watcher states round-trip. Without them a
restart at 14:00 rebuilds every level in ``IDLE`` and re-reports everything
price already passed today, which teaches the reader to ignore the channel.

Writes go through a temporary file and an atomic replace. The engine saves after
every tick, so a crash mid-write is not a hypothetical, and a truncated JSON
file would lose the session's state entirely.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from chartnexus.contexts.trade_buddy.application.ports import RuntimeState
from chartnexus.contexts.trade_buddy.domain.bands import AlertOverrides, BandOverrides
from chartnexus.contexts.trade_buddy.domain.level import (
    LevelBands,
    LevelMark,
    LevelRole,
    MarkSet,
)
from chartnexus.contexts.trade_buddy.domain.state import LevelState, LevelWatcher
from chartnexus.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)

_VERSION = 4


@dataclass(slots=True)
class JsonLevelStore:
    """Implements the ``LevelStore`` port against one JSON file per instrument."""

    directory: Path
    bands: LevelBands
    #: Guards the read-modify-write cycle; the engine and the API both write.
    _lock: asyncio.Lock = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    # -- paths --------------------------------------------------------------

    def _path(self, symbol: str) -> Path:
        # Symbols carry colons and hyphens ("NSE:NIFTY50-INDEX"), and a colon is
        # not a legal Windows filename character.
        safe = symbol.replace(":", "_").replace("/", "_")
        return self.directory / f"{safe}.json"

    async def _read(self, symbol: str) -> dict[str, Any]:
        path = self._path(symbol)
        if not path.exists():
            return {}
        try:
            raw = await asyncio.to_thread(path.read_text, encoding="utf-8")
            parsed: dict[str, Any] = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            # A corrupt file must not take the watcher down with it — losing
            # today's resume state is survivable, a crash loop is not.
            log.warning("trade_buddy_state_unreadable", symbol=symbol, error=repr(exc))
            return {}
        if parsed.get("version") != _VERSION:
            log.warning("trade_buddy_state_version_mismatch", symbol=symbol)
            return {}
        return parsed

    async def _write(self, symbol: str, payload: dict[str, Any]) -> None:
        payload["version"] = _VERSION
        path = self._path(symbol)
        body = json.dumps(payload, indent=2, sort_keys=True)

        def _atomic() -> None:
            temp = path.with_suffix(".json.tmp")
            temp.write_text(body, encoding="utf-8")
            temp.replace(path)

        await asyncio.to_thread(_atomic)

    # -- marks --------------------------------------------------------------

    async def load_marks(self, symbol: str) -> MarkSet:
        data = await self._read(symbol)
        marks = tuple(_mark_from(row) for row in data.get("marks", []))

        marked_on: date | None = None
        raw = data.get("marked_on")
        if isinstance(raw, str):
            with contextlib.suppress(ValueError):
                marked_on = date.fromisoformat(raw)
        return MarkSet(marks=marks, marked_on=marked_on)

    async def save_marks(self, symbol: str, marks: tuple[LevelMark, ...], marked_on: date) -> None:
        async with self._lock:
            data = await self._read(symbol)
            data["marks"] = [_mark_to(mark) for mark in marks]
            data["marked_on"] = marked_on.isoformat()
            await self._write(symbol, data)

    async def clear(self, symbol: str) -> None:
        async with self._lock:
            path = self._path(symbol)
            if path.exists():
                await asyncio.to_thread(path.unlink)

    # -- live state ---------------------------------------------------------

    async def load_watchers(self, symbol: str) -> tuple[LevelWatcher, ...]:
        data = await self._read(symbol)
        rows = data.get("watchers", [])
        return tuple(_watcher_from(symbol, row, self.bands) for row in rows)

    async def save_watchers(self, symbol: str, watchers: tuple[LevelWatcher, ...]) -> None:
        async with self._lock:
            data = await self._read(symbol)
            data["watchers"] = [_watcher_to(w) for w in watchers]
            await self._write(symbol, data)

    # -- runtime counters ---------------------------------------------------

    async def load_runtime(self, symbol: str) -> RuntimeState:
        data = await self._read(symbol)
        row = data.get("runtime")
        if not isinstance(row, dict):
            return RuntimeState()

        last_tick: datetime | None = None
        raw = row.get("last_tick_at")
        if isinstance(raw, str):
            with contextlib.suppress(ValueError):
                last_tick = datetime.fromisoformat(raw)

        session: date | None = None
        raw_session = row.get("session")
        if isinstance(raw_session, str):
            with contextlib.suppress(ValueError):
                session = date.fromisoformat(raw_session)

        raw_atr = row.get("atr")
        cached_atr = float(raw_atr) if isinstance(raw_atr, (int, float)) else None

        raw_price = row.get("last_price")
        last_price = float(raw_price) if isinstance(raw_price, (int, float)) else None

        budget = row.get("level_budget")
        sends = row.get("whatsapp_sends")
        return RuntimeState(
            last_tick_at=last_tick,
            last_price=last_price,
            atr=cached_atr,
            session=session,
            level_budget=budget if isinstance(budget, dict) else {},
            whatsapp_sends=(
                tuple(s for s in sends if isinstance(s, str)) if isinstance(sends, list) else ()
            ),
        )

    # -- per-instrument band overrides --------------------------------------

    async def load_overrides(self, symbol: str) -> AlertOverrides:
        data = await self._read(symbol)
        row = data.get("overrides")
        if not isinstance(row, dict):
            return AlertOverrides()
        cap = row.get("daily_alert_cap")
        return AlertOverrides(
            bands=BandOverrides(
                touch=_opt_float(row.get("touch")),
                approach=_opt_float(row.get("approach")),
                break_buffer=_opt_float(row.get("break_buffer")),
                confirm_hold_seconds=_opt_float(row.get("confirm_hold_seconds")),
            ),
            cooldown_minutes=_opt_float(row.get("cooldown_minutes"), allow_zero=True),
            daily_alert_cap=int(cap)
            if isinstance(cap, int) and not isinstance(cap, bool)
            else None,
        )

    async def save_overrides(self, symbol: str, overrides: AlertOverrides) -> None:
        async with self._lock:
            data = await self._read(symbol)
            data["overrides"] = {
                "touch": overrides.bands.touch,
                "approach": overrides.bands.approach,
                "break_buffer": overrides.bands.break_buffer,
                "confirm_hold_seconds": overrides.bands.confirm_hold_seconds,
                "cooldown_minutes": overrides.cooldown_minutes,
                "daily_alert_cap": overrides.daily_alert_cap,
            }
            await self._write(symbol, data)

    async def save_runtime(self, symbol: str, state: RuntimeState) -> None:
        async with self._lock:
            data = await self._read(symbol)
            data["runtime"] = {
                "last_tick_at": (state.last_tick_at.isoformat() if state.last_tick_at else None),
                "last_price": state.last_price,
                "atr": state.atr,
                "session": state.session.isoformat() if state.session else None,
                "level_budget": state.level_budget,
                "whatsapp_sends": list(state.whatsapp_sends),
            }
            await self._write(symbol, data)


# -- mapping ----------------------------------------------------------------


def _opt_float(value: Any, *, allow_zero: bool = False) -> float | None:
    """A stored override, or None.

    A bad value is dropped rather than raised on: `resolve_bands` reports an
    unusable override, and a crash here would take the whole watch down over a
    hand-edited file. `allow_zero` is for the cooldown, where zero is a
    meaningful setting ("no cooldown") rather than an unset one.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value < 0 or (value == 0 and not allow_zero):
        return None
    return float(value)


def _mark_to(mark: LevelMark) -> dict[str, Any]:
    return {"label": mark.label, "price": mark.price, "role": mark.role.value}


def _mark_from(row: dict[str, Any]) -> LevelMark:
    return LevelMark(
        label=str(row["label"]),
        price=float(row["price"]),
        role=LevelRole(row["role"]),
    )


def _watcher_to(watcher: LevelWatcher) -> dict[str, Any]:
    """Persist the state *and* the pending-break bookkeeping.

    ``pending_since`` is a monotonic reading, which is meaningless across a
    process restart — it is written for completeness but deliberately dropped on
    load, so a break that was mid-hold when the process died has to re-earn its
    hold rather than confirm instantly against a stale origin.
    """
    return {
        "mark": _mark_to(watcher.mark),
        "role": watcher.role.value,
        "state": watcher.state.value,
        "break_sign": watcher.break_sign,
    }


def _watcher_from(symbol: str, row: dict[str, Any], bands: LevelBands) -> LevelWatcher:
    watcher = LevelWatcher(symbol=symbol, mark=_mark_from(row["mark"]), bands=bands)
    watcher.role = LevelRole(row["role"])
    state = LevelState(row["state"])
    sign = row.get("break_sign")
    watcher.break_sign = int(sign) if sign is not None else None

    if state is LevelState.BREAK_PENDING:
        # Restart during a pending break: fall back to TOUCHED so the hold is
        # measured again from the next tick. Confirming on a resumed, unverified
        # hold would be exactly the false break this module exists to avoid.
        watcher.state = LevelState.TOUCHED
        watcher.pending_since = None
        watcher.break_sign = None
    else:
        watcher.state = state
        watcher.pending_since = None
    return watcher
