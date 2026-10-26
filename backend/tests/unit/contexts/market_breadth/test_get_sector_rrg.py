"""Turning the archive into rotation tails.

The arithmetic is covered in ``test_rrg``; what is tested here is everything
between the archive and it. A grid that staggers two members by a period, a
benchmark counted as one of its own sectors, a latecomer that truncates a
sector's whole history — none of these throw, and each one draws a board that
looks exactly as plausible as a correct one.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from chartnexus.contexts.market_breadth.application.get_sector_rrg import (
    DAILY,
    TUNING,
    GetSectorRrg,
    SectorRrgQuery,
    periods_required,
)
from chartnexus.contexts.market_breadth.application.ports import BreadthScope, SectorBoard
from chartnexus.contexts.market_breadth.domain.breadth import BreadthCount, SectorRow
from chartnexus.contexts.market_breadth.domain.breadth_series import PricePoint
from chartnexus.contexts.market_breadth.domain.constituents import Constituent
from chartnexus.shared_kernel.types.identifiers import TenantId

pytestmark = pytest.mark.unit

TENANT = TenantId("00000000-0000-0000-0000-000000000001")
BENCHMARK = "NIFTY"

#: 09:15 IST, inside the session window the clipper keeps.
OPEN = datetime(2026, 10, 12, 3, 45, tzinfo=UTC)


def member(symbol: str, sector: str) -> Constituent:
    return Constituent(
        symbol=symbol,
        name=symbol,
        last=Decimal(100),
        previous_close=Decimal(100),
        weight_percent=Decimal(0),
        sector=sector,
    )


def sector_row(sector: str, symbols: Sequence[str]) -> SectorRow:
    return SectorRow(
        sector=sector,
        count=BreadthCount(advancing=len(symbols)),
        mean_change_percent=Decimal(0),
        members=len(symbols),
        rows=tuple(member(symbol, sector) for symbol in symbols),
    )


class FakeHistory:
    """An archive of exactly the prices a test asks for."""

    def __init__(self, sessions: Sequence[date], points: Sequence[PricePoint]) -> None:
        self._sessions = list(sessions)
        self._points = list(points)

    async def prices(self, session: date, symbols: Sequence[str]) -> list[PricePoint]:
        wanted = set(symbols)
        return [
            point
            for point in self._points
            if point.symbol in wanted and point.at.astimezone(UTC).date() == session
        ]

    async def baselines(self, session: date, symbols: Sequence[str]) -> dict[str, Decimal]:
        return {}

    async def sessions(self, limit: int) -> list[date]:
        return self._sessions[:limit]


class FakeUniverse:
    def __init__(self, sectors: Sequence[SectorRow], level: str | None = BENCHMARK) -> None:
        self._sectors = list(sectors)
        self._level = level

    async def scope(self, index: str, sector: str | None) -> BreadthScope:
        return BreadthScope(label=index, symbols=(), level_symbol=self._level)

    async def sector_board(self, tenant_id: TenantId) -> SectorBoard:
        return SectorBoard(sectors=self._sectors, source="mock")

    async def live(self, tenant_id: TenantId, symbols: Sequence[str]):  # pragma: no cover
        raise AssertionError("the RRG board reads the archive, never the live board")


#: Fifteen-minute buckets in one session. 09:15 to 15:30 is 375 minutes, and
#: the clipper drops anything outside that — so a fixture that wants sixty
#: periods needs three sessions, not one long day.
BUCKETS_PER_SESSION = 25


def at_period(index: int) -> datetime:
    """Where period ``index`` falls, rolling into the next session as needed."""
    session, bucket = divmod(index, BUCKETS_PER_SESSION)
    return OPEN + timedelta(days=session, minutes=15 * bucket)


def ticks(symbol: str, prices: Sequence[float], *, start: int = 0) -> list[PricePoint]:
    """One price per fifteen-minute bucket, from period ``start`` onward."""
    return [
        PricePoint(symbol=symbol, at=at_period(start + step), price=Decimal(str(price)))
        for step, price in enumerate(prices)
    ]


def build(points: Sequence[PricePoint], sectors: Sequence[SectorRow]) -> GetSectorRrg:
    sessions = sorted({point.at.astimezone(UTC).date() for point in points})
    return GetSectorRrg(history=FakeHistory(sessions, points), universe=FakeUniverse(sectors))


def rising(periods: int, rate: float) -> list[float]:
    """Accelerating, so the series is not momentum-neutral. See test_rrg."""
    return [100.0 + rate * step * step / 50.0 for step in range(periods)]


class TestPeriodsRequired:
    def test_is_derived_from_the_tuning(self) -> None:
        # 2*14 + 2*3 + 4 - 3
        assert periods_required(TUNING["15m"]) == 35

    def test_the_daily_axis_fits_inside_a_thirty_session_archive(self) -> None:
        # The whole reason the daily tuning is shorter: the capture worker
        # prunes at thirty sessions, so a window needing more than that could
        # never draw a point no matter how long the deployment ran.
        assert periods_required(TUNING[DAILY]) <= 30


class TestEmptyBoards:
    @pytest.mark.anyio
    async def test_an_empty_archive_says_so_rather_than_throwing(self) -> None:
        board = await build([], [sector_row("IT", ["A"])])(
            SectorRrgQuery(tenant_id=TENANT, index="NIFTY50")
        )
        assert board.tails == []
        assert board.periods == 0

    @pytest.mark.anyio
    async def test_a_benchmark_with_no_contract_draws_nothing(self) -> None:
        # Without a level symbol there is nothing to be relative *to*.
        use_case = GetSectorRrg(
            history=FakeHistory([date(2026, 10, 12)], ticks("A", rising(60, 1.0))),
            universe=FakeUniverse([sector_row("IT", ["A"])], level=None),
        )
        board = await use_case(SectorRrgQuery(tenant_id=TENANT, index="NIFTY50"))
        assert board.tails == []

    @pytest.mark.anyio
    async def test_a_shallow_grid_reports_what_it_needed(self) -> None:
        # The page distinguishes "not enough history yet" from "nothing priced",
        # so the counts have to come back even when no tail does.
        points = [*ticks(BENCHMARK, [100.0] * 10), *ticks("A", [100.0] * 10)]
        board = await build(points, [sector_row("IT", ["A"])])(
            SectorRrgQuery(tenant_id=TENANT, index="NIFTY50")
        )
        assert board.tails == []
        assert board.periods == 10
        assert board.periods_required == 35


class TestTails:
    @pytest.mark.anyio
    async def test_a_strengthening_sector_leads(self) -> None:
        periods = 60
        points = [
            *ticks(BENCHMARK, [100.0] * periods),
            *ticks("A", rising(periods, 1.0)),
            *ticks("B", rising(periods, 1.0)),
        ]
        board = await build(points, [sector_row("IT", ["A", "B"])])(
            SectorRrgQuery(tenant_id=TENANT, index="NIFTY50")
        )

        assert len(board.tails) == 1
        tail = board.tails[0]
        assert tail.sector == "IT"
        assert tail.measured == 2
        assert tail.head is not None
        assert tail.head.rs_ratio > 100.0

    @pytest.mark.anyio
    async def test_the_benchmark_is_never_one_of_the_sectors(self) -> None:
        # NIFTY is not one of the fifty stocks in NIFTY. If it leaked into a
        # sector's composite that sector would be measured partly against
        # itself and sit permanently near the cross.
        periods = 60
        points = [
            *ticks(BENCHMARK, [100.0] * periods),
            *ticks("A", rising(periods, 1.0)),
        ]
        board = await build(points, [sector_row("IT", ["A"])])(
            SectorRrgQuery(tenant_id=TENANT, index="NIFTY50")
        )
        assert [tail.sector for tail in board.tails] == ["IT"]
        assert board.tails[0].members == 1

    @pytest.mark.anyio
    async def test_the_tail_length_is_honoured(self) -> None:
        periods = 80
        points = [
            *ticks(BENCHMARK, [100.0] * periods),
            *ticks("A", rising(periods, 1.0)),
        ]
        board = await build(points, [sector_row("IT", ["A"])])(
            SectorRrgQuery(tenant_id=TENANT, index="NIFTY50", tail=4)
        )
        assert len(board.tails[0].points) == 4

    @pytest.mark.anyio
    async def test_a_sector_nothing_priced_in_is_dropped_not_blank(self) -> None:
        periods = 60
        points = [
            *ticks(BENCHMARK, [100.0] * periods),
            *ticks("A", rising(periods, 1.0)),
        ]
        board = await build(points, [sector_row("IT", ["A"]), sector_row("PHARMA", ["GHOST"])])(
            SectorRrgQuery(tenant_id=TENANT, index="NIFTY50")
        )
        assert [tail.sector for tail in board.tails] == ["IT"]


class TestAlignment:
    """The bugs that draw a perfectly plausible wrong board."""

    @pytest.mark.anyio
    async def test_a_quiet_bucket_carries_the_last_price_forward(self) -> None:
        periods = 60
        gappy = ticks("A", rising(periods, 1.0))
        # Drop every third print: the symbol went quiet, it did not de-list.
        gappy = [point for index, point in enumerate(gappy) if index % 3]
        points = [*ticks(BENCHMARK, [100.0] * periods), *gappy]

        board = await build(points, [sector_row("IT", ["A"])])(
            SectorRrgQuery(tenant_id=TENANT, index="NIFTY50")
        )
        assert board.tails, "a symbol with gaps should still plot"
        assert board.periods == periods

    @pytest.mark.anyio
    async def test_a_latecomer_is_dropped_rather_than_truncating_the_sector(self) -> None:
        # The member joins with 20% coverage, below the floor. Keeping it would
        # cut the other member's history back to the latecomer's first print
        # and leave too few periods for any tail at all.
        periods = 60
        points = [
            *ticks(BENCHMARK, [100.0] * periods),
            *ticks("A", rising(periods, 1.0)),
            *ticks("LATE", [100.0] * 12, start=periods - 12),
        ]
        board = await build(points, [sector_row("IT", ["A", "LATE"])])(
            SectorRrgQuery(tenant_id=TENANT, index="NIFTY50")
        )

        assert board.tails, "the sector should survive its latecomer"
        assert board.tails[0].measured == 1
        assert board.tails[0].members == 2

    @pytest.mark.anyio
    async def test_members_are_aligned_on_the_period_not_the_list_index(self) -> None:
        # Both members rise identically; one simply starts printing later but
        # still covers enough of the grid to be kept. Aligned correctly the
        # composite is a clean rise and the sector leads. Aligned by list index
        # — trimming to the shortest — the late member's early prices would be
        # plotted against the early member's late ones, and the composite would
        # wobble rather than trend.
        periods = 60
        shape = rising(periods, 1.0)
        points = [
            *ticks(BENCHMARK, [100.0] * periods),
            *ticks("EARLY", shape),
            *ticks("LATEISH", shape[10:], start=10),
        ]
        board = await build(points, [sector_row("IT", ["EARLY", "LATEISH"])])(
            SectorRrgQuery(tenant_id=TENANT, index="NIFTY50")
        )

        assert board.tails
        tail = board.tails[0]
        assert tail.measured == 2
        assert tail.head is not None
        # Both members are rising against a flat benchmark, so whatever the
        # start offsets, the sector must read as strong.
        assert tail.head.rs_ratio > 100.0

    @pytest.mark.anyio
    async def test_points_carry_stamps_from_the_grid(self) -> None:
        periods = 60
        points = [
            *ticks(BENCHMARK, [100.0] * periods),
            *ticks("A", rising(periods, 1.0)),
        ]
        board = await build(points, [sector_row("IT", ["A"])])(
            SectorRrgQuery(tenant_id=TENANT, index="NIFTY50")
        )
        stamps = [point.at for point in board.tails[0].points]
        assert stamps == sorted(stamps)
        assert all(stamp.tzinfo is not None for stamp in stamps)
