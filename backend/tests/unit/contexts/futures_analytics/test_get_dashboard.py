"""The dashboard read — one board fetch, sliced six ways."""

from __future__ import annotations

from decimal import Decimal

import pytest

from marketcompass.contexts.futures_analytics.application.get_dashboard import (
    MAX_PANEL_LIMIT,
    FuturesDashboardQuery,
    GetFuturesDashboard,
)
from marketcompass.contexts.futures_analytics.application.ports import BoardSnapshot
from marketcompass.contexts.futures_analytics.domain.buildup import (
    BuildupState,
    FuturesReading,
)
from marketcompass.shared_kernel.types.identifiers import TenantId, new_id

pytestmark = pytest.mark.unit

TENANT = TenantId(new_id())


def reading(
    symbol: str,
    *,
    price: str = "110",
    oi: int = 1100,
    sector: str | None = None,
    kind: str | None = None,
    expiry: str | None = None,
) -> FuturesReading:
    return FuturesReading(
        symbol=symbol,
        price=Decimal(price),
        price_open=Decimal(100),
        open_interest=oi,
        open_interest_open=1000,
        sector=sector,
        kind=kind,
        expiry=expiry,
    )


class FakeSource:
    def __init__(
        self,
        readings: list[FuturesReading],
        *,
        universe: int | None = None,
        expiry: str | None = None,
    ) -> None:
        self.snapshot = BoardSnapshot(
            readings=readings,
            universe=universe if universe is not None else len(readings),
            expiry=expiry,
        )
        self.calls = 0

    async def read(self, tenant_id: TenantId) -> BoardSnapshot:
        self.calls += 1
        return self.snapshot


async def test_the_board_is_fetched_once_for_all_six_panels() -> None:
    """Panels are views of one read.

    Fetching per panel would let a contract top the gainers card while being
    absent from the build-up card beside it, drawn from a board a second older.
    """
    source = FakeSource([reading("A"), reading("B", price="90")])

    await GetFuturesDashboard(source=source)(FuturesDashboardQuery(tenant_id=TENANT))

    assert source.calls == 1


async def test_panels_are_populated_from_the_same_rows() -> None:
    source = FakeSource(
        [
            reading("LONGS", price="110", oi=1100),
            reading("SHORTS", price="90", oi=1100),
            reading("COVERING", price="110", oi=900),
            reading("UNWINDING", price="90", oi=900),
        ]
    )

    dash = await GetFuturesDashboard(source=source)(FuturesDashboardQuery(tenant_id=TENANT))

    assert [r.symbol for r in dash.long_buildup] == ["LONGS"]
    assert [r.symbol for r in dash.short_buildup] == ["SHORTS"]
    assert [r.symbol for r in dash.short_covering] == ["COVERING"]
    assert [r.symbol for r in dash.long_unwinding] == ["UNWINDING"]
    assert dash.covered == 4


async def test_coverage_and_universe_are_reported_separately() -> None:
    """A board of 2 out of 219 is a weaker claim than one of 219, and says so."""
    source = FakeSource([reading("A"), reading("B")], universe=219)

    dash = await GetFuturesDashboard(source=source)(FuturesDashboardQuery(tenant_id=TENANT))

    assert (dash.covered, dash.universe) == (2, 219)


async def test_a_sector_filter_narrows_the_whole_board() -> None:
    source = FakeSource(
        [
            reading("BANK1", sector="Financials"),
            reading("BANK2", sector="financials"),  # casing must not matter
            reading("PHARMA", sector="Healthcare"),
        ]
    )

    dash = await GetFuturesDashboard(source=source)(
        FuturesDashboardQuery(tenant_id=TENANT, sector="FINANCIALS")
    )

    assert {row.symbol for row in dash.rows} == {"BANK1", "BANK2"}
    assert dash.covered == 2


async def test_the_panel_limit_is_capped() -> None:
    source = FakeSource([reading(f"S{n}", price=str(101 + n)) for n in range(MAX_PANEL_LIMIT + 20)])

    dash = await GetFuturesDashboard(source=source)(
        FuturesDashboardQuery(tenant_id=TENANT, limit=10_000)
    )

    assert len(dash.top_gainers) == MAX_PANEL_LIMIT


