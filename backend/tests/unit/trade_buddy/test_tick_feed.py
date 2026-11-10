"""The Fyers socket adapter, with the SDK replaced by a recorder.

This module had no tests, and it is the only one that speaks to the broker's
WebSocket — which is how both of the bugs below reached production while 348
other tests passed. Everything else in the suite drives `ManualFeed`, whose
`subscribe` merely records the tuple it was handed, so no test could see what
the real adapter would have put on the wire.

The two failures pinned here are the same mistake twice, and both are silent:

**The symbols were never translated.** `subscribe` was handed canonical names
(`BANKNIFTY`) and passed them straight to the SDK, which only understands the
exchange's own strings (`NSE:NIFTYBANK-INDEX`). A subscription the broker
cannot parse is not an error — it is a socket that connects, reports healthy
and delivers nothing for the rest of the session.

**The reconnect re-subscribed to nothing.** `_on_connect` re-sent
`list(self._broker_to_canonical)`, a dict that was never written to, so the
re-subscribe sent an empty list. A mid-session drop reconnected into permanent
silence, which is precisely what the comment above it claimed to prevent.

The SDK is stubbed rather than mocked at the port: the point is to assert on
the exact arguments that cross into `fyers_apiv3`, and a double at any higher
level would have been just as blind as `ManualFeed`.
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from typing import Any

import pytest


def _install_sdk_stub() -> None:
    """Stand in for ``fyers_apiv3`` when the package is not installed at all.

    ``fyers-stream`` is an optional extra, deliberately, so that the API
    process does not carry a broker SDK — and the integration job installs
    without it. That is no reason to leave this adapter the one untested module
    in the feature: the only thing it needs from the SDK is a
    ``FyersDataSocket`` to construct, and every test here replaces that with a
    recorder anyway, so nothing under test comes from the SDK.

    Not reached where the extra *is* installed, including CI's
    ``uv sync --all-extras`` — there the import below runs for real, which also
    exercises the ``pkg_resources`` shim in ``brokers/fyers/sdk.py``.
    """
    root = sys.modules.setdefault("fyers_apiv3", types.ModuleType("fyers_apiv3"))
    package = types.ModuleType("fyers_apiv3.FyersWebsocket")
    stub = types.ModuleType("fyers_apiv3.FyersWebsocket.data_ws")
    stub.FyersDataSocket = object  # type: ignore[attr-defined]
    package.data_ws = stub  # type: ignore[attr-defined]
    root.FyersWebsocket = package  # type: ignore[attr-defined]
    sys.modules["fyers_apiv3.FyersWebsocket"] = package
    sys.modules["fyers_apiv3.FyersWebsocket.data_ws"] = stub


try:
    from chartnexus.infrastructure.brokers.fyers import data_socket as module
except ModuleNotFoundError:  # the `fyers-stream` extra is not installed
    _install_sdk_stub()
    from chartnexus.infrastructure.brokers.fyers import data_socket as module

FyersTickFeed = module.FyersTickFeed

pytestmark = pytest.mark.unit

TOKEN = "APPID:TOKEN"  # the SDK's joined "APPID:TOKEN" form, not a real credential

#: What the catalog fixture in `tests/conftest.py` maps the three indices to.
NIFTY_WIRE = "NSE:NIFTY50-INDEX"
BANKNIFTY_WIRE = "NSE:NIFTYBANK-INDEX"
SENSEX_WIRE = "BSE:SENSEX-INDEX"


class FakeSocket:
    """Records what the adapter asks the SDK to do, and nothing else."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.connected = 0
        #: One entry per `subscribe` call, each the symbol list as sent.
        self.subscriptions: list[list[str]] = []
        self.closed = 0
        self.fail_subscribe = False

    def connect(self) -> None:
        self.connected += 1

    def subscribe(self, symbols: list[str], data_type: str) -> None:
        if self.fail_subscribe:
            raise RuntimeError("socket not ready")
        self.subscriptions.append(list(symbols))

    def close_connection(self) -> None:
        self.closed += 1

    # The adapter wires these in; a test fires them to simulate the SDK thread.
    def fire_connect(self) -> None:
        self.kwargs["on_connect"]()


@pytest.fixture
def sockets(monkeypatch) -> list[FakeSocket]:
    """Every socket the adapter builds, newest last."""
    built: list[FakeSocket] = []

    def _build(**kwargs: Any) -> FakeSocket:
        socket = FakeSocket(**kwargs)
        built.append(socket)
        return socket

    monkeypatch.setattr(module.data_ws, "FyersDataSocket", _build)
    return built


@pytest.fixture
def health() -> list[tuple[str, str]]:
    return []


