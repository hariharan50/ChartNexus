"""The intraday Price-vs-OI series behind Future Lab → Price vs OI.

The series is the page's whole subject, so what these cover is mostly the
question "what are these numbers worth": a captured session, a two-point proxy
when nothing is archived, and nothing at all — never one of them wearing
another's label.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from chartnexus.contexts.futures_analytics.application.get_price_oi_series import (
    GetFuturesPriceOiSeries,
    PriceOiSeriesQuery,
)
from chartnexus.contexts.futures_analytics.application.ports import (
    BoardFrame,
    BoardSnapshot,
)
from chartnexus.contexts.futures_analytics.domain.buildup import FuturesReading
from chartnexus.shared_kernel.types.identifiers import TenantId, new_id

pytestmark = pytest.mark.unit

TENANT = TenantId(new_id())
SESSION = date(2026, 9, 21)
# 14:00 IST on the session date — comfortably mid-session.
NOW = datetime(2026, 9, 21, 8, 30, tzinfo=UTC)
_IST = timezone(timedelta(hours=5, minutes=30))


def frame(
    minutes: int,
    *,
    price: str = "1200",
    oi: int | None = 100_000,
    source: str = "live",
) -> BoardFrame:
    return BoardFrame(
        symbol="RELIANCE",
        session_date=SESSION,
        captured_at=datetime(2026, 9, 21, 4, 0, tzinfo=UTC) + timedelta(minutes=minutes),
        price=Decimal(price),
        open_interest=oi,
        volume=5_000,
        expiry="2026-09-29",
        source=source,
    )


class FakeHistory:
    def __init__(self, frames: list[BoardFrame]) -> None:
        self.frames = frames
        self.asked: list[tuple[str, date]] = []

    async def frames_for(self, symbol: str, session_date: date) -> list[BoardFrame]:
        self.asked.append((symbol, session_date))
        return list(self.frames)


class FakeBoard:
    def __init__(self, snapshot: BoardSnapshot | None = None) -> None:
        self.snapshot = snapshot or BoardSnapshot()
        self.reads = 0

    async def read(self, tenant_id: TenantId) -> BoardSnapshot:
        self.reads += 1
        return self.snapshot


def reading(*, price: str = "1250", price_open: str = "1200", oi: int = 110_000) -> FuturesReading:
    return FuturesReading(
        symbol="RELIANCE",
        price=Decimal(price),
        price_open=Decimal(price_open),
        open_interest=oi,
        open_interest_open=100_000,
        expiry="2026-09-29",
        volume=5_000,
    )


def service(history: FakeHistory, board: FakeBoard) -> GetFuturesPriceOiSeries:
    return GetFuturesPriceOiSeries(history=history, board=board, now_utc=lambda: NOW)


def query(**kwargs: object) -> PriceOiSeriesQuery:
    return PriceOiSeriesQuery(tenant_id=TENANT, symbol="RELIANCE", **kwargs)  # type: ignore[arg-type]


# -- the captured session ----------------------------------------------------


async def test_a_stored_session_is_served_as_captured() -> None:
    history = FakeHistory([frame(0), frame(1, price="1201"), frame(2, price="1202")])

    result = await service(history, FakeBoard())(query())

    assert result["data_quality"] == "intraday"
    assert result["price"] == [1200.0, 1201.0, 1202.0]
    assert result["open_is_estimated"] is False
    assert result["expiry_date"] == "2026-09-29"


async def test_a_captured_session_never_reads_the_live_board() -> None:
    """The archive is the answer. Reaching for the board as well would put a
    point on the chart that no capture ever recorded."""
    board = FakeBoard()

    await service(FakeHistory([frame(0), frame(1)]), board)(query())

    assert board.reads == 0


async def test_open_interest_gaps_survive_as_nulls() -> None:
    """A frame captured between open-interest sweeps genuinely has none.

    Zero would draw a cliff to the axis and back; null leaves the gap the data
    actually has.
    """
    history = FakeHistory([frame(0), frame(1, oi=None), frame(2)])

    result = await service(history, FakeBoard())(query())

    assert result["oi"] == [100_000, None, 100_000]


async def test_frames_after_now_are_clipped_on_the_live_day() -> None:
    # 04:00 UTC + 300 minutes is 09:00 UTC — still inside the session, but past
    # the pinned "now" of 08:30, so only the clock rules it out.
    history = FakeHistory([frame(0), frame(1), frame(300)])

    result = await service(history, FakeBoard())(query())

    assert len(result["t"]) == 2


async def test_a_past_session_is_served_whole() -> None:
    """Historical replays a finished day, so nothing is in its future."""
    history = FakeHistory([frame(0), frame(1), frame(300)])

    result = await service(history, FakeBoard())(query(trade_date=date(2026, 9, 18)))

    assert len(result["t"]) == 3
    assert history.asked == [("RELIANCE", date(2026, 9, 18))]


async def test_frames_captured_after_the_bell_are_dropped() -> None:
    """The broker answers all evening with the last traded price.

    A worker that kept capturing would archive hours of flat frames no trading
    produced, and the chart would trail off in a straight line towards
    midnight. 04:00 UTC + 630 minutes is 20:10 IST — long past the close.
    """
    history = FakeHistory([frame(0), frame(1), frame(630)])

    result = await service(history, FakeBoard())(query(trade_date=date(2026, 9, 18)))

    assert len(result["t"]) == 2


async def test_frames_captured_before_the_bell_are_dropped() -> None:
    """04:00 UTC is 09:30 IST; sixty minutes earlier is 08:30, pre-open."""
    history = FakeHistory([frame(-60), frame(0), frame(1)])

    result = await service(history, FakeBoard())(query(trade_date=date(2026, 9, 18)))

    assert len(result["t"]) == 2


async def test_the_proxys_now_point_never_lands_after_the_close() -> None:
    """Opening the page at 8pm must not stretch the axis four hours past the
    bell with a reading nobody traded at."""
    evening = datetime(2026, 9, 21, 14, 30, tzinfo=UTC)  # 20:00 IST
    board = FakeBoard(BoardSnapshot(readings=[reading()], source="live"))
    run = GetFuturesPriceOiSeries(history=FakeHistory([]), board=board, now_utc=lambda: evening)

    result = await run(query())

    last = datetime.fromisoformat(result["t"][-1].replace("Z", "+00:00")).astimezone(_IST)
    assert (last.hour, last.minute) == (15, 30)


# -- downsampling ------------------------------------------------------------


async def test_a_bucket_reports_its_last_frame_not_its_average() -> None:
    """Every other number on the page is a last-traded price. A bucket that
    reported its mean would disagree with the board beside it."""
    history = FakeHistory([frame(0, price="1200"), frame(1, price="1210"), frame(2, price="1220")])

    result = await service(history, FakeBoard())(query(interval="5m"))

    assert result["price"] == [1220.0]
    assert result["interval"] == "5m"


async def test_an_unknown_interval_falls_back_rather_than_failing() -> None:
    result = await service(FakeHistory([frame(0), frame(1)]), FakeBoard())(
        query(interval="3 fortnights")
    )

    assert result["interval"] == "1m"


# -- the proxy ---------------------------------------------------------------


async def test_a_day_with_nothing_archived_falls_back_to_previous_close_vs_now() -> None:
    board = FakeBoard(BoardSnapshot(readings=[reading()], source="live"))

    result = await service(FakeHistory([]), board)(query())

    assert result["data_quality"] == "live_proxy"
    # Two honest points, flagged, rather than a line nobody captured.
    assert result["price"] == [1200.0, 1250.0]
    assert result["oi"] == [100_000, 110_000]
    assert result["open_is_estimated"] is True


async def test_one_stored_frame_is_not_yet_a_session() -> None:
    """Two points drawn as a line would imply a shape one capture cannot support."""
    board = FakeBoard(BoardSnapshot(readings=[reading()], source="live"))

    result = await service(FakeHistory([frame(0)]), board)(query())

    assert result["data_quality"] == "live_proxy"


async def test_the_proxy_reports_the_boards_own_provenance() -> None:
    """A proxy drawn from a generated board must say so, not inherit 'live'."""
    board = FakeBoard(BoardSnapshot(readings=[reading()], source="mock"))

    result = await service(FakeHistory([]), board)(query())

    assert result["source"] == "mock"


# -- nothing to draw ---------------------------------------------------------


async def test_a_contract_the_board_cannot_price_is_empty_not_zero() -> None:
    result = await service(FakeHistory([]), FakeBoard())(query())

    assert result["data_quality"] == "empty"
    assert result["t"] == []
    assert result["price"] == []


async def test_a_past_day_with_no_archive_never_reaches_for_the_live_board() -> None:
    """There is no live equivalent of a finished session. Substituting today's
    board would date-stamp the present as the past."""
    board = FakeBoard(BoardSnapshot(readings=[reading()], source="live"))

    result = await service(FakeHistory([]), board)(query(trade_date=date(2026, 9, 18)))

    assert result["data_quality"] == "empty"
    assert board.reads == 0


async def test_an_empty_payload_is_still_well_formed() -> None:
    """The client parses one shape. An empty day must not be a different one."""
    result = await service(FakeHistory([]), FakeBoard())(query())

    for field in ("instrument_id", "open_ts", "now_ts", "data_quality", "interval", "source"):
        assert result[field] is not None
    assert result["t"] == result["price"] == result["oi"] == []
