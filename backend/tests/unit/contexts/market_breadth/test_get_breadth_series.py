"""Which tier a breadth series is, and what a sector scope is missing.

The tiers are the whole point of this use case. A page that cannot tell a
captured session from two points joined by a straight line will draw the second
one with the confidence of the first, and the reader has no way to know.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from marketcompass.contexts.market_breadth.application.get_breadth_series import (
    BreadthSeriesQuery,
    GetBreadthSeries,
    GetSectorRail,
)
from marketcompass.contexts.market_breadth.application.ports import (
    BreadthScope,
    LiveReading,
    SectorBoard,
)
from marketcompass.contexts.market_breadth.domain.breadth import (
    BreadthCount,
    SectorRow,
    sector_board,
)
from marketcompass.contexts.market_breadth.domain.breadth_series import (
    PricePoint,
    SeriesQuality,
)
from marketcompass.contexts.market_breadth.domain.constituents import Constituent
from marketcompass.shared_kernel.types.identifiers import TenantId, new_id

pytestmark = pytest.mark.unit

TENANT = TenantId(new_id())
SESSION = date(2026, 9, 22)
OPEN = datetime(2026, 9, 22, 3, 50, tzinfo=UTC)  # 09:20 IST
NOW = datetime(2026, 9, 22, 6, 0, tzinfo=UTC)  # 11:30 IST

INDEX_SCOPE = BreadthScope(
    label="NIFTY 50",
    symbols=("A", "B", "NIFTY"),
    weights={"A": Decimal(30), "B": Decimal(20)},
    level_symbol="NIFTY",
)
SECTOR_SCOPE = BreadthScope(label="IT", symbols=("A", "B"))


class FakeHistory:
    def __init__(
        self,
        prices: list[PricePoint] | None = None,
        baselines: dict[str, Decimal] | None = None,
        sessions: list[date] | None = None,
    ) -> None:
        self._prices = prices or []
        self._baselines = baselines or {}
        self._sessions = sessions or []

    async def prices(self, session: date, symbols: object) -> list[PricePoint]:
        return list(self._prices)

    async def baselines(self, session: date, symbols: object) -> dict[str, Decimal]:
        return dict(self._baselines)

    async def sessions(self, limit: int) -> list[date]:
        return list(self._sessions)


class FakeUniverse:
    def __init__(
        self,
        scope: BreadthScope = INDEX_SCOPE,
        live: LiveReading | None = None,
        board: SectorBoard | None = None,
    ) -> None:
        self._scope = scope
        self._live = live or LiveReading(at=NOW)
        self._board = board or SectorBoard()

    async def scope(self, index: str, sector: str | None) -> BreadthScope:
        return self._scope

    async def sector_board(self, tenant_id: TenantId) -> SectorBoard:
        return self._board

    async def live(self, tenant_id: TenantId, symbols: object) -> LiveReading:
        return self._live


def tick(symbol: str, minute: int, price: str) -> PricePoint:
    return PricePoint(symbol=symbol, at=OPEN + timedelta(minutes=minute), price=Decimal(price))


def build(history: FakeHistory, universe: FakeUniverse) -> GetBreadthSeries:
    return GetBreadthSeries(history=history, universe=universe, now_utc=lambda: NOW)


# -- the captured session ------------------------------------------------------


@pytest.mark.asyncio
async def test_a_captured_session_is_the_intraday_tier() -> None:
    history = FakeHistory(
        prices=[tick("A", 0, "101"), tick("B", 0, "99"), tick("A", 1, "102")],
        baselines={"A": Decimal(100), "B": Decimal(100), "NIFTY": Decimal(23400)},
    )
    series = await build(history, FakeUniverse())(
        BreadthSeriesQuery(tenant_id=TENANT, index="NIFTY50", session=SESSION)
    )

    assert series.quality is SeriesQuality.INTRADAY
    assert len(series.points) == 2
    assert series.baseline == "archived_close"


@pytest.mark.asyncio
async def test_the_benchmark_is_not_counted_among_its_own_members() -> None:
    """`universe` is the members, and NIFTY is not one of the fifty."""
    history = FakeHistory(
        prices=[
            tick("A", 0, "101"),
            tick("NIFTY", 0, "23450"),
            tick("A", 1, "102"),
        ],
        baselines={"A": Decimal(100), "B": Decimal(100), "NIFTY": Decimal(23400)},
    )
    series = await build(history, FakeUniverse())(
        BreadthSeriesQuery(tenant_id=TENANT, index="NIFTY50", session=SESSION)
    )

    assert series.universe == 2  # A and B; NIFTY rode along for its level only
    assert series.measured == 2


@pytest.mark.asyncio
async def test_a_sector_has_no_weights_and_no_level() -> None:
    """Both absences are real and the page has to be able to say so."""
    history = FakeHistory(
        prices=[tick("A", 0, "101"), tick("B", 0, "99"), tick("A", 1, "102")],
        baselines={"A": Decimal(100), "B": Decimal(100)},
    )
    series = await build(history, FakeUniverse(scope=SECTOR_SCOPE))(
        BreadthSeriesQuery(tenant_id=TENANT, index="NIFTY50", sector="IT", session=SESSION)
    )

    assert series.label == "IT"
    assert series.weighted_available is False
    assert all(point.level is None for point in series.points)


# -- the fallbacks -------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_archived_day_with_nothing_captured_is_empty_not_today() -> None:
    """Drawing today's board under an old date would be the worst answer."""
    series = await build(FakeHistory(), FakeUniverse())(
        BreadthSeriesQuery(tenant_id=TENANT, index="NIFTY50", session=SESSION)
    )

    assert series.quality is SeriesQuality.EMPTY
    assert series.points == []