async def _settle(reported: list[tuple[str, str]], *, passes: int = 10) -> None:
    """Wait for a health report that crossed the SDK-thread boundary.

    Reporting from a callback is a two-step hand-off — ``call_soon_threadsafe``
    schedules a callback that then creates the reporting task — so a single
    ``sleep(0)`` schedules it without running it. Yielding until it lands keeps
    the assertion about the adapter rather than about scheduling order.
    """
    for _ in range(passes):
        if reported:
            return
        await asyncio.sleep(0)


@pytest.fixture
def feed(sockets, health) -> FyersTickFeed:
    async def report(reason: str, detail: str) -> None:
        health.append((reason, detail))

    return FyersTickFeed(access_token=TOKEN, on_health=report)


class TestSdkPackagingShim:
    """The SDK imports `pkg_resources`, which setuptools 81 removed.

    Without the shim in `brokers/fyers/sdk.py` the adapter raises
    `ModuleNotFoundError` at import — and because `build_feed` imports it
    lazily, that surfaces at the first watch session rather than at startup.
    """

    def test_resource_filename_resolves_a_file_inside_a_package(self) -> None:
        from chartnexus.infrastructure.brokers.fyers.sdk import resource_filename  # noqa: PLC0415

        located = resource_filename("chartnexus.infrastructure.brokers.fyers", "sdk.py")

        assert Path(located).is_file()

    def test_the_sdk_module_is_reachable(self) -> None:
        """Whatever provides it — the real package here, a stub without the extra."""
        from chartnexus.infrastructure.brokers.fyers.sdk import data_ws  # noqa: PLC0415

        assert hasattr(data_ws, "FyersDataSocket")

    def test_the_real_sdk_imports_on_this_setuptools(self) -> None:
        """Skipped only where the optional extra is absent entirely."""
        pytest.importorskip("fyers_apiv3", reason="the fyers-stream extra is not installed")
        from chartnexus.infrastructure.brokers.fyers.sdk import data_ws  # noqa: PLC0415

        assert data_ws.FyersDataSocket.__name__ == "FyersDataSocket"


class TestSubscriptionSymbols:
    """The regression that matters: what actually goes on the wire."""

    async def test_canonical_names_are_translated_to_broker_symbols(self, feed, sockets):
        await feed.subscribe(("NIFTY", "BANKNIFTY", "SENSEX"))

        assert sockets[0].subscriptions == [[NIFTY_WIRE, BANKNIFTY_WIRE, SENSEX_WIRE]]

    async def test_banknifty_reaches_the_root_it_is_quoted_under(self, feed, sockets):
        """`BANKNIFTY` is quoted `NIFTYBANK` — not derivable, hence the catalog."""
        await feed.subscribe(("BANKNIFTY",))

        assert sockets[0].subscriptions == [[BANKNIFTY_WIRE]]

    async def test_sensex_crosses_to_its_own_exchange(self, feed, sockets):
        """SENSEX is a BSE symbol; an `NSE:` prefix would subscribe to nothing."""
        await feed.subscribe(("SENSEX",))

        assert sockets[0].subscriptions == [[SENSEX_WIRE]]

    async def test_no_canonical_name_ever_reaches_the_sdk(self, feed, sockets):
        await feed.subscribe(("NIFTY", "BANKNIFTY", "SENSEX"))

        sent = [symbol for call in sockets[0].subscriptions for symbol in call]
        assert not {"NIFTY", "BANKNIFTY", "SENSEX"} & set(sent)

    async def test_the_socket_is_connected_once_for_a_later_addition(self, feed, sockets):
        """A newly marked instrument joins mid-session without dropping the socket."""
        await feed.subscribe(("NIFTY",))
        await feed.subscribe(("SENSEX",))

        assert len(sockets) == 1
        assert sockets[0].connected == 1
        assert sockets[0].subscriptions == [[NIFTY_WIRE], [SENSEX_WIRE]]

    async def test_a_repeat_subscription_is_not_re_sent(self, feed, sockets):
        await feed.subscribe(("NIFTY",))
        await feed.subscribe(("NIFTY",))

        assert sockets[0].subscriptions == [[NIFTY_WIRE]]

    async def test_symbols_reports_the_canonical_names(self, feed):
        """What is watched is reported in the vocabulary the engine speaks."""
        await feed.subscribe(("NIFTY", "SENSEX"))

        assert feed._symbols == ("NIFTY", "SENSEX")


