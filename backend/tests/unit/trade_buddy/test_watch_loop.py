"""The engine driven by a feed, end to end, with no network and no clock.

``ManualFeed`` implements the same ``TickFeed`` port as the Fyers socket, so
these exercise the real engine, the real state machine and the real router over
a scripted market. This is the closest thing to an integration test that can run
without a live session, and it is what the Fyers adapter is kept thin for: the
only thing untested below is the SDK's own frame delivery.
"""

from __future__ import annotations

import asyncio

import pytest

from chartnexus.contexts.trade_buddy.application.ports import Tick
from chartnexus.contexts.trade_buddy.application.routing import AlertRouter
from chartnexus.contexts.trade_buddy.application.watch import WatchEngine
from chartnexus.contexts.trade_buddy.domain.budget import LevelBudget, WhatsAppBudget
from chartnexus.contexts.trade_buddy.domain.events import AlertKind
from chartnexus.contexts.trade_buddy.domain.level import LevelMark, LevelRole
from chartnexus.infrastructure.trade_buddy.clock import FakeClock
from chartnexus.infrastructure.trade_buddy.manual_feed import ManualFeed
from tests.unit.trade_buddy.conftest import (
    SESSION_START,
    MemoryLevelStore,
    RecordingNotifier,
    RecordingSink,
    at,
    policy,
    window,
)

pytestmark = pytest.mark.unit

SYMBOL = "NSE:NIFTY50-INDEX"
MARKS = (
    LevelMark(label="R1", price=24_700.0, role=LevelRole.RESISTANCE),
    LevelMark(label="S1", price=24_600.0, role=LevelRole.SUPPORT),
)


async def drain(engine: WatchEngine, feed: ManualFeed) -> None:
    """Pump every queued tick through the engine, then stop."""
    await feed.close()
    async for tick in feed.ticks():
        await engine.on_tick(tick)


class TestManualFeedContract:
    async def test_it_satisfies_the_tick_feed_port(self):
        feed = ManualFeed()
        await feed.subscribe((SYMBOL,))
        assert feed.symbols == (SYMBOL,)

        await feed.push(Tick(symbol=SYMBOL, price=24_650.0, at=SESSION_START))
        await feed.close()

        received = [tick async for tick in feed.ticks()]
        assert [t.price for t in received] == [24_650.0]

    async def test_close_is_idempotent(self):
        feed = ManualFeed()
        await feed.close()
        await feed.close()
        assert [t async for t in feed.ticks()] == []


