"""The two market-breadth adapters.

One bridges the futures board into a priced index; the other stands in for a
participant file nobody has wired up yet. Both have one property that matters
more than their arithmetic: they must never let generated data look live.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from chartnexus.contexts.futures_analytics.application.ports import BoardSnapshot
from chartnexus.contexts.futures_analytics.domain.buildup import FuturesReading
from chartnexus.contexts.market_breadth.application.ports import (
    IndexConstituentSource,
    InstitutionalFlowSource,
)
from chartnexus.contexts.market_breadth.domain.flows import Segment
from chartnexus.contexts.market_breadth.domain.open_interest import (
    OI_SEGMENTS,
    PARTICIPANT_ORDER,
    FutureLegs,
    OptionLegs,
    segment_imbalance,
)
from chartnexus.infrastructure.breadth.constituent_source import (
    BASIS,
    BoardIndexConstituentSource,
)
from chartnexus.infrastructure.breadth.flow_source import (
    SimulatedInstitutionalFlowSource,
)
from chartnexus.infrastructure.time.clock import FixedClock
from chartnexus.shared_kernel.types.identifiers import TenantId, new_id

pytestmark = pytest.mark.unit

TENANT = TenantId(new_id())


def reading(symbol: str, *, price: str, previous: str = "100") -> FuturesReading:
    return FuturesReading(
        symbol=symbol,
        price=Decimal(price),
        price_open=Decimal(previous),
    )


class FakeBoard:
    def __init__(self, readings: list[FuturesReading], *, source: str = "live") -> None:
        self.snapshot = BoardSnapshot(readings=readings, universe=len(readings), source=source)
        self.calls = 0

    async def read(self, tenant_id: TenantId) -> BoardSnapshot:
        self.calls += 1
        return self.snapshot


# -- the index source ---------------------------------------------------------


def test_it_implements_the_port() -> None:
    assert isinstance(BoardIndexConstituentSource(FakeBoard([])), IndexConstituentSource)


async def test_members_are_priced_against_their_previous_close() -> None:
    board = FakeBoard(
        [reading("RELIANCE", price="110"), reading("NIFTY", price="101", previous="100")]
    )

    snapshot = await BoardIndexConstituentSource(board).read(TENANT, "NIFTY50")

    reliance = next(m for m in snapshot.members if m.symbol == "RELIANCE")
    assert reliance.change_percent == Decimal(10)
    assert reliance.weight_percent > 0
    assert reliance.sector is not None


async def test_the_index_level_comes_from_the_index_s_own_contract() -> None:
    board = FakeBoard([reading("NIFTY", price="24900", previous="24600")])

    snapshot = await BoardIndexConstituentSource(board).read(TENANT, "NIFTY50")

    assert snapshot.level == Decimal(24900)
    assert snapshot.previous_close == Decimal(24600)


async def test_a_board_without_the_index_contract_reports_no_level() -> None:
    """None, not a level reconstructed from the members — the contribution
    maths needs a real baseline and must not invent one."""
    board = FakeBoard([reading("RELIANCE", price="110")])

    snapshot = await BoardIndexConstituentSource(board).read(TENANT, "NIFTY50")

    assert snapshot.level is None
    assert snapshot.change_percent is None


async def test_unpriced_members_shrink_coverage_rather_than_the_universe() -> None:
    board = FakeBoard([reading("RELIANCE", price="110")])

    snapshot = await BoardIndexConstituentSource(board).read(TENANT, "NIFTY50")

    assert len(snapshot.members) == 1
    assert snapshot.universe == 50
    assert snapshot.covered_weight_percent < Decimal(100)


async def test_provenance_travels_from_the_board() -> None:
    board = FakeBoard([reading("RELIANCE", price="110")], source="mock")

    snapshot = await BoardIndexConstituentSource(board).read(TENANT, "NIFTY50")

    assert snapshot.source == "mock"
    # And the page is told which market the prices came from.
    assert snapshot.basis == BASIS == "futures"


async def test_an_unknown_index_returns_an_empty_snapshot_not_a_crash() -> None:
    board = FakeBoard([reading("RELIANCE", price="110")])

    snapshot = await BoardIndexConstituentSource(board).read(TENANT, "MADEUP")

    assert snapshot.members == ()
    assert board.calls == 0


async def test_one_board_read_serves_the_whole_index() -> None:
    """Fifty members, one broker call — the quota does not survive otherwise."""
    board = FakeBoard([reading(symbol, price="110") for symbol in ("RELIANCE", "INFY", "TCS")])

    await BoardIndexConstituentSource(board).read(TENANT, "NIFTY50")

    assert board.calls == 1


def test_the_universe_lists_only_indices_that_can_be_drawn() -> None:
    universe = BoardIndexConstituentSource(FakeBoard([])).universe()

    assert "NIFTY50" in universe
    assert "BANKNIFTY" in universe


# -- the flow source ----------------------------------------------------------


def flows(*, today: date = date(2026, 9, 18)) -> SimulatedInstitutionalFlowSource:
    """The source with a pinned clock, so "the latest session" is knowable.

    Midday UTC is late afternoon IST, which keeps the exchange date and the
    server date on the same day and stops the fixture drifting across the
    05:30 rollover the adapter exists to handle.
    """
    return SimulatedInstitutionalFlowSource(
        FixedClock(datetime(today.year, today.month, today.day, 12, tzinfo=UTC))
    )


def test_the_flow_source_implements_the_port() -> None:
    assert isinstance(flows(), InstitutionalFlowSource)


def test_generated_flow_is_always_labelled_as_generated() -> None:
    """The only thing separating this board from a real one."""
    assert flows().source == "mock"


async def test_it_returns_the_requested_number_of_sessions_oldest_first() -> None:
    days = await flows().read(TENANT, sessions=5)

    assert len(days) == 5
    assert [day.session_date for day in days] == sorted(day.session_date for day in days)


async def test_weekends_are_not_sessions() -> None:
    days = await flows().read(TENANT, sessions=10)

    assert all(day.session_date.weekday() < 5 for day in days)


async def test_the_same_session_always_generates_the_same_figures() -> None:
    """A page must not reshuffle its own history on every poll."""
    first = await flows().read(TENANT, sessions=3)
    second = await flows().read(TENANT, sessions=3)

    assert [day.segment(Segment.CASH).fii.net for day in first] == [  # type: ignore[union-attr]
        day.segment(Segment.CASH).fii.net  # type: ignore[union-attr]
        for day in second
    ]


async def test_until_caps_the_window_at_an_archived_session() -> None:
    days = await flows().read(TENANT, sessions=3, until=date(2026, 9, 10))

    assert days[-1].session_date == date(2026, 9, 10)


async def test_every_segment_is_published_and_only_cash_carries_a_dii_line() -> None:
    day = (await flows().read(TENANT, sessions=1))[0]

    assert {entry.segment for entry in day.segments} == set(Segment)
    cash = day.segment(Segment.CASH)
    assert cash is not None and cash.dii is not None
    for name in (Segment.INDEX_FUTURES, Segment.INDEX_OPTIONS, Segment.STOCK_OPTIONS):
        entry = day.segment(name)
        assert entry is not None and entry.dii is None


async def test_buy_and_sell_reproduce_the_net_a_reader_would_compute() -> None:
    day = (await flows().read(TENANT, sessions=1))[0]

    for entry in day.segments:
        assert entry.fii.buy - entry.fii.sell == entry.fii.net
        assert entry.fii.buy >= 0 and entry.fii.sell >= 0


# -- the open-interest board --------------------------------------------------


async def test_the_board_covers_every_participant_in_every_segment() -> None:
    rows = await flows().read_open_interest(TENANT, date(2026, 9, 21))

    assert len(rows) == len(PARTICIPANT_ORDER) * len(OI_SEGMENTS)
    assert {row.participant for row in rows} == set(PARTICIPANT_ORDER)
    assert {row.segment for row in rows} == set(OI_SEGMENTS)


async def test_cash_is_not_an_open_interest_segment() -> None:
    """Shares bought in the cash market are not a position with an expiry."""
    rows = await flows().read_open_interest(TENANT, date(2026, 9, 21))

    assert Segment.CASH not in {row.segment for row in rows}


async def test_every_segment_s_nets_sum_to_zero() -> None:
    """Every long is somebody's short — the one invariant of this board."""
    rows = await flows().read_open_interest(TENANT, date(2026, 9, 21))

    assert set(segment_imbalance(rows).values()) == {0}


