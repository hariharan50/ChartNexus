"""Behaviour of the option-chain capture use case.

Pure: fakes stand in for the broker source, the writer, the clock, and the
calendar, so the tier rules — market-hours gate, mock policy, per-symbol
isolation, header-metric derivation — are asserted without a database or broker.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
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
    """Returns a preset observation per symbol, or raises the preset error.

    An observation comes back stamped with the expiry it was asked for, because
    a real source returns a different contract's book for each one. A fake that
    handed back the same expiry every time would make the capture loop's
    per-contract duplicate check reject every expiry after the first.
    """

    def __init__(
        self,
        results: dict[str, ChainObservation | Exception | None],
        listed: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        self._results = results
        self.listed = listed or {}
        self.asked: list[str] = []

    async def expiries(self, symbol: str) -> tuple[str, ...]:
        return self.listed.get(symbol, ())

    async def fetch(self, symbol: str, *, expiry: str | None = None) -> ChainObservation | None:
        self.asked.append(symbol)
        result = self._results.get(symbol)
        if isinstance(result, Exception):
            raise result
        if result is not None and expiry is not None:
            return replace(result, expiry=expiry)
        return result

    def set(self, symbol: str, result: ChainObservation) -> None:
        """Change what the next fetch answers, for multi-tick tests."""
        self._results[symbol] = result


class FakeWriter:
    def __init__(self) -> None:
        self.saved: list[SnapshotToWrite] = []

    async def save(self, snapshot: SnapshotToWrite) -> None:
        self.saved.append(snapshot)

    async def latest_rows(
        self, symbol: str, session_date: date, expiry: str | None = None
    ) -> tuple[ChainRowToWrite, ...] | None:
        # Honours the expiry scope, as the real repository does: a fake that
        # ignored it would compare each contract against whichever was written
        # last and reject every expiry after the first as a duplicate.
        for snapshot in reversed(self.saved):
            if snapshot.symbol != symbol or snapshot.session_date != session_date:
                continue
            if expiry is not None and snapshot.expiry != expiry:
                continue
            return snapshot.rows
        return None

    async def has_source(self, symbol: str, session_date: date, source: str) -> bool:
        return any(
            s.symbol == symbol and s.session_date == session_date and s.source == source
            for s in self.saved
        )


def _observation(
    symbol: str, *, source: str = "live", rows: bool = True, oi: int = 200
) -> ChainObservation:
    legs: tuple[ChainRowToWrite, ...] = ()
    if rows:
        legs = (
            ChainRowToWrite(Decimal("100"), "CE", oi=oi, oi_change=10, volume=5),
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


def _capture(
    source: FakeSource,
    writer: FakeWriter,
    *,
    open_: bool,
    allow_mock: bool = False,
    expiries: int = 1,
):
    return CaptureChainSnapshots(
        source=source,
        writer=writer,
        calendar=FakeCalendar(open_=open_),
        clock=FakeClock(CAPTURED_AT),
        symbols=("NIFTY",),
        allow_mock=allow_mock,
        expiries=expiries,
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


# -- a frozen tape ----------------------------------------------------------


async def test_an_identical_capture_is_not_stored_twice() -> None:
    """A repeated tape must leave a gap, not a wall of identical frames.

    `ExchangeCalendar.holidays` is empty, so on an NSE holiday the calendar
    reports the market open and the provider keeps answering with the same
    chain. Storing every one of those would leave the Open Interest tool's
    timeline fully populated and completely inert — a far more confusing
    failure than an honest gap.
    """
    writer = FakeWriter()
    capture = _capture(FakeSource({"NIFTY": _observation("NIFTY")}), writer, open_=True)

    first = await capture()
    second = await capture()

    assert first.written == ("NIFTY",)
    assert second.written == ()
    assert second.skipped_unchanged == ("NIFTY",)
    assert len(writer.saved) == 1


async def test_a_changed_capture_is_still_stored() -> None:
    writer = FakeWriter()
    original = _observation("NIFTY")
    source = FakeSource({"NIFTY": original})
    capture = _capture(source, writer, open_=True)
    await capture()

    # One leg moves — that is a real tick and must be archived.
    source.set(
        "NIFTY", replace(original, rows=(replace(original.rows[0], oi=999_999), *original.rows[1:]))
    )
    result = await capture()

    assert result.written == ("NIFTY",)
    assert len(writer.saved) == 2


async def test_mock_never_follows_live_within_a_session() -> None:
    """A broker that drops out mid-session must leave a gap, not a seam.

    Splicing a fabricated afternoon onto a real morning draws one continuous
    line with nothing on screen marking where the real data stopped. An honest
    gap is recoverable; a seam quietly misleads.
    """
    writer = FakeWriter()
    source = FakeSource({"NIFTY": _observation("NIFTY", source="live")})
    capture = _capture(source, writer, open_=True, allow_mock=True)
    await capture()

    # The connection drops; the resolver falls back to the simulator.
    source.set("NIFTY", _observation("NIFTY", source="mock", oi=555_555))
    result = await capture()

    assert result.skipped_mock == ("NIFTY",)
    assert [s.source for s in writer.saved] == ["live"]


async def test_mock_is_still_written_on_a_day_with_no_live_capture() -> None:
    # The guard is about mixing, not about mock itself — a machine with no
    # broker connected must still accumulate a scrubbable timeline.
    writer = FakeWriter()
    source = FakeSource({"NIFTY": _observation("NIFTY", source="mock")})
    capture = _capture(source, writer, open_=True, allow_mock=True)

    first = await capture()
    source.set("NIFTY", _observation("NIFTY", source="mock", oi=777_777))
    second = await capture()

    assert first.written == ("NIFTY",)
    assert second.written == ("NIFTY",)
    assert [s.source for s in writer.saved] == ["mock", "mock"]


# -- several expiries per tick ------------------------------------------------


async def test_one_expiry_asks_the_provider_to_choose() -> None:
    """The behaviour the archive has always had, kept as the default.

    ``None`` is not "the nearest" - it lets the provider resolve, which is what
    every existing deployment's history was captured under.
    """
    source = FakeSource({"NIFTY": _observation("NIFTY")}, {"NIFTY": ("2026-10-01", "2026-10-08")})
    writer = FakeWriter()

    await _capture(source, writer, open_=True, allow_mock=True)()

    assert len(writer.saved) == 1


async def test_raising_the_setting_archives_a_session_for_each_expiry() -> None:
    """The fix. Without this the series pages have history for the front month
    only, and every other expiry falls back to a two-point open-versus-now."""
    source = FakeSource(
        {"NIFTY": _observation("NIFTY")},
        {"NIFTY": ("2026-10-01", "2026-10-08", "2026-10-15", "2026-10-22")},
    )
    writer = FakeWriter()

    result = await _capture(source, writer, open_=True, allow_mock=True, expiries=3)()

    assert len(writer.saved) == 3
    assert result.written == ("NIFTY@2026-10-01", "NIFTY@2026-10-08", "NIFTY@2026-10-15")


async def test_it_never_asks_for_more_expiries_than_are_listed() -> None:
    source = FakeSource({"NIFTY": _observation("NIFTY")}, {"NIFTY": ("2026-10-01",)})
    writer = FakeWriter()

    await _capture(source, writer, open_=True, allow_mock=True, expiries=6)()

    assert len(writer.saved) == 1


async def test_a_source_that_cannot_list_expiries_still_captures_one() -> None:
    """A provider outage on the expiry list must not stop the archive entirely."""
    source = FakeSource({"NIFTY": _observation("NIFTY")}, {})
    writer = FakeWriter()

    await _capture(source, writer, open_=True, allow_mock=True, expiries=6)()

    assert len(writer.saved) == 1


async def test_one_expiry_failing_does_not_cost_the_others() -> None:
    """Same rule as one symbol not sinking the tick, one level down."""

    class PartlyBroken(FakeSource):
        async def fetch(self, symbol: str, *, expiry: str | None = None):  # type: ignore[no-untyped-def]
            if expiry == "2026-10-08":
                raise RuntimeError("broker hiccup")
            return await super().fetch(symbol, expiry=expiry)

    source = PartlyBroken(
        {"NIFTY": _observation("NIFTY")},
        {"NIFTY": ("2026-10-01", "2026-10-08", "2026-10-15")},
    )
    writer = FakeWriter()

    result = await _capture(source, writer, open_=True, allow_mock=True, expiries=3)()

    assert len(writer.saved) == 2
    assert [label for label, _ in result.failed] == ["NIFTY@2026-10-08"]
