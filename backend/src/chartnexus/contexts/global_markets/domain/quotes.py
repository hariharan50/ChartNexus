"""A global quote, and where it came from.

The provenance vocabulary mirrors ``market_data``'s deliberately: bounded
contexts may not import one another, so this context declares its own copy
rather than reaching across, exactly as ``market_breadth`` does. The words mean
the same thing in both, which is the point — a badge reading "Simulated" on the
GIA page has to mean what it means on the dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class DataSource(StrEnum):
    LIVE = "live"
    CACHED = "cached"
    MOCK = "mock"


@dataclass(frozen=True, slots=True)
class Provenance:
    source: DataSource
    fetched_at: datetime

    @property
    def is_stale(self) -> bool:
        return self.source is not DataSource.LIVE


@dataclass(frozen=True, slots=True)
class GlobalQuote:
    """One instrument's latest reading.

    ``change`` and ``change_percent`` come from the provider rather than being
    derived from ``previous_close``: the provider computes them against the
    official prior settlement, which is not always the last close in whatever
    window happened to be requested. ``previous_close`` is then back-derived
    from them so the three figures can never disagree on screen.

    Every optional field is ``None`` when unknown, never zero. A market that
    did not publish a high is not a market that traded at zero.
    """

    key: str
    price: Decimal
    change: Decimal | None
    change_percent: Decimal | None
    previous_close: Decimal | None
    day_open: Decimal | None = None
    day_high: Decimal | None = None
    day_low: Decimal | None = None
    #: Recent closes, oldest first, for the board's sparkline. Empty when the
    #: provider returned no usable series.
    spark: tuple[Decimal, ...] = ()
    #: The exchange's own local date for this reading. The timeline needs it
    #: to place the band: a US quote read at 06:00 IST belongs to *yesterday's*
    #: New York session, and dating it "today" would draw it in the future.
    session: datetime | None = None
    provenance: Provenance | None = None

    @property
    def is_up(self) -> bool:
        return self.change_percent is not None and self.change_percent > 0


@dataclass(frozen=True, slots=True)
class QuoteSet:
    """Everything the page read, with the weakest provenance of the batch.

    One bad adapter among fourteen must not let the page claim it is live, so
    the summary source is the *worst* of what went into it, not the best.
    """

    quotes: dict[str, GlobalQuote] = field(default_factory=dict)
    source: DataSource = DataSource.MOCK
    fetched_at: datetime | None = None

    def get(self, key: str) -> GlobalQuote | None:
        return self.quotes.get(key)
