"""Kite's binary tick format, and the feed's subscribe/reconnect behaviour."""

from __future__ import annotations

import asyncio
import json
import struct
from datetime import UTC, datetime
from typing import Any

import pytest

from chartnexus.infrastructure.brokers.kite.ticker import (
    KiteTickFeed,
    parse_frame,
    price_divisor,
    socket_url,
)

pytestmark = pytest.mark.unit

NIFTY = 256265  # low byte 9: indices segment
FUTURE = 13238786  # low byte 2: NFO
EPOCH = 1_785_729_600  # 2026-08-03T04:00:00Z


def _frame(*packets: bytes) -> bytes:
    out = struct.pack(">H", len(packets))
    for packet in packets:
        out += struct.pack(">H", len(packet)) + packet
    return out


def _ltp(token: int, paise: int) -> bytes:
    return struct.pack(">ii", token, paise)


def _index_quote(token: int, paise: int) -> bytes:
    # token, ltp, high, low, open, close, change
    return struct.pack(">7i", token, paise, paise + 100, paise - 100, paise, paise - 50, 50)


def _index_full(token: int, paise: int, epoch: int) -> bytes:
    return _index_quote(token, paise) + struct.pack(">i", epoch)


def _quote(token: int, paise: int, volume: int) -> bytes:
    # token, ltp, last_qty, avg, volume, buy_qty, sell_qty, open, high, low, close
    return struct.pack(">11i", token, paise, 75, paise, volume, 10, 20, paise, paise, paise, paise)


def _full(token: int, paise: int, volume: int, oi: int, epoch: int) -> bytes:
    head = _quote(token, paise, volume)
    # last_trade_time, oi, oi_day_high, oi_day_low, exchange_timestamp
    extra = struct.pack(">5i", epoch, oi, oi + 10, oi - 10, epoch)
    depth = bytes(120)  # 10 depth entries of 12 bytes
    return head + extra + depth


class TestParseFrame:
    def test_a_heartbeat_is_nothing(self) -> None:
        assert parse_frame(b"\x00") == []

    def test_ltp_packet_in_rupees(self) -> None:
        (packet,) = parse_frame(_frame(_ltp(NIFTY, 2_450_015)))
        assert len(_ltp(NIFTY, 1)) == 8
        assert packet.instrument_token == NIFTY
        assert packet.last_price == pytest.approx(24500.15)
        assert packet.mode == "ltp"

    def test_index_quote_packet(self) -> None:
        body = _index_quote(NIFTY, 2_450_000)
        assert len(body) == 28
        (packet,) = parse_frame(_frame(body))
        assert packet.mode == "quote"
        assert packet.last_price == pytest.approx(24500.0)
        assert packet.exchange_time is None

    def test_index_full_packet_carries_the_exchange_time(self) -> None:
        body = _index_full(NIFTY, 2_450_000, EPOCH)
        assert len(body) == 32
        (packet,) = parse_frame(_frame(body))
        assert packet.mode == "full"
        assert packet.exchange_time == datetime.fromtimestamp(EPOCH, tz=UTC)

    def test_quote_packet_carries_volume(self) -> None:
        body = _quote(FUTURE, 2_460_050, 123_456)
        assert len(body) == 44
        (packet,) = parse_frame(_frame(body))
        assert packet.mode == "quote"
        assert packet.volume == 123_456
        assert packet.open_interest is None

    def test_full_packet_carries_oi_and_time(self) -> None:
        body = _full(FUTURE, 2_460_050, 1000, 9_876_543, EPOCH)
        assert len(body) == 184
        (packet,) = parse_frame(_frame(body))
        assert packet.mode == "full"
        assert packet.last_price == pytest.approx(24600.50)
        assert packet.open_interest == 9_876_543
        assert packet.exchange_time == datetime.fromtimestamp(EPOCH, tz=UTC)

    def test_several_packets_in_one_frame(self) -> None:
        packets = parse_frame(_frame(_ltp(NIFTY, 2_450_000), _ltp(FUTURE, 2_460_000)))
        assert [p.instrument_token for p in packets] == [NIFTY, FUTURE]

    def test_a_zero_price_is_not_a_price(self) -> None:
        assert parse_frame(_frame(_ltp(NIFTY, 0))) == []

    def test_an_unknown_length_is_skipped_not_guessed(self) -> None:
        odd = _ltp(NIFTY, 2_450_000) + b"\x00" * 4  # 12 bytes
        packets = parse_frame(_frame(odd, _ltp(FUTURE, 2_460_000)))
        assert [p.instrument_token for p in packets] == [FUTURE]

    def test_a_truncated_frame_keeps_what_was_whole(self) -> None:
        frame = _frame(_ltp(NIFTY, 2_450_000), _ltp(FUTURE, 2_460_000))[:-3]
        assert [p.instrument_token for p in parse_frame(frame)] == [NIFTY]

    def test_currency_segments_use_their_own_divisor(self) -> None:
        assert price_divisor(NIFTY) == 100.0
        assert price_divisor(0x0103) == 10_000_000.0  # CDS
        assert price_divisor(0x0106) == 10_000.0  # BCD


