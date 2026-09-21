"""Wire shapes for the futures dashboard."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from marketcompass.contexts.futures_analytics.application.get_dashboard import FuturesDashboard
from marketcompass.contexts.futures_analytics.domain.buildup import BuildupRow


class FuturesRowResponse(BaseModel):
    """One contract on the board."""

    symbol: str
    name: str | None = None
    price: Decimal
    #: Null when the contract had no prior close to measure against. Clients
    #: must render that as "no data", never as 0.00%.
    price_change_percent: Decimal | None = None
    #: Null when the feed does not carry open interest for this contract.
    open_interest: int | None = None
    oi_change_percent: Decimal | None = None
    state: str = Field(description="long_buildup | short_buildup | short_covering | long_unwinding | neutral")
    kind: str | None = Field(default=None, description="index | stock")
    lot_size: int | None = None
    volume: int | None = None
    #: Null whenever yesterday's volume is unknown, which is the normal case on
    #: live data. Clients must render it as "no data", never as 0.00%.
    volume_change_percent: Decimal | None = None
    #: "O=L", "O=H", or null when the day's prints do not answer the question.
    open_marker: str | None = None
    sector: str | None = None

    @classmethod
    def of(cls, row: BuildupRow) -> FuturesRowResponse:
        return cls(
            symbol=row.symbol,
            name=row.name,
            price=row.price,
            price_change_percent=row.price_change_percent,
            open_interest=row.open_interest,
            oi_change_percent=row.oi_change_percent,
            state=row.state.value,
            kind=row.kind,
            volume_change_percent=row.volume_change_percent,
            open_marker=row.open_marker,
            lot_size=row.lot_size,
            volume=row.volume,
            sector=row.sector,
        )


class FuturesDashboardResponse(BaseModel):
    """The six panels, plus how much of the universe they are drawn from."""

    top_gainers: list[FuturesRowResponse]
    top_losers: list[FuturesRowResponse]
    long_buildup: list[FuturesRowResponse]
    short_buildup: list[FuturesRowResponse]
    short_covering: list[FuturesRowResponse]
    long_unwinding: list[FuturesRowResponse]
    #: Contracts that produced a usable reading, and the size of the catalogued
    #: universe. A board covering 40 of 219 is a weaker claim than one covering
    #: all of them, and the client is entitled to say so.
    covered: int
    universe: int
    source: str = Field(default="mock", description="live | mock")
    expiry: str | None = Field(
        default=None, description="ISO date of the front-month contract."
    )

    @classmethod
    def of(cls, dashboard: FuturesDashboard) -> FuturesDashboardResponse:
        convert = FuturesRowResponse.of
        return cls(
            top_gainers=[convert(row) for row in dashboard.top_gainers],
            top_losers=[convert(row) for row in dashboard.top_losers],
            long_buildup=[convert(row) for row in dashboard.long_buildup],
            short_buildup=[convert(row) for row in dashboard.short_buildup],
            short_covering=[convert(row) for row in dashboard.short_covering],
            long_unwinding=[convert(row) for row in dashboard.long_unwinding],
            covered=dashboard.covered,
            universe=dashboard.universe,
            source=dashboard.source,
            expiry=dashboard.expiry,
        )


class FuturesBoardResponse(BaseModel):
    """Every classified contract, for the table view and the movers page."""

    rows: list[FuturesRowResponse]
    covered: int
    universe: int
    source: str = Field(default="mock", description="live | mock")
    expiry: str | None = Field(
        default=None, description="ISO date of the front-month contract."
    )

    @classmethod
    def of(cls, dashboard: FuturesDashboard) -> FuturesBoardResponse:
        return cls(
            rows=[FuturesRowResponse.of(row) for row in dashboard.rows],
            covered=dashboard.covered,
            universe=dashboard.universe,
            source=dashboard.source,
            expiry=dashboard.expiry,
        )


class PriceOiSeriesResponse(BaseModel):
    """One contract's intraday futures price against its own open interest.

    Deliberately the same shape as the Options Lab's series response so the
    client keeps one parser, with one addition: ``source``, because a page
    drawn from a generated board must be able to say so.
    """

    instrument_id: str
    symbol: str
    expiry_date: str | None = Field(
        default=None, description="ISO date of the contract these frames priced."
    )
    open_ts: str
    now_ts: str
    data_quality: str = Field(description="intraday | live_proxy | empty")
    open_is_estimated: bool = Field(
        default=False,
        description="True when the opening point is inferred rather than captured.",
    )
    interval: str
    source: str = Field(default="mock", description="live | mock")
    t: list[str] = Field(default_factory=list, description="Frame timestamps, UTC ISO.")
    price: list[float] = Field(default_factory=list)
    oi: list[int | None] = Field(
        default_factory=list,
        description=(
            "Futures open interest, not the option chain's. Null where a frame "
            "fell between open-interest sweeps — a genuine gap, not a zero."
        ),
    )
