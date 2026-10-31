"""The Fyers v3 WebSocket, behind the ``TickFeed`` port.

This is the only module in the repository allowed to import ``fyers_apiv3`` for
streaming — ``tests/architecture/test_vendor_imports.py`` enforces it — and the
reason the confinement matters here is that the SDK's shape fights the rest of
the codebase in three specific ways:

**It is synchronous and threaded.** ``FyersDataSocket`` runs its own thread and
invokes ``on_message`` from it. Touching an asyncio primitive from that thread
is undefined behaviour, so every callback does exactly one thing:
``loop.call_soon_threadsafe`` onto a queue the async side drains. Nothing
outside this file ever learns a thread was involved.

**Its payload shape varies.** Litemode sends ``ltp``; full mode sends a nested
structure, and the key that carries last price has differed across releases.
:func:`extract_price` therefore probes a list of candidates rather than trusting
one, and returns ``None`` instead of guessing — a fabricated price here becomes
a false break alert, which is the worst thing this module can produce.

**Its failures are silent.** A dropped socket or an expired token can leave the
SDK quietly not delivering. The health callbacks are wired to a reporter so the
engine can say so, because silence from a dead feed is indistinguishable from a
quiet market.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from fyers_apiv3.FyersWebsocket import data_ws

from chartnexus.contexts.trade_buddy.application.ports import Tick
from chartnexus.infrastructure.brokers.fyers.symbol_mapper import (
    from_broker_symbol,
)
from chartnexus.infrastructure.brokers.fyers.tick_parsing import (
    extract_price,
    extract_symbol,
    extract_time,
)
from chartnexus.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)

#: Called with ``(reason, detail)`` when the socket drops or the token is
#: refused, so the engine can alert rather than going quietly silent.
HealthReporter = Callable[[str, str], Awaitable[None]]


class FyersTickFeed:
    """Implements ``TickFeed`` over ``data_ws.FyersDataSocket``.

    One instance per *session*, not per process: ``access_token`` is the
    SDK's ``"APPID:TOKEN"`` form and the token half expires daily, so the
    runtime builds a fresh socket each morning. Never logged.
    """

    def __init__(
        self,
        *,
        access_token: str,
        on_health: HealthReporter | None = None,
        queue_size: int = 1000,
        litemode: bool = True,
    ) -> None:
        self._access_token = access_token
        self._on_health = on_health
        self._litemode = litemode
        self._loop: asyncio.AbstractEventLoop | None = None
        # Bounded: if the consumer stalls, dropping the oldest ticks is correct.
        # An unbounded queue would turn a slow consumer into a memory leak and
        # then deliver a backlog of stale prices, which is worse than a gap.
        self._queue: asyncio.Queue[Tick | None] = asyncio.Queue(maxsize=queue_size)
        self._socket: Any | None = None
        #: Canonical names, as the engine knows them.
        self._symbols: tuple[str, ...] = ()
        #: Broker string -> canonical, for translating inbound frames.
        self._broker_to_canonical: dict[str, str] = {}
        self._closed = False
        self._dropped = 0

    # -- the async side -----------------------------------------------------

    async def subscribe(self, symbols: tuple[str, ...]) -> None:
        """Connect (if needed) and subscribe. Idempotent per symbol set."""
        self._loop = asyncio.get_running_loop()
        if self._socket is None:
            self._socket = self._build()
            # `connect()` spawns the SDK's own thread and returns; it does not
            # block, so there is nothing to await here.
            await asyncio.to_thread(self._socket.connect)
        new = tuple(s for s in symbols if s not in self._symbols)
        if not new:
            return
        self._symbols += new
        await asyncio.to_thread(self._socket.subscribe, symbols=list(new), data_type="SymbolUpdate")
        log.info("fyers_socket_subscribed", symbols=list(new), litemode=self._litemode)

    async def ticks(self) -> AsyncIterator[Tick]:
        while True:
            tick = await self._queue.get()
            if tick is None:
                return
            yield tick

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._socket is not None:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(self._socket.close_connection)
        await self._queue.put(None)
        if self._dropped:
            log.warning("fyers_socket_ticks_dropped", dropped=self._dropped)

    def _build(self) -> Any:
        return data_ws.FyersDataSocket(
            access_token=self._access_token,
            write_to_file=False,
            log_path="",
            reconnect=True,
            on_connect=self._on_connect,
            on_close=self._on_close,
            on_error=self._on_error,
            on_message=self._on_message,
            litemode=self._litemode,
        )

    # -- SDK callbacks: these run on the SDK's thread -----------------------
    #
    # Each one does the minimum and hands off. No asyncio object may be touched
    # directly from here; `call_soon_threadsafe` is the only safe door.

    def _on_message(self, message: Any) -> None:
        price = extract_price(message)
        if price is None:
            return
        raw = extract_symbol(message)
        canonical = self._canonical(raw)
        if not canonical:
            return
        arrived = datetime.now(UTC)
        tick = Tick(symbol=canonical, price=price, at=extract_time(message, fallback=arrived))
        self._offer(tick)

    def _canonical(self, raw: str | None) -> str | None:
        """The canonical name for an inbound frame's symbol.

        Falls back to the sole subscription when the frame carries no symbol —
        litemode sometimes omits it — but never when more than one instrument
        is subscribed, because attributing a BANKNIFTY tick to NIFTY would
        compare the wrong price against the wrong levels.
        """
        if raw:
            mapped = self._broker_to_canonical.get(raw)
            if mapped:
                return mapped
            resolved = from_broker_symbol(raw)
            if resolved is not None:
                return str(resolved)
            return None
        return self._symbols[0] if len(self._symbols) == 1 else None

    def _offer(self, tick: Tick) -> None:
        loop = self._loop
        if loop is None or self._closed:
            return

        def _put() -> None:
            try:
                self._queue.put_nowait(tick)
            except asyncio.QueueFull:
                # Drop the oldest, keep the newest: a level watcher wants the
                # current price, never a queue of prices it has already missed.
                with contextlib.suppress(asyncio.QueueEmpty):
                    self._queue.get_nowait()
                self._dropped += 1
                with contextlib.suppress(asyncio.QueueFull):
                    self._queue.put_nowait(tick)

        loop.call_soon_threadsafe(_put)

    def _on_connect(self) -> None:
        log.info("fyers_socket_connected")
        if self._symbols:
            # A reconnect does not restore subscriptions; re-sending them is
            # what keeps a mid-session drop from going permanently quiet.
            socket = self._socket
            if socket is not None:
                with contextlib.suppress(Exception):
                    socket.subscribe(
                        symbols=list(self._broker_to_canonical), data_type="SymbolUpdate"
                    )

    def _on_close(self, message: Any = None) -> None:
        log.warning("fyers_socket_closed", detail=str(message))
        self._report("feed_disconnected", f"Fyers socket closed: {message}")

    def _on_error(self, message: Any = None) -> None:
        detail = str(message)
        log.error("fyers_socket_error", detail=detail)
        # The SDK reports an expired token as a generic error; naming it lets
        # the alert say what to actually do about it.
        lowered = detail.lower()
        reason = "token_rejected" if ("token" in lowered or "401" in lowered) else "feed_error"
        self._report(reason, f"Fyers socket error: {detail}")

    def _report(self, reason: str, detail: str) -> None:
        """Hand a health event to the async side, from the SDK's thread."""
        loop = self._loop
        reporter = self._on_health
        if loop is None or reporter is None or self._closed:
            return
        loop.call_soon_threadsafe(lambda: loop.create_task(_safe_report(reporter, reason, detail)))


async def _safe_report(reporter: HealthReporter, reason: str, detail: str) -> None:
    try:
        await reporter(reason, detail)
    except Exception as exc:
        log.error("fyers_health_report_failed", error=repr(exc))
