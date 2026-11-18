"""KiteMarketDataProvider: a composed option chain and chunked history."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from chartnexus.contexts.broker_connections.domain.errors import BrokerRejectedError
from chartnexus.contexts.broker_connections.domain.value_objects import (
    BrokerCredentials,
    BrokerName,
)
from chartnexus.contexts.market_data.domain.instruments import InstrumentSymbol
from chartnexus.contexts.market_data.domain.market_data import CandleInterval
from chartnexus.infrastructure.brokers.fyers.circuit_breaker import CircuitBreaker
from chartnexus.infrastructure.brokers.fyers.retry_policy import RetryPolicy
from chartnexus.infrastructure.brokers.kite.client import (
    KiteMarketDataProvider,
    _pick_expiry,
    _strike_window,
)
from chartnexus.infrastructure.brokers.kite.instruments import KiteInstrument
from chartnexus.infrastructure.brokers.quota import NullBucketQuota

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 3, 6, 0, tzinfo=UTC)  # 11:30 IST
NEAR = date(2026, 8, 6)
NEXT = date(2026, 8, 13)
NIFTY = InstrumentSymbol("NIFTY")


def _contract(token: int, strike: int, kind: str, expiry: date = NEAR) -> KiteInstrument:
    return KiteInstrument(
        instrument_token=token,
        exchange="NFO",
        segment="NFO-OPT",
        tradingsymbol=f"NIFTY{expiry:%y%m%d}{strike}{kind}",
        name="NIFTY",
        instrument_type=kind,
        expiry=expiry,
        strike=Decimal(strike),
        lot_size=75,
        tick_size=Decimal("0.05"),
    )


STRIKES = list(range(23000, 26050, 50))  # 61 strikes
CONTRACTS = [
    _contract(10_000 + index * 2 + offset, strike, kind)
    for index, strike in enumerate(STRIKES)
    for offset, kind in enumerate(("CE", "PE"))
]
FUTURE = KiteInstrument(
    instrument_token=13238786,
    exchange="NFO",
    segment="NFO-FUT",
    tradingsymbol="NIFTY26AUGFUT",
    name="NIFTY",
    instrument_type="FUT",
    expiry=date(2026, 8, 27),
    strike=None,
    lot_size=75,
    tick_size=Decimal("0.1"),
)
SPOT = KiteInstrument(
    instrument_token=256265,
    exchange="NSE",
    segment="INDICES",
    tradingsymbol="NIFTY 50",
    name="NIFTY 50",
    instrument_type="EQ",
    expiry=None,
    strike=None,
    lot_size=0,
    tick_size=Decimal("0.05"),
)


class FakeInstruments:
    async def option_expiries(self, root: str, exchange: str) -> list[date]:
        return [NEAR, NEXT]

    async def options(self, root: str, exchange: str, expiry: date) -> list[KiteInstrument]:
        return [c for c in CONTRACTS if c.expiry == expiry]

    async def futures(self, root: str, exchange: str) -> list[KiteInstrument]:
        return [FUTURE]

    async def spot(self, symbol: str, listing: str) -> KiteInstrument | None:
        return SPOT if symbol == "NIFTY" else None


class FakeRest:
    def __init__(self) -> None:
        self.quote_batches: list[list[str]] = []
        self.history_calls: list[tuple[datetime, datetime, str]] = []

    async def fetch_quotes(self, *, instruments: Sequence[str], **_: Any) -> dict[str, Any]:
        self.quote_batches.append(list(instruments))
        out: dict[str, Any] = {}
        for key in instruments:
            if key == "NSE:NIFTY 50":
                out[key] = {"last_price": 24512.3, "ohlc": {"close": 24400.0}}
            elif key == "NSE:INDIA VIX":
                out[key] = {"last_price": 13.2, "ohlc": {"close": 13.0}}
            elif key.endswith("FUT"):
                out[key] = {"last_price": 24580.0, "oi": 1_000_000, "ohlc": {"close": 24450.0}}
            else:
                out[key] = {"last_price": 100.0, "oi": 5000, "volume": 10, "ohlc": {"close": 90}}
        return out

    async def fetch_historical(
        self, *, start: datetime, end: datetime, interval: str, **_: Any
    ) -> list[list[Any]]:
        self.history_calls.append((start, end, interval))
        # One candle at the chunk's start and one at its end: the seams overlap.
        return [
            [start.isoformat(), 1, 2, 0.5, 1.5, 100],
            [end.isoformat(), 1, 2, 0.5, 1.5, 100],
        ]


class PassThroughQuotes:
    async def quotes(self, keys: Sequence[str], fetch: Any) -> dict[str, Any]:
        return dict(await fetch(list(keys)))


class NoPreviousOi:
    async def read(self, session: date, tokens: Any) -> dict[int, int]:
        return {}


class FixedClock:
    def now(self) -> datetime:
        return NOW


def _provider(rest: FakeRest, *, each_side: int = 5) -> KiteMarketDataProvider:
    return KiteMarketDataProvider(
        rest=rest,  # type: ignore[arg-type]
        credentials=BrokerCredentials.parse(
            "abc123xyz789", "s3cretvalue0123456789", BrokerName.KITE
        ),
        access_token="tok",
        quota=NullBucketQuota(),
        breaker=CircuitBreaker(failure_threshold=5),
        quotes=PassThroughQuotes(),  # type: ignore[arg-type]
        instruments=FakeInstruments(),  # type: ignore[arg-type]
        previous_oi=NoPreviousOi(),  # type: ignore[arg-type]
        retry=RetryPolicy(attempts=1),
        clock=FixedClock(),  # type: ignore[arg-type]
        strikes_each_side=each_side,
    )


class TestStrikeWindow:
    def test_it_centres_on_the_nearest_strike(self) -> None:
        window = _strike_window(CONTRACTS, 24512.3, 2)
        assert sorted({int(c.strike or 0) for c in window}) == [24400, 24450, 24500, 24550, 24600]
        assert len(window) == 10  # CE and PE for each

    def test_it_is_clipped_at_the_edges(self) -> None:
        window = _strike_window(CONTRACTS, 1.0, 3)
        assert sorted({int(c.strike or 0) for c in window}) == [23000, 23050, 23100, 23150]

    def test_an_unreadable_spot_falls_back_to_the_middle(self) -> None:
        window = _strike_window(CONTRACTS, None, 0)
        assert {int(c.strike or 0) for c in window} == {STRIKES[len(STRIKES) // 2]}

    def test_no_contracts_no_window(self) -> None:
        assert _strike_window([], 24500, 5) == []


class TestPickExpiry:
    def test_nearest_by_default(self) -> None:
        assert _pick_expiry([NEAR, NEXT], None) == NEAR

    def test_a_listed_request_is_honoured(self) -> None:
        assert _pick_expiry([NEAR, NEXT], NEXT.isoformat()) == NEXT

    def test_an_unlisted_request_falls_back(self) -> None:
        assert _pick_expiry([NEAR, NEXT], "2026-12-31") == NEAR
        assert _pick_expiry([NEAR, NEXT], "garbage") == NEAR


class TestOptionChain:
    async def test_the_chain_is_composed_from_one_window_quote(self) -> None:
        rest = FakeRest()
        chain = await _provider(rest, each_side=5).get_option_chain(NIFTY)

        assert chain.expiry == NEAR.isoformat()
        assert chain.expiries == (NEAR.isoformat(), NEXT.isoformat())
        assert chain.spot_price == Decimal("24512.3")
        assert len(chain.strikes) == 11
        assert chain.strikes[5].strike == Decimal(24500)  # ATM in the middle
        assert all(row.call is not None and row.put is not None for row in chain.strikes)
        assert chain.lot_size == 75
        assert chain.future_price == Decimal("24580.0")
        assert chain.india_vix == Decimal("13.2")

        # The spot first (for ATM), then everything else in one request.
        assert rest.quote_batches[0] == ["NSE:NIFTY 50"]
        window_batch = rest.quote_batches[-1]
        assert {"NSE:NIFTY 50", "NSE:INDIA VIX", "NFO:NIFTY26AUGFUT"} <= set(window_batch)
        assert len(window_batch) == 3 + 22

    async def test_a_requested_expiry_is_used(self) -> None:
        chain = await _provider(FakeRest()).get_option_chain(NIFTY, NEXT.isoformat())
        assert chain.expiry == NEXT.isoformat()

    async def test_no_listed_options_is_a_clear_rejection(self) -> None:
        class Empty(FakeInstruments):
            async def option_expiries(self, root: str, exchange: str) -> list[date]:
                return []

        provider = _provider(FakeRest())
        provider._instruments = Empty()  # type: ignore[assignment]
        with pytest.raises(BrokerRejectedError, match="instrument catalog"):
            await provider.get_option_chain(NIFTY)

    async def test_the_window_quote_never_exceeds_500(self) -> None:
        rest = FakeRest()
        await _provider(rest, each_side=60).get_option_chain(NIFTY)
        assert all(len(batch) <= 500 for batch in rest.quote_batches)


class TestHistory:
    async def test_a_long_minute_range_is_split_into_60_day_requests(self) -> None:
        rest = FakeRest()
        await _provider(rest).get_history(NIFTY, CandleInterval.M1, 150)

        assert [interval for *_, interval in rest.history_calls] == ["minute"] * 3
        spans = [end - start for start, end, _ in rest.history_calls]
        assert spans[0] == timedelta(days=60)
        assert spans[1] == timedelta(days=60)
        assert spans[2] == timedelta(days=30)
        # Consecutive: each chunk starts where the last ended.
        for (_, end, _), (start, _, _) in zip(
            rest.history_calls, rest.history_calls[1:], strict=False
        ):
            assert start == end

    async def test_seam_candles_are_not_duplicated(self) -> None:
        series = await _provider(FakeRest()).get_history(NIFTY, CandleInterval.M1, 150)
        opened = [candle.opened_at for candle in series.candles]
        assert len(opened) == len(set(opened)) == 4

    async def test_a_daily_range_is_one_request(self) -> None:
        rest = FakeRest()
        await _provider(rest).get_history(NIFTY, CandleInterval.D1, 365)
        assert len(rest.history_calls) == 1
        assert rest.history_calls[0][2] == "day"

    async def test_an_uncatalogued_symbol_is_rejected(self) -> None:
        with pytest.raises(BrokerRejectedError, match="catalog"):
            await _provider(FakeRest()).get_history(
                InstrumentSymbol("RELIANCE"), CandleInterval.D1, 30
            )
