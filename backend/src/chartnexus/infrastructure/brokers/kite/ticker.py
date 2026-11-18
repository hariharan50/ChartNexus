"""The Kite Connect WebSocket ticker, behind the ``TickFeed`` port.

A native asyncio client rather than the SDK's ``KiteTicker``. That one runs a
Twisted reactor on its own thread, which would bring back every
thread-to-event-loop workaround ``fyers/data_socket.py`` has to carry. Kite's
wire format is documented, so owning it is about two hundred lines.

**Wire format** (Kite Connect v3 streaming):

* Connect to ``wss://ws.kite.trade?api_key=…&access_token=…``.
* Control messages are JSON text: ``{"a": "subscribe", "v": [tokens]}`` and
  ``{"a": "mode", "v": ["ltp" | "quote" | "full", [tokens]]}``.
* Market data is binary: ``int16`` packet count, then for each packet an
  ``int16`` length followed by that many bytes. Every field is a big-endian
  ``int32``; prices are in **paise** (divide by 100; currency segments differ).
  Packet length identifies the mode — 8 LTP, 28 index quote, 32 index full,
  44 quote, 184 full.
* A 1-byte binary message is a heartbeat, roughly once a second.
* Text messages are JSON ``{"type": "error" | "message" | "order", ...}``.

The rules carried over from the FYERS feed, each learned the hard way there:
a bounded queue that drops the *oldest* tick; re-subscribe on every reconnect;
announce symbols that cannot be translated instead of subscribing to nothing;
never fabricate a price; report a refused token as ``token_rejected``. And one
Kite-specific one: **the socket URL carries the access token, so it is never
logged.**
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import random
import struct
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from chartnexus.contexts.trade_buddy.application.ports import Tick
from chartnexus.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)

HealthReporter = Callable[[str, str], Awaitable[None]]
TokenResolver = Callable[[str], Awaitable[int | None]]

DEFAULT_WS_URL = "wss://ws.kite.trade"

#: No frame — not even a heartbeat — for this long means the socket is dead.
_SILENCE_SECONDS = 5.0
_BACKOFF_START = 1.0
_BACKOFF_CEILING = 30.0

# Exchange segment ids are the low byte of an instrument token.
_SEGMENT_CDS = 3
_SEGMENT_BCD = 6
_SEGMENT_INDICES = 9

_LTP = 8
_INDEX_QUOTE = 28
_INDEX_FULL = 32
_QUOTE = 44
_FULL = 184
_HEARTBEAT = 1


@dataclass(frozen=True, slots=True)
class KitePacket:
    """One decoded instrument update. Prices already in rupees."""

    instrument_token: int
    last_price: float
    mode: str
    open_interest: int | None = None
    volume: int | None = None
    exchange_time: datetime | None = None


def price_divisor(instrument_token: int) -> float:
    segment = instrument_token & 0xFF
    if segment == _SEGMENT_CDS:
        return 10_000_000.0
    if segment == _SEGMENT_BCD:
        return 10_000.0
    return 100.0


def parse_frame(frame: bytes) -> list[KitePacket]:
    """Decode one binary message into packets. Heartbeats decode to nothing.

    Unknown packet lengths are skipped rather than guessed at: a misparsed
    price is a false alert, which is worse than a missed tick.
    """
    if len(frame) < 2:  # noqa: PLR2004 — heartbeat or truncated
        return []
    (count,) = struct.unpack_from(">H", frame, 0)
    offset = 2
    packets: list[KitePacket] = []
    for _ in range(count):
        if offset + 2 > len(frame):
            break
        (length,) = struct.unpack_from(">H", frame, offset)
        offset += 2
        body = frame[offset : offset + length]
        offset += length
        if len(body) != length:
            break
        packet = _packet(body)
        if packet is not None:
            packets.append(packet)
    return packets


def _packet(body: bytes) -> KitePacket | None:
    length = len(body)
    if length < _LTP:
        return None
    token, raw_price = struct.unpack_from(">ii", body, 0)
    divisor = price_divisor(token)
    price = raw_price / divisor
    if price <= 0:
        # Kite sends 0 for an instrument with no trade yet. Not a price.
        return None

    if length == _LTP:
        return KitePacket(instrument_token=token, last_price=price, mode="ltp")

    if length in (_INDEX_QUOTE, _INDEX_FULL):
        exchange_time = None
        if length == _INDEX_FULL:
            (epoch,) = struct.unpack_from(">i", body, 28)
            exchange_time = _epoch(epoch)
        return KitePacket(
            instrument_token=token,
            last_price=price,
            mode="full" if length == _INDEX_FULL else "quote",
            exchange_time=exchange_time,
        )

    if length in (_QUOTE, _FULL):
        # token, ltp, last_qty, avg_price, volume, buy_qty, sell_qty, o, h, l, c
        fields = struct.unpack_from(">11i", body, 0)
        volume = fields[4]
        oi = None
        exchange_time = None
        if length == _FULL:
            # last_trade_time, oi, oi_day_high, oi_day_low, exchange_timestamp
            extra = struct.unpack_from(">5i", body, 44)
            oi = extra[1]
            exchange_time = _epoch(extra[4])
        return KitePacket(
            instrument_token=token,
            last_price=price,
            mode="full" if length == _FULL else "quote",
            open_interest=oi,
            volume=volume,
            exchange_time=exchange_time,
        )
    return None


def _epoch(value: int) -> datetime | None:
    return datetime.fromtimestamp(value, tz=UTC) if value > 0 else None


def socket_url(base: str, *, api_key: str, access_token: str) -> str:
    """Never log the result: it carries the access token."""
    return f"{base}?{urlencode({'api_key': api_key, 'access_token': access_token})}"


class KiteTickFeed:
    """Implements ``TickFeed`` over Kite's WebSocket.

    One instance per watch *session*: the token dies at 06:00 IST, so the
    runtime builds a fresh feed each day, exactly as it does for FYERS.
    """

    def __init__(
        self,
        *,
        api_key: str,
        access_token: str,
        resolve_token: TokenResolver,
        on_health: HealthReporter | None = None,
        ws_url: str = DEFAULT_WS_URL,
        mode: str = "ltp",
        queue_size: int = 1000,
        connect: Callable[[str], Any] | None = None,
    ) -> None:
        self._url = socket_url(ws_url, api_key=api_key, access_token=access_token)
        self._resolve = resolve_token
        self._on_health = on_health
        self._mode = mode
        self._queue: asyncio.Queue[Tick | None] = asyncio.Queue(maxsize=queue_size)
        self._token_to_symbol: dict[int, str] = {}
        self._task: asyncio.Task[None] | None = None
        self._socket: Any | None = None
        self._closed = False
        self._dropped = 0
        self._connect = connect or _default_connect

    # -- the port ---------------------------------------------------------------

    async def subscribe(self, symbols: tuple[str, ...]) -> None:
        new = [s for s in symbols if s not in self._token_to_symbol.values()]
        if not new:
            return
        unresolved: list[str] = []
        added: list[int] = []
        for symbol in new:
            token = await self._resolve(symbol)
            if token is None:
                unresolved.append(symbol)
                continue
            self._token_to_symbol[token] = symbol
            added.append(token)
        if unresolved:
            await self._announce(
                "feed_symbol_unmapped",
                f"No Kite instrument for {', '.join(unresolved)} — not subscribed, so no "
                "alerts will be sent for it. The Kite instrument catalog may not be synced.",
            )
        if not added:
            return
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="kite-ticker")
        elif self._socket is not None:
            await self._send_subscriptions(self._socket, added)
        log.info("kite_socket_subscribed", symbols=[self._token_to_symbol[t] for t in added])

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
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
        if self._socket is not None:
            with contextlib.suppress(Exception):
                await self._socket.close()
        await self._queue.put(None)
        if self._dropped:
            log.warning("kite_socket_ticks_dropped", dropped=self._dropped)

    # -- the connection loop ----------------------------------------------------

    async def _run(self) -> None:
        backoff = _BACKOFF_START
        while not self._closed:
            try:
                async with self._connect(self._url) as socket:
                    self._socket = socket
                    log.info("kite_socket_connected")
                    # A reconnect restores nothing on Kite's side: re-send it all.
                    await self._send_subscriptions(socket, list(self._token_to_symbol))
                    backoff = _BACKOFF_START
                    await self._read(socket)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._socket = None
                if _is_auth_failure(exc):
                    await self._announce(
                        "token_rejected",
                        "Zerodha refused the stream: the session has expired. Reconnect Kite "
                        "in Settings → Broker.",
                    )
                    return  # retrying a refused token only gets the key throttled
                await self._announce(
                    "feed_disconnected", f"Kite socket dropped: {type(exc).__name__}"
                )
            # A method, not the attribute: close() runs concurrently, and mypy
            # would otherwise take the loop condition as still holding here.
            if self._is_closed():
                return
            await asyncio.sleep(backoff + random.uniform(0, backoff / 2))  # noqa: S311 — jitter
            backoff = min(backoff * 2, _BACKOFF_CEILING)

    def _is_closed(self) -> bool:
        return self._closed

    async def _read(self, socket: Any) -> None:
        while not self._closed:
            try:
                message = await asyncio.wait_for(socket.recv(), timeout=_SILENCE_SECONDS)
            except TimeoutError as exc:
                # Kite heartbeats every second; this much silence is a dead link
                # that has not noticed yet.
                msg = "no heartbeat"
                raise ConnectionError(msg) from exc
            if isinstance(message, bytes | bytearray):
                if len(message) == _HEARTBEAT:
                    continue
                arrived = datetime.now(UTC)
                for packet in parse_frame(bytes(message)):
                    self._offer(packet, arrived)
            else:
                await self._on_text(str(message))

    async def _on_text(self, text: str) -> None:
        try:
            data = json.loads(text)
        except ValueError:
            return
        if isinstance(data, dict) and data.get("type") == "error":
            detail = str(data.get("data") or "")[:200]
            await self._announce("feed_error", f"Kite stream error: {detail}")

    async def _send_subscriptions(self, socket: Any, tokens: Sequence[int]) -> None:
        if not tokens:
            return
        await socket.send(json.dumps({"a": "subscribe", "v": list(tokens)}))
        await socket.send(json.dumps({"a": "mode", "v": [self._mode, list(tokens)]}))

    def _offer(self, packet: KitePacket, arrived: datetime) -> None:
        symbol = self._token_to_symbol.get(packet.instrument_token)
        if symbol is None:
            return
        tick = Tick(symbol=symbol, price=packet.last_price, at=packet.exchange_time or arrived)
        try:
            self._queue.put_nowait(tick)
        except asyncio.QueueFull:
            # Drop the oldest, keep the newest: a level watcher wants the
            # current price, never a backlog of prices it has already missed.
            with contextlib.suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
            self._dropped += 1
            with contextlib.suppress(asyncio.QueueFull):
                self._queue.put_nowait(tick)

    async def _announce(self, reason: str, detail: str) -> None:
        log.warning("kite_socket_health", reason=reason)
        if self._on_health is None:
            return
        try:
            await self._on_health(reason, detail)
        except Exception as exc:
            log.error("kite_health_report_failed", error=repr(exc))


def _default_connect(url: str) -> Any:
    from websockets.asyncio.client import connect  # noqa: PLC0415

    return connect(url, open_timeout=10, ping_interval=None, max_size=2**22)


def _is_auth_failure(exc: Exception) -> bool:
    """A 403 on the handshake: Zerodha refused the token."""
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status in (401, 403)