class TestEndToEnd:
    async def test_a_scripted_session_produces_the_expected_alert_sequence(self, store):
        """One full morning, through every real component except the socket."""
        store.mark(SYMBOL, *MARKS)
        sink = RecordingSink()
        clock = FakeClock(SESSION_START)
        engine = WatchEngine(
            symbol=SYMBOL,
            policy=policy(),
            window=window(),
            store=store,
            sink=sink,
            clock=clock,
            budget=LevelBudget(),
        )
        await engine.load()

        feed = ManualFeed()
        await feed.subscribe((SYMBOL,))
        script = [
            (24_650.0, 0.0),  # mid-range, nothing
            (24_680.0, 10.0),  # inside R1's approach band
            (24_697.0, 20.0),  # touching R1
            (24_715.0, 30.0),  # past the buffer — pending
            (24_705.0, 35.0),  # back inside before the hold — wick
            (24_716.0, 60.0),  # out again
            (24_720.0, 85.0),  # held past 20s — confirmed
        ]
        for price, offset in script:
            await feed.push(Tick(symbol=SYMBOL, price=price, at=at(offset)))

        await feed.close()
        async for tick in feed.ticks():
            clock.set(tick.at)
            while clock.monotonic() < (tick.at - SESSION_START).total_seconds():
                clock.advance(1.0)
            await engine.on_tick(tick)

        assert sink.kinds == [
            AlertKind.APPROACHING,
            AlertKind.TOUCHED,
            AlertKind.WICK_REJECTED,
            AlertKind.BREAK_CONFIRMED,
        ]

    async def test_the_router_receives_them_on_the_right_channels(self, store):
        """The same session, but through the real AlertRouter.

        Telegram sees all four; WhatsApp sees only the confirmed break. This is
        the asymmetry that protects the CallMeBot budget.
        """
        store.mark(SYMBOL, *MARKS)
        telegram = RecordingNotifier(name="telegram", rich=True)
        whatsapp = RecordingNotifier(name="whatsapp", rich=False)
        clock = FakeClock(SESSION_START)
        router = AlertRouter(
            telegram=telegram,
            whatsapp=whatsapp,
            clock=clock,
            budget=WhatsAppBudget(limit=10),
            backoff_seconds=0.0,
        )
        engine = WatchEngine(
            symbol=SYMBOL,
            policy=policy(),
            window=window(),
            store=store,
            sink=router,
            clock=clock,
            budget=LevelBudget(),
            whatsapp_budget=router.budget,
        )
        await engine.load()

        for price, offset in [
            (24_680.0, 0.0),
            (24_697.0, 10.0),
            (24_715.0, 20.0),
            (24_705.0, 25.0),
            (24_716.0, 40.0),
            (24_720.0, 65.0),
        ]:
            clock.set(at(offset))
            while clock.monotonic() < offset:
                clock.advance(1.0)
            await engine.on_tick(Tick(symbol=SYMBOL, price=price, at=at(offset)))

        assert len(telegram.sent) == 4
        assert len(whatsapp.sent) == 1
        assert "BROKEN" in whatsapp.sent[0]
        # And the spend was persisted for the next process.
        assert len((await store.load_runtime(SYMBOL)).whatsapp_sends) == 1

    async def test_a_malformed_tick_does_not_end_the_watch(self, store):
        """Swallow-and-survive: one bad tick must not end the session."""
        store.mark(SYMBOL, *MARKS)
        sink = RecordingSink()
        clock = FakeClock(SESSION_START)
        engine = WatchEngine(
            symbol=SYMBOL,
            policy=policy(),
            window=window(),
            store=store,
            sink=sink,
            clock=clock,
            budget=LevelBudget(),
        )
        await engine.load()

        # No try/except: an exception from any of these *is* the failure, and
        # letting it propagate names the offending tick instead of hiding it.
        for price, offset in [(24_697.0, 0.0), (float("nan"), 5.0), (24_698.0, 10.0)]:
            clock.set(at(offset))
            await engine.on_tick(Tick(symbol=SYMBOL, price=price, at=at(offset)))

        # The NaN tick matched no band, so only the two real touches register.
        assert sink.kinds == [AlertKind.TOUCHED]

    async def test_two_symbols_keep_separate_state(self, store):
        """Fan-out correctness: the runtime routes each tick by symbol."""
        other = "NSE:NIFTYBANK-INDEX"
        store.mark(SYMBOL, *MARKS)
        store.mark(other, LevelMark(label="R1", price=52_000.0, role=LevelRole.RESISTANCE))
        clock = FakeClock(SESSION_START)
        engines = {}
        sinks = {}
        for symbol in (SYMBOL, other):
            sinks[symbol] = RecordingSink()
            engines[symbol] = WatchEngine(
                symbol=symbol,
                policy=policy(),
                window=window(),
                store=store,
                sink=sinks[symbol],
                clock=clock,
                budget=LevelBudget(),
            )
            await engines[symbol].load()

        # A NIFTY tick must not touch the BANKNIFTY engine.
        await engines[SYMBOL].on_tick(Tick(symbol=SYMBOL, price=24_697.0, at=at(0.0)))

        assert sinks[SYMBOL].kinds == [AlertKind.TOUCHED]
        assert sinks[other].kinds == []


class TestConcurrentShutdown:
    async def test_closing_the_feed_ends_the_consumer(self):
        """The loop must exit on close rather than hanging on an empty queue."""
        feed = ManualFeed()
        await feed.subscribe((SYMBOL,))
        seen: list[Tick] = []

        async def consume() -> None:
            async for tick in feed.ticks():
                seen.append(tick)

        task = asyncio.create_task(consume())
        await feed.push(Tick(symbol=SYMBOL, price=24_650.0, at=SESSION_START))
        await feed.close()
        await asyncio.wait_for(task, timeout=2.0)

        assert len(seen) == 1


@pytest.fixture
def store() -> MemoryLevelStore:
    return MemoryLevelStore()