@pytest.mark.asyncio
async def test_a_live_day_with_nothing_captured_falls_back_to_two_points() -> None:
    """The open and now — a join, not a shape, and labelled as such."""
    live = LiveReading(
        at=NOW,
        prices=[PricePoint(symbol="A", at=NOW, price=Decimal(104))],
        baselines={"A": Decimal(100), "B": Decimal(100)},
        source="live",
    )
    series = await build(FakeHistory(), FakeUniverse(live=live))(
        BreadthSeriesQuery(tenant_id=TENANT, index="NIFTY50")
    )

    assert series.quality is SeriesQuality.LIVE_PROXY
    assert len(series.points) == 2
    # The broker's own previous close, not the archive's derived one.
    assert series.baseline == "previous_close"
    assert series.points[0].advancing == 0  # everything opens flat, by construction
    assert series.points[-1].advancing == 1


@pytest.mark.asyncio
async def test_a_live_day_the_board_cannot_price_is_empty() -> None:
    series = await build(FakeHistory(), FakeUniverse())(
        BreadthSeriesQuery(tenant_id=TENANT, index="NIFTY50")
    )
    assert series.quality is SeriesQuality.EMPTY


@pytest.mark.asyncio
async def test_a_scope_with_no_contracts_draws_nothing() -> None:
    empty = BreadthScope(label="TEXTILES", symbols=())
    series = await build(FakeHistory(), FakeUniverse(scope=empty))(
        BreadthSeriesQuery(tenant_id=TENANT, index="NIFTY50", sector="TEXTILES")
    )
    assert series.quality is SeriesQuality.EMPTY


# -- the rail ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_rail_offers_only_sessions_the_archive_holds() -> None:
    """A day nobody captured is a day this page cannot draw."""
    history = FakeHistory(sessions=[date(2026, 9, 22), date(2026, 9, 21)])
    board = SectorBoard(
        sectors=[
            SectorRow(
                sector="IT", count=_count(3, 1), mean_change_percent=Decimal("1.2"), members=4
            )
        ],
        source="live",
    )
    rail = await GetSectorRail(
        universe=FakeUniverse(board=board), history=history, indices=("NIFTY50",)
    )(TENANT)

    assert rail.sessions == [date(2026, 9, 22), date(2026, 9, 21)]
    assert [row.sector for row in rail.sectors] == ["IT"]
    assert rail.indices == ("NIFTY50",)


def test_a_sector_of_the_fo_universe_averages_unweighted() -> None:
    """These names carry no index weight, so a weighted mean has no denominator."""
    members = [
        Constituent(
            symbol="A",
            name=None,
            last=Decimal(110),
            previous_close=Decimal(100),
            weight_percent=Decimal(0),
            sector="IT",
        ),
        Constituent(
            symbol="B",
            name=None,
            last=Decimal(90),
            previous_close=Decimal(100),
            weight_percent=Decimal(0),
            sector="IT",
        ),
    ]
    rows = sector_board(members)

    assert len(rows) == 1
    assert rows[0].mean_change_percent == Decimal(0)  # +10 and -10
    assert (rows[0].count.advancing, rows[0].count.declining) == (1, 1)


def _count(advancing: int, declining: int) -> BreadthCount:
    return BreadthCount(advancing=advancing, declining=declining)
