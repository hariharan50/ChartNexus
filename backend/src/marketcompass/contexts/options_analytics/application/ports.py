"""Ports the Open Interest use case depends on.

All three are satisfied by infrastructure adapters, keeping this context free of
any import of ``market_data`` or the persistence layer.

* ``ChainProvider`` yields a live option chain (rows + spot + contract meta).
* ``SnapshotReader`` yields stored intraday chains. There is no writer for these
  yet, so the shipped adapter returns nothing and the service serves the live
  tier; when ingestion lands, the intraday tier activates with no service change.
* ``CandleSource`` yields the underlying index's own price bars. Option analytics
  needs them to draw positions *against price*, and they come from a different
  upstream call than the chain does.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

from marketcompass.contexts.options_analytics.domain.oi_math import ChainRow
from marketcompass.shared_kernel.types.identifiers import TenantId


@dataclass(frozen=True, slots=True)
class ProviderChain:
    """A live chain plus the contract metadata the payload needs."""

    rows: tuple[ChainRow, ...]
    spot: float | None
    lot_size: int | None = None
    expiry: str | None = None


@dataclass(frozen=True, slots=True)
class ChainSnapshot:
    """One stored option-chain observation for a tenant/symbol at a point in time.

    ``captured_at`` is naive-UTC as stored in the database; the service attaches
    the timezone on read.

    ``spot``/``atm_strike``/``max_pain`` are what the market looked like *at this
    instant*, not now. Scrubbing the timeline is meaningless without them: the
    bars would redraw for 10:30 while the spot line and max-pain marker stayed
    pinned to the latest snapshot. They are optional because the live tier
    synthesises frames that have no stored header to read them from.
    """

    captured_at: datetime
    rows: tuple[ChainRow, ...] = field(default_factory=tuple)
    spot: float | None = None
    atm_strike: float | None = None
    max_pain: float | None = None
    # The current-month future at this instant. Price overlays plot *this*, not
    # spot: it is the tradable instrument, and on a chart of option positions
    # the index level is the one price nobody in the picture can deal at.
    future_price: float | None = None


@dataclass(frozen=True, slots=True)
class Candle:
    """One price bar of the underlying index.

    ``opened_at`` is the instant the bar *starts*, in UTC — the convention the
    charting client expects, and the one the broker's history endpoint uses.

    No volume field: index candles carry the index's own turnover, which is a
    different quantity from the option volume every Options Lab tool means when
    it says "volume". Leaving it out is cheaper than leaving a plausible-looking
    number that nobody should plot next to a chain total.
    """

    opened_at: datetime
    open: float
    high: float
    low: float
    close: float


@runtime_checkable
class ChainProvider(Protocol):
    async def fetch(
        self, tenant_id: TenantId, symbol: str, *, expiry: str | None = None
    ) -> ProviderChain:
        """The chain for ``expiry``, or the nearest one when it is ``None``."""
        ...


@runtime_checkable
class CandleSource(Protocol):
    """Reads the underlying's price bars. Never raises on absence — returns empty."""

    async def minute_candles(
        self, tenant_id: TenantId, symbol: str, *, trade_date_utc: datetime
    ) -> list[Candle]:
        """One-minute bars for the IST trading day containing ``trade_date_utc``.

        Always one-minute, never the caller's display interval: the broker does
        not offer every bucket the UI does, and a caller that must align these
        against option captures is already doing its own bucketing. One grid,
        aggregated once, beats two rounding rules that disagree at the edges.
        """
        ...


@runtime_checkable
class SnapshotReader(Protocol):
    """Reads stored intraday snapshots. Never raises on absence — returns empty."""

    async def latest_in_session(
        self, tenant_id: TenantId, symbol: str, *, now_utc: datetime
    ) -> ChainSnapshot | None: ...

    async def day_snapshots(
        self, tenant_id: TenantId, symbol: str, *, trade_date_utc: datetime
    ) -> list[ChainSnapshot]: ...
