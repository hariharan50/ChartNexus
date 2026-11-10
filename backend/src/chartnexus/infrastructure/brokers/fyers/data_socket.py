"""The Fyers v3 WebSocket, behind the ``TickFeed`` port.

Streaming is confined to this directory —
``tests/architecture/test_vendor_imports.py`` enforces it — and the SDK itself
is reached through :mod:`sdk`, which carries the packaging shim it needs to
import at all. The reason the confinement matters here is that the SDK's shape
fights the rest of the codebase in three specific ways:

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

from chartnexus.contexts.market_data.domain.instruments import InstrumentSymbol
from chartnexus.contexts.trade_buddy.application.ports import Tick
from chartnexus.infrastructure.brokers.fyers.sdk import data_ws
from chartnexus.infrastructure.brokers.fyers.symbol_mapper import (
    from_broker_symbol,
    to_broker_symbol,
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
        #: Canonical names, as the engine knows them. Only the ones actually
        #: subscribed: a symbol the catalog could not translate never lands
        #: here, so it cannot be reported as watched.
        self._symbols: tuple[str, ...] = ()
        #: The broker strings sent to the SDK, in subscription order. Held
        #: because a reconnect has to re-send exactly these — the SDK does not
        #: restore subscriptions, and it has never heard a canonical name.
        self._broker_symbols: tuple[str, ...] = ()
        #: Upper-cased broker string -> canonical, for translating inbound
        #: frames without a catalog scan per tick.
        self._broker_to_canonical: dict[str, str] = {}
        self._closed = False
        self._dropped = 0

    # -- the async side -----------------------------------------------------

    async def subscribe(self, symbols: tuple[str, ...]) -> None:
        """Connect (if needed) and subscribe. Idempotent per symbol set.

        ``symbols`` arrive canonical (``BANKNIFTY``) because that is what every
        layer above speaks. The SDK only understands the exchange's own strings
        (``NSE:NIFTYBANK-INDEX``), and the index root is not derivable from the
        canonical name, so each one goes through the catalog here — this is the
        boundary where that translation belongs, and the only place in the
        repository where a broker symbol is spoken out loud.

        Translation happens *before* the socket is opened. A subscription the
        broker cannot parse yields no ticks and no error, which is the one
        failure this feed must never produce silently, so an untranslatable
        symbol is announced through the health reporter and left unsubscribed
        rather than passed down as-is.
        """
        self._loop = asyncio.get_running_loop()
        new = tuple(s for s in symbols if s not in self._symbols)
        if not new:
            return

        resolved: list[tuple[str, str]] = []
        unresolved: list[str] = []
        for canonical in new:
            broker = self._broker_symbol(canonical)
            if broker is None:
                unresolved.append(canonical)
            else:
                resolved.append((canonical, broker))

        if unresolved:
            await self._announce(
                "feed_symbol_unmapped",
                f"No broker symbol for {', '.join(unresolved)} — not subscribed, "
                "so no alerts will be sent for it. The instrument catalog may "
                "not be loaded.",
            )
        if not resolved:
            # Nothing to listen to. Opening a socket now would connect, sit
            # subscribed to nothing, and look healthy while delivering nothing.
            return

        if self._socket is None:
            self._socket = self._build()
            # `connect()` spawns the SDK's own thread and returns; it does not
            # block, so there is nothing to await here.
            await asyncio.to_thread(self._socket.connect)

        for canonical, broker in resolved:
            self._broker_to_canonical[broker.strip().upper()] = canonical
        self._symbols += tuple(canonical for canonical, _ in resolved)
        self._broker_symbols += tuple(broker for _, broker in resolved)

        wire = [broker for _, broker in resolved]
        await asyncio.to_thread(self._socket.subscribe, symbols=wire, data_type="SymbolUpdate")
        log.info(
            "fyers_socket_subscribed",
            symbols=[canonical for canonical, _ in resolved],
            broker_symbols=wire,
            litemode=self._litemode,
        )

    def _broker_symbol(self, canonical: str) -> str | None:
        """The broker's string for one canonical name, or ``None``.

        A catalog miss returns ``None`` rather than raising: one unmappable
        instrument must not stop the others from being watched, and the caller
        reports it.
        """
        try:
            return to_broker_symbol(InstrumentSymbol(canonical))
        except Exception as exc:
            log.error("fyers_socket_symbol_unmapped", symbol=canonical, error=repr(exc))
            return None

    async def _announce(self, reason: str, detail: str) -> None:
        """Report a health event from the async side, defensively."""
        reporter = self._on_health
        if reporter is None:
            return
        try:
            await reporter(reason, detail)
        except Exception as exc:
            log.error("fyers_health_report_failed", error=repr(exc))

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
            mapped = self._broker_to_canonical.get(raw.strip().upper())
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
        socket = self._socket
        if not self._broker_symbols or socket is None:
            return
        # A reconnect does not restore subscriptions; re-sending them is what
        # keeps a mid-session drop from going permanently quiet. It has to be
        # the broker strings — the SDK has never heard a canonical name.
        wire = list(self._broker_symbols)
        try:
            socket.subscribe(symbols=wire, data_type="SymbolUpdate")
        except Exception as exc:
            # A re-subscribe that fails leaves a connected socket delivering
            # nothing, which looks exactly like a quiet market. Saying so is
            # the whole reason these callbacks report health at all.
            log.error("fyers_socket_resubscribe_failed", symbols=wire, error=repr(exc))
            self._report(
                "feed_resubscribe_failed",
                f"Reconnected to Fyers but could not re-subscribe to {', '.join(wire)}: {exc}",
            )
        else:
            log.info("fyers_socket_resubscribed", broker_symbols=wire)

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