class FakeSocket:
    """Delivers scripted frames, records what the feed sends."""

    def __init__(self, frames: list[Any]) -> None:
        self.frames = list(frames)
        self.sent: list[dict[str, Any]] = []
        self.closed = False

    async def send(self, message: str) -> None:
        self.sent.append(json.loads(message))

    async def recv(self) -> Any:
        if self.frames:
            return self.frames.pop(0)
        await asyncio.sleep(3600)
        return b"\x00"

    async def close(self) -> None:
        self.closed = True

    def __aiter__(self) -> FakeSocket:
        return self

    async def __anext__(self) -> Any:
        if self.frames:
            return self.frames.pop(0)
        raise StopAsyncIteration

    async def __aenter__(self) -> FakeSocket:
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.closed = True


async def _resolve(symbol: str) -> int | None:
    return {"NIFTY": NIFTY}.get(symbol)


class TestFeed:
    def test_the_socket_url_carries_key_and_token(self) -> None:
        url = socket_url("wss://ws.kite.trade", api_key="k", access_token="t")
        assert url == "wss://ws.kite.trade?api_key=k&access_token=t"

    async def test_an_unresolvable_symbol_is_announced_not_subscribed(self) -> None:
        announced: list[tuple[str, str]] = []

        async def health(reason: str, detail: str) -> None:
            announced.append((reason, detail))

        sockets: list[FakeSocket] = []

        def connect(url: str) -> FakeSocket:
            sockets.append(FakeSocket([]))
            return sockets[-1]

        feed = KiteTickFeed(
            api_key="k", access_token="t", resolve_token=_resolve, on_health=health, connect=connect
        )
        await feed.subscribe(("NOPE",))
        await feed.close()

        assert announced and announced[0][0] == "feed_symbol_unmapped"
        assert sockets == []  # nothing to stream, so no socket opened

    async def test_ticks_flow_and_subscriptions_are_sent(self) -> None:
        sockets: list[FakeSocket] = []

        def connect(url: str) -> FakeSocket:
            sockets.append(FakeSocket([_frame(_ltp(NIFTY, 2_450_015))]))
            return sockets[-1]

        feed = KiteTickFeed(api_key="k", access_token="t", resolve_token=_resolve, connect=connect)
        await feed.subscribe(("NIFTY",))

        ticks = feed.ticks()
        tick = await asyncio.wait_for(anext(ticks), timeout=2)
        await feed.close()

        assert tick.symbol == "NIFTY"
        assert tick.price == pytest.approx(24500.15)
        actions = [message["a"] for message in sockets[0].sent]
        assert actions[:2] == ["subscribe", "mode"]
        assert sockets[0].sent[0]["v"] == [NIFTY]

    async def test_every_reconnect_re_subscribes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Kite forgets subscriptions with the socket; a feed that didn't resend
        them would reconnect into silence."""
        monkeypatch.setattr("chartnexus.infrastructure.brokers.kite.ticker._BACKOFF_START", 0.01)
        announced: list[str] = []

        async def health(reason: str, detail: str) -> None:
            announced.append(reason)

        class DroppingSocket(FakeSocket):
            async def recv(self) -> Any:
                raise ConnectionResetError("gone")

        sockets: list[FakeSocket] = []

        def connect(url: str) -> FakeSocket:
            if not sockets:
                sockets.append(DroppingSocket([]))
            else:
                sockets.append(FakeSocket([_frame(_ltp(NIFTY, 2_450_000))]))
            return sockets[-1]

        feed = KiteTickFeed(
            api_key="k", access_token="t", resolve_token=_resolve, on_health=health, connect=connect
        )
        await feed.subscribe(("NIFTY",))
        tick = await asyncio.wait_for(anext(feed.ticks()), timeout=3)
        await feed.close()

        assert tick.price == pytest.approx(24500.0)
        assert len(sockets) == 2
        assert all(s.sent and s.sent[0] == {"a": "subscribe", "v": [NIFTY]} for s in sockets)
        assert "feed_disconnected" in announced

    async def test_a_refused_token_stops_retrying(self) -> None:
        announced: list[str] = []

        async def health(reason: str, detail: str) -> None:
            announced.append(reason)

        class RefusedError(Exception):
            response = type("Response", (), {"status_code": 403})()

        attempts = {"n": 0}

        def connect(url: str) -> Any:
            attempts["n"] += 1
            raise RefusedError

        feed = KiteTickFeed(
            api_key="k", access_token="t", resolve_token=_resolve, on_health=health, connect=connect
        )
        await feed.subscribe(("NIFTY",))
        await asyncio.sleep(0.05)
        await feed.close()

        assert announced == ["token_rejected"]
        assert attempts["n"] == 1

    async def test_a_full_queue_drops_the_oldest(self) -> None:
        feed = KiteTickFeed(
            api_key="k", access_token="t", resolve_token=_resolve, queue_size=2, connect=FakeSocket
        )
        feed._token_to_symbol[NIFTY] = "NIFTY"
        arrived = datetime(2026, 8, 3, 4, 0, tzinfo=UTC)
        for paise in (100, 200, 300):
            for packet in parse_frame(_frame(_ltp(NIFTY, paise))):
                feed._offer(packet, arrived)

        ticks = feed.ticks()
        prices = [(await anext(ticks)).price, (await anext(ticks)).price]
        assert prices == [2.0, 3.0]