async def test_an_empty_board_yields_empty_panels_rather_than_failing() -> None:
    """A broker outage should render an empty dashboard, not a 500."""
    dash = await GetFuturesDashboard(source=FakeSource([]))(FuturesDashboardQuery(tenant_id=TENANT))

    assert dash.rows == []
    assert dash.top_gainers == []
    assert dash.covered == 0


async def test_a_wider_deadband_moves_quiet_contracts_out_of_the_buckets() -> None:
    source = FakeSource([reading("QUIET", price="100.5", oi=1005)])

    strict = await GetFuturesDashboard(source=source)(
        FuturesDashboardQuery(tenant_id=TENANT, deadband_percent=Decimal(1))
    )

    assert strict.long_buildup == []
    assert strict.rows[0].state is BuildupState.NEUTRAL


async def test_the_board_can_be_narrowed_to_stocks() -> None:
    """The Stocks page wants the 210 single names without the index contracts,
    and should not have to join against the catalog to work out which is which."""
    source = FakeSource(
        [
            reading("NIFTY", kind="index"),
            reading("RELIANCE", kind="stock"),
            reading("TCS", kind="stock"),
        ]
    )

    dash = await GetFuturesDashboard(source=source)(
        FuturesDashboardQuery(tenant_id=TENANT, kind="stock")
    )

    assert {row.symbol for row in dash.rows} == {"RELIANCE", "TCS"}
    # The universe is still the whole catalog: the filter narrows what is
    # shown, not what was read.
    assert dash.universe == 3
    assert dash.covered == 2


async def test_the_kind_filter_composes_with_the_sector_filter() -> None:
    source = FakeSource(
        [
            reading("NIFTY", kind="index", sector="Financials"),
            reading("HDFCBANK", kind="stock", sector="Financials"),
            reading("CIPLA", kind="stock", sector="Healthcare"),
        ]
    )

    dash = await GetFuturesDashboard(source=source)(
        FuturesDashboardQuery(tenant_id=TENANT, kind="stock", sector="financials")
    )

    assert [row.symbol for row in dash.rows] == ["HDFCBANK"]


async def test_kind_is_carried_onto_the_row() -> None:
    source = FakeSource([reading("RELIANCE", kind="stock")])

    dash = await GetFuturesDashboard(source=source)(FuturesDashboardQuery(tenant_id=TENANT))

    assert dash.rows[0].kind == "stock"


async def test_the_expiry_describes_the_rows_that_survived_the_filter() -> None:
    """NSE and BSE do not settle on the same day.

    September 2026 is 29 Sep on NSE and 24 Sep on BSE. Reading one date off the
    whole universe let the three BSE index contracts label every NSE stock with
    the wrong expiry, which is what the heatmap's chip was showing.
    """
    source = FakeSource(
        [
            reading("RELIANCE", kind="stock", expiry="2026-09-29"),
            reading("TCS", kind="stock", expiry="2026-09-29"),
            reading("SENSEX", kind="index", expiry="2026-09-24"),
        ],
        # A board-wide guess, taken from whichever contract happened to be first.
        expiry="2026-09-24",
    )
    dashboard = GetFuturesDashboard(source=source)

    stocks = await dashboard(FuturesDashboardQuery(tenant_id=TENANT, kind="stock"))
    indices = await dashboard(FuturesDashboardQuery(tenant_id=TENANT, kind="index"))

    assert stocks.expiry == "2026-09-29"
    assert indices.expiry == "2026-09-24"


async def test_the_majority_expiry_wins_over_a_stray_contract() -> None:
    """One contract on an odd date does not relabel the board."""
    source = FakeSource(
        [
            reading("A", expiry="2026-09-29"),
            reading("B", expiry="2026-09-29"),
            reading("C", expiry="2026-10-27"),
        ]
    )

    dashboard = await GetFuturesDashboard(source=source)(FuturesDashboardQuery(tenant_id=TENANT))

    assert dashboard.expiry == "2026-09-29"


async def test_the_snapshot_expiry_stands_in_when_no_reading_carries_one() -> None:
    source = FakeSource([reading("A"), reading("B")], expiry="2026-09-29")

    dashboard = await GetFuturesDashboard(source=source)(FuturesDashboardQuery(tenant_id=TENANT))

    assert dashboard.expiry == "2026-09-29"
