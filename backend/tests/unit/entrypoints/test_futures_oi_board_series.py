"""With Kite, a whole OI series is one board read instead of a paced walk."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from chartnexus.contexts.market_data.domain.instruments import InstrumentSymbol
from chartnexus.entrypoints.futures_oi_runtime import _board_series

pytestmark = pytest.mark.unit

AT = datetime(2026, 8, 3, 5, 0, tzinfo=UTC)


def _quote(oi: int | None, previous: int | None = None) -> Any:
    return SimpleNamespace(
        last_price=Decimal("100"),
        open_interest=oi,
        previous_open_interest=previous,
        provenance=SimpleNamespace(fetched_at=AT),
    )


class BoardProvider:
    def __init__(self, board: dict[InstrumentSymbol, Any], *, fails: bool = False) -> None:
        self.board = board
        self.fails = fails
        self.calls: list[tuple[list[str], int]] = []

    async def get_futures_board(self, instruments: Any, *, series: int = 0) -> Any:
        self.calls.append(([i.value for i in instruments], series))
        if self.fails:
            raise RuntimeError("kite down")
        return self.board

    async def get_open_interest(self, *_: Any, **__: Any) -> Any:
        raise AssertionError("the Kite sweep must not walk contracts one by one")


async def test_one_board_read_fills_the_series() -> None:
    provider = BoardProvider(
        {
            InstrumentSymbol("NIFTY"): _quote(1_000_000, 950_000),
            InstrumentSymbol("RELIANCE"): _quote(250_000),
            InstrumentSymbol("TCS"): _quote(None),  # no OI: not cached
        }
    )

    readings = await _board_series(provider, ("NIFTY", "RELIANCE", "TCS"), 1)  # type: ignore[arg-type]

    assert provider.calls == [(["NIFTY", "RELIANCE", "TCS"], 1)]
    assert set(readings) == {"NIFTY", "RELIANCE"}
    assert readings["NIFTY"].open_interest == 1_000_000
    assert readings["NIFTY"].previous_open_interest == 950_000
    assert readings["NIFTY"].observed_at == AT


async def test_a_failed_board_read_is_an_empty_series_not_a_crash() -> None:
    provider = BoardProvider({}, fails=True)
    assert await _board_series(provider, ("NIFTY",), 0) == {}  # type: ignore[arg-type]