class TestUnmappableSymbols:
    """A symbol the catalog cannot place must be loud, not dropped."""

    async def test_it_is_reported_through_the_health_channel(self, feed, health):
        await feed.subscribe(("NOTLISTED",))

        assert [reason for reason, _ in health] == ["feed_symbol_unmapped"]
        assert "NOTLISTED" in health[0][1]

    async def test_no_socket_is_opened_for_nothing(self, feed, sockets):
        """A connected socket subscribed to nothing looks healthy and is not."""
        await feed.subscribe(("NOTLISTED",))

        assert sockets == []

    async def test_it_is_not_recorded_as_watched(self, feed):
        await feed.subscribe(("NOTLISTED",))

        assert feed._symbols == ()

    async def test_a_mixed_batch_subscribes_what_it_can(self, feed, sockets, health):
        await feed.subscribe(("NIFTY", "NOTLISTED"))

        assert sockets[0].subscriptions == [[NIFTY_WIRE]]
        assert feed._symbols == ("NIFTY",)
        assert [reason for reason, _ in health] == ["feed_symbol_unmapped"]


class TestReconnect:
    """The SDK does not restore subscriptions, so the adapter must."""

    async def test_a_reconnect_re_sends_the_broker_symbols(self, feed, sockets):
        await feed.subscribe(("NIFTY", "BANKNIFTY"))

        sockets[0].fire_connect()

        assert sockets[0].subscriptions == [
            [NIFTY_WIRE, BANKNIFTY_WIRE],
            [NIFTY_WIRE, BANKNIFTY_WIRE],
        ]

    async def test_it_re_sends_nothing_before_anything_was_subscribed(self, feed, sockets):
        await feed.subscribe(("NIFTY",))
        sockets[0].subscriptions.clear()
        feed._broker_symbols = ()

        sockets[0].fire_connect()

        assert sockets[0].subscriptions == []

    async def test_a_failed_re_subscribe_is_reported_rather_than_swallowed(
        self, feed, sockets, health
    ):
        """A connected socket delivering nothing is the hardest failure to see."""
        await feed.subscribe(("NIFTY",))
        sockets[0].fail_subscribe = True

        sockets[0].fire_connect()
        await _settle(health)

        assert [reason for reason, _ in health] == ["feed_resubscribe_failed"]


class TestInboundFrames:
    """Frames arrive carrying broker strings and must come back out canonical."""

    async def _first_tick(self, feed, frame: dict[str, Any]):
        feed._on_message(frame)
        await asyncio.sleep(0)  # `call_soon_threadsafe` runs on the next pass
        return await asyncio.wait_for(feed._queue.get(), timeout=1.0)

    async def test_a_frame_maps_back_to_the_canonical_name(self, feed):
        await feed.subscribe(("BANKNIFTY",))

        tick = await self._first_tick(feed, {"symbol": BANKNIFTY_WIRE, "ltp": 57_900.5})

        assert tick.symbol == "BANKNIFTY"
        assert tick.price == 57_900.5

    async def test_the_mapping_is_case_insensitive(self, feed):
        await feed.subscribe(("NIFTY",))

        tick = await self._first_tick(feed, {"symbol": NIFTY_WIRE.lower(), "ltp": 24_650.0})

        assert tick.symbol == "NIFTY"

    async def test_each_index_is_attributed_to_itself(self, feed):
        """Attributing a BANKNIFTY tick to NIFTY would compare the wrong price
        against the wrong levels — the one error worse than a missing tick."""
        await feed.subscribe(("NIFTY", "BANKNIFTY", "SENSEX"))

        for wire, expected, price in (
            (NIFTY_WIRE, "NIFTY", 24_650.0),
            (BANKNIFTY_WIRE, "BANKNIFTY", 57_900.0),
            (SENSEX_WIRE, "SENSEX", 81_000.0),
        ):
            tick = await self._first_tick(feed, {"symbol": wire, "ltp": price})
            assert (tick.symbol, tick.price) == (expected, price)

    async def test_an_unknown_symbol_is_dropped(self, feed):
        await feed.subscribe(("NIFTY",))

        feed._on_message({"symbol": "NSE:RANDOM-EQ", "ltp": 100.0})
        await asyncio.sleep(0)

        assert feed._queue.empty()

    async def test_a_symbolless_frame_falls_back_only_on_a_sole_subscription(self, feed):
        """Litemode sometimes omits the symbol. One subscription makes that
        unambiguous; more than one does not, and guessing would misattribute."""
        await feed.subscribe(("NIFTY",))
        tick = await self._first_tick(feed, {"ltp": 24_650.0})
        assert tick.symbol == "NIFTY"

        await feed.subscribe(("BANKNIFTY",))
        feed._on_message({"ltp": 57_900.0})
        await asyncio.sleep(0)
        assert feed._queue.empty()
