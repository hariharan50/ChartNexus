"""ATR from Kite's daily candles, chosen per call by the connected broker."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from chartnexus.contexts.trade_buddy.application.ports import BrokerCredentials
from chartnexus.infrastructure.trade_buddy.atr_source import FyersAtrSource, KiteDailyCandles

pytestmark = pytest.mark.unit


def _candles(n: int) -> list[list[Any]]:
    # A steady 100-point range each day: ATR converges on 100.
    return [
        [f"2026-07-{day:02d}T00:00:00+0530", 24000, 24100, 24000, 24050, 0]
        for day in range(1, n + 1)
    ]


class FixedCredentials:
    def __init__(self, broker: str) -> None:
        self._broker = broker

    async def fetch(self) -> BrokerCredentials:
        return BrokerCredentials(app_id="abc123xyz789", access_token="tok", broker=self._broker)


class KiteRest:
    def __init__(self, rows: list[list[Any]]) -> None:
        self.rows = rows
        self.calls: list[dict[str, Any]] = []

    async def fetch_historical(self, **kwargs: Any) -> list[list[Any]]:
        self.calls.append(kwargs)
        return self.rows


class FyersRestThatMustNotBeCalled:
    async def fetch_history(self, **_: Any) -> Any:
        raise AssertionError("a Kite connection must not reach the FYERS endpoint")


async def _resolve(symbol: str) -> int | None:
    return {"NIFTY": 256265}.get(symbol)


async def test_a_kite_connection_reads_daily_candles_by_token() -> None:
    rest = KiteRest(_candles(30))
    source = FyersAtrSource(
        FyersRestThatMustNotBeCalled(),  # type: ignore[arg-type]
        FixedCredentials("kite"),
        kite=KiteDailyCandles(rest, _resolve),
    )

    value = await source.atr("NIFTY", period=14)

    assert value == pytest.approx(100.0)
    call = rest.calls[0]
    assert call["instrument_token"] == 256265
    assert call["interval"] == "day"
    assert call["api_key"] == "abc123xyz789"
    assert isinstance(call["start"], datetime) and call["start"] < call["end"]


async def test_an_uncatalogued_symbol_degrades_to_none() -> None:
    source = FyersAtrSource(
        FyersRestThatMustNotBeCalled(),  # type: ignore[arg-type]
        FixedCredentials("kite"),
        kite=KiteDailyCandles(KiteRest(_candles(30)), _resolve),
    )
    assert await source.atr("UNKNOWN") is None


async def test_kite_without_the_kite_path_wired_degrades_to_none() -> None:
    source = FyersAtrSource(
        FyersRestThatMustNotBeCalled(),  # type: ignore[arg-type]
        FixedCredentials("kite"),
    )
    assert await source.atr("NIFTY") is None


async def test_thin_kite_history_is_not_an_atr() -> None:
    source = FyersAtrSource(
        FyersRestThatMustNotBeCalled(),  # type: ignore[arg-type]
        FixedCredentials("kite"),
        kite=KiteDailyCandles(KiteRest(_candles(5)), _resolve),
    )
    assert await source.atr("NIFTY", period=14) is None
