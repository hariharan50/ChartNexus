"""One ATR fetch per instrument per day, however many users watch it.

ATR is a daily figure about the market, not about a user. Per-user Trade Buddy
builds one engine per (user, instrument), and each engine asks for ATR when it
loads and again when the session rolls — so without this, a hundred people
watching NIFTY would spend a hundred history calls on one number. Under FYERS'
free plan (5,000 data calls a day) that alone could exhaust the day.

Concurrent first requests for the same key share one fetch rather than racing.
A ``None`` (thin history, provider outage) is **not** cached, so the next
engine to load tries again instead of the whole day degrading to point bands.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from chartnexus.contexts.trade_buddy.application.ports import AtrSource

_IST = ZoneInfo("Asia/Kolkata")


def _today_ist() -> date:
    return datetime.now(UTC).astimezone(_IST).date()


@dataclass(slots=True)
class SessionAtrCache:
    """Implements ``AtrSource`` over another, caching per (symbol, period, day)."""

    inner: AtrSource
    today: Callable[[], date] = _today_ist
    _values: dict[tuple[str, int, date], float] = field(default_factory=dict)
    _locks: dict[tuple[str, int, date], asyncio.Lock] = field(default_factory=dict)

    async def atr(self, symbol: str, *, period: int = 14) -> float | None:
        key = (symbol, period, self.today())
        cached = self._values.get(key)
        if cached is not None:
            return cached
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self._values.get(key)
            if cached is not None:
                return cached
            value = await self.inner.atr(symbol, period=period)
            if value is not None:
                # Keep only today's: yesterday's entries are never asked for again.
                for stale in [k for k in self._values if k[2] != key[2]]:
                    del self._values[stale]
                    self._locks.pop(stale, None)
                self._values[key] = value
            return value
