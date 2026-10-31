"""A feed you push ticks into. The reason the engine is testable at all.

Implements the same ``TickFeed`` port as the Fyers socket, so a test drives the
real engine, the real state machine and the real router over a scripted market —
no network, no SDK, no market hours. The alternative is testing the engine
through the Fyers adapter with a mocked socket, which tests the mock.

Also useful at runtime: replaying a recorded session through this feed is how
you confirm a config change (a wider buffer, a longer hold) would have produced
fewer false alerts without waiting for another live session to find out.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from chartnexus.contexts.trade_buddy.application.ports import Tick


@dataclass(slots=True)
class ManualFeed:
    """A ``TickFeed`` fed by :meth:`push` instead of by a socket."""

    _queue: asyncio.Queue[Tick | None] = field(default_factory=asyncio.Queue)
    _symbols: tuple[str, ...] = ()
    _closed: bool = False

    async def subscribe(self, symbols: tuple[str, ...]) -> None:
        self._symbols = symbols

    @property
    def symbols(self) -> tuple[str, ...]:
        """What was subscribed, so a test can assert the engine asked for it."""
        return self._symbols

    async def push(self, tick: Tick) -> None:
        """Offer one tick to the consumer."""
        await self._queue.put(tick)

    async def ticks(self) -> AsyncIterator[Tick]:
        while True:
            tick = await self._queue.get()
            if tick is None:  # the close sentinel
                return
            yield tick

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._queue.put(None)
