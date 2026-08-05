"""Behaviour of the option-chain capture use case.

Pure: fakes stand in for the broker source, the writer, the clock, and the
calendar, so the tier rules — market-hours gate, mock policy, per-symbol
isolation, header-metric derivation — are asserted without a database or broker.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from marketcompass.contexts.market_ingestion.application.capture import CaptureChainSnapshots
from marketcompass.contexts.market_ingestion.application.ports import (
    ChainObservation,
    ChainRowToWrite,
    SnapshotToWrite,
)

# 04:00 UTC == 09:30 IST, inside the session, on 2026-08-04.
CAPTURED_AT = datetime(2026, 8, 4, 4, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


class FakeCalendar:
    def __init__(self, *, open_: bool) -> None:
        self._open = open_

    def is_open(self, moment: datetime) -> bool:
        return self._open


class FakeSource:
    """Returns a preset observation per symbol, or raises the preset error."""

    def __init__(self, results: dict[str, ChainObservation | Exception | None]) -> None:
        self._results = results
        self.asked: list[str] = []

    async def fetch(self, symbol: str) -> ChainObservation | None:
        self.asked.append(symbol)
        result = self._results.get(symbol)
        if isinstance(result, Exception):
            raise result
        return result


class FakeWriter:
    def __init__(self) -> None:
        self.saved: list[SnapshotToWrite] = []

    async def save(self, snapshot: SnapshotToWrite) -> None:
        self.saved.append(snapshot)


def _observation(symbol: str, *, source: str = "live", rows: bool = True) -> ChainObservation:
    legs: tuple[ChainRowToWrite, ...] = ()
    if rows:
        legs = (
            ChainRowToWrite(Decimal("100"), "CE", oi=200, oi_change=10, volume=5),
            ChainRowToWrite(Decimal("100"), "PE", oi=400, oi_change=20, volume=7),
            ChainRowToWrite(Decimal("110"), "CE", oi=100, oi_change=-5, volume=3),
            ChainRowToWrite(Decimal("110"), "PE", oi=600, oi_change=30, volume=9),
        )
    return ChainObservation(
        symbol=symbol,
        captured_at=CAPTURED_AT,
        spot=Decimal("104"),
        rows=legs,
        source=source,
        expiry="2026-08-07",
        lot_size=75,
    )


def _capture(source: FakeSource, writer: FakeWriter, *, open_: bool, allow_mock: bool = False):
    return CaptureChainSnapshots(
        source=source,
        writer=writer,
        calendar=FakeCalendar(open_=open_),
        clock=FakeClock(CAPTURED_AT),
        symbols=("NIFTY",),
        allow_mock=allow_mock,
    )


async def test_market_closed_writes_nothing() -> None:
    source = FakeSource({"NIFTY": _observation("NIFTY")})
    writer = FakeWriter()

    result = await _capture(source, writer, open_=False)()

    assert result.skipped_closed is True
    assert writer.saved == []
    assert source.asked == []  # not even fetched


async def test_mock_is_skipped_unless_allowed() -> None:
    source = FakeSource({"NIFTY": _observation("NIFTY", source="mock")})
    writer = FakeWriter()

    result = await _capture(source, writer, open_=True, allow_mock=False)()

    assert result.skipped_mock == ("NIFTY",)
    assert writer.saved == []


async def test_mock_is_written_when_allowed() -> None:
    source = FakeSource({"NIFTY": _observation("NIFTY", source="mock")})
    writer = FakeWriter()

    result = await _capture(source, writer, open_=True, allow_mock=True)()

    assert result.written == ("NIFTY",)
    assert writer.saved[0].source == "mock"


async def test_empty_chain_is_skipped() -> None:
    source = FakeSource({"NIFTY": _observation("NIFTY", rows=False)})
    writer = FakeWriter()

    result = await _capture(source, writer, open_=True)()

    assert result.skipped_empty == ("NIFTY",)
    assert writer.saved == []


async def test_live_snapshot_is_written_with_header_metrics() -> None:
    source = FakeSource({"NIFTY": _observation("NIFTY")})
    writer = FakeWriter()

    result = await _capture(source, writer, open_=True)()

    assert result.written == ("NIFTY",)
    snap = writer.saved[0]
    assert snap.symbol == "NIFTY"
    assert snap.session_date.isoformat() == "2026-08-04"  # IST date, not UTC
    assert snap.total_call_oi == 300  # 200 + 100
    assert snap.total_put_oi == 1000  # 400 + 600
    assert snap.pcr_oi == Decimal("3.3333")  # 1000 / 300
    assert snap.atm_strike == Decimal("100")  # nearest listed to spot 104
    assert snap.max_pain_strike in {Decimal("100"), Decimal("110")}
    assert len(snap.rows) == 4


@pytest.mark.parametrize("allow_mock", [False, True])
async def test_one_symbol_failure_does_not_sink_the_tick(allow_mock: bool) -> None:
    source = FakeSource(
        {
            "NIFTY": RuntimeError("broker exploded"),
            "BANKNIFTY": _observation("BANKNIFTY"),
        }
    )
    writer = FakeWriter()
    capture = CaptureChainSnapshots(
        source=source,
        writer=writer,
        calendar=FakeCalendar(open_=True),
        clock=FakeClock(CAPTURED_AT),
        symbols=("NIFTY", "BANKNIFTY"),
        allow_mock=allow_mock,
    )

    result = await capture()

    assert [s for s, _ in result.failed] == ["NIFTY"]
    assert result.written == ("BANKNIFTY",)
    assert [s.symbol for s in writer.saved] == ["BANKNIFTY"]