async def test_the_legs_reproduce_the_net_they_sit_behind() -> None:
    rows = await flows().read_open_interest(TENANT, date(2026, 9, 21))

    for row in rows:
        assert row.legs is not None
        assert row.legs.net == row.net, row


async def test_no_leg_is_negative() -> None:
    """A book cannot hold a negative number of contracts."""
    rows = await flows().read_open_interest(TENANT, date(2026, 9, 21))

    for row in rows:
        legs = row.legs
        sides: tuple[int, ...]
        if isinstance(legs, OptionLegs):
            sides = (legs.call_long, legs.call_short, legs.put_long, legs.put_short)
        else:
            assert isinstance(legs, FutureLegs)
            sides = (legs.long, legs.short)
        assert all(side >= 0 for side in sides), row


async def test_yesterday_s_column_matches_yesterday_s_board() -> None:
    """The reason the Change column can be trusted: stepping back a session
    must show exactly the numbers today's change was measured against."""
    source = flows()
    today = await source.read_open_interest(TENANT, date(2026, 9, 22))
    yesterday = await source.read_open_interest(TENANT, date(2026, 9, 21))

    nets = {(row.participant, row.segment): row.net for row in yesterday}
    for row in today:
        assert row.previous_net == nets[(row.participant, row.segment)], row


async def test_positions_drift_rather_than_being_redrawn_each_session() -> None:
    """Open interest is a stock, not a flow.

    An earlier generator drew each session independently and produced books
    that flipped from millions long to millions short overnight — arithmetically
    fine, and nothing anyone would see on a real exchange.
    """
    rows = await flows().read_open_interest(TENANT, date(2026, 9, 22))

    for row in rows:
        level = max(abs(row.net), abs(row.previous_net))
        assert abs(row.change) <= level, row


async def test_neighbours_skip_the_weekend() -> None:
    # 21 Sep 2026 is a Monday, so the session before it is Friday the 18th.
    # The clock is pinned past that Tuesday, or the forward step would
    # correctly refuse to walk into a session that has not happened.
    previous, following = await flows(today=date(2026, 9, 25)).neighbours(TENANT, date(2026, 9, 21))

    assert previous == date(2026, 9, 18)
    assert following == date(2026, 9, 22)


async def test_there_is_no_session_after_the_latest_published_one() -> None:
    """The forward arrow must stop rather than walk into a future the archive
    cannot contain."""
    source = flows(today=date(2026, 9, 22))

    previous, following = await source.neighbours(TENANT, date(2026, 9, 22))

    assert previous == date(2026, 9, 21)
    assert following is None
