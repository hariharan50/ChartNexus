"""What the outside world hands this context, in this context's own words.

Every port in ``application/ports.py`` returns one of these. They are not the
shapes ``market_data``, ``options_analytics``, ``global_markets`` or
``market_breadth`` use — those belong to those contexts, and a bounded context
may not import another's types. The adapters in ``infrastructure/pre_market/``
translate at the boundary, which is the whole reason the boundary holds.

The translation is not bureaucracy. It is where four providers' different
spellings of "previous close" get reconciled once, in one place, instead of
four times across the domain.

**Everything optional is ``| None``, never a default.** A missing PCR and a PCR
of zero are different facts, and a screener that renders the second when it
means the first is worse than one that renders nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from chartnexus.shared_kernel.domain.levels import Bar


@dataclass(frozen=True, slots=True)
class SpotReading:
    """One index's live quote."""

    symbol: str
    label: str
    price: Decimal
    previous_close: Decimal | None
    day_open: Decimal | None
    change: Decimal | None
    change_percent: Decimal | None
    #: ``live`` / ``cached`` / ``mock`` — carried through to the badge so the
    #: page never presents generated numbers as observed ones.
    source: str


@dataclass(frozen=True, slots=True)
class CandleSeries:
    """Daily bars, oldest first, for one instrument.

    Already converted to floats and to the shared kernel's ``Bar``: the
    level and indicator maths is float-based, and converting once here keeps
    the conversion out of every call site.
    """

    symbol: str
    bars: tuple[Bar, ...]
    #: ``True`` when the series came from the broker rather than the simulator.
    live: bool = True

    @property
    def closes(self) -> tuple[float, ...]:
        return tuple(bar.close for bar in self.bars)

    @property
    def highs(self) -> tuple[float, ...]:
        return tuple(bar.high for bar in self.bars)

    @property
    def lows(self) -> tuple[float, ...]:
        return tuple(bar.low for bar in self.bars)


@dataclass(frozen=True, slots=True)
class OptionsReading:
    """The option book, reduced to what a pre-market read needs.

    Deliberately not the whole chain. The screener wants positioning and a
    priced range; anyone who wants the ladder has Options Lab.
    """

    expiry: date | None
    days_to_expiry: int | None
    spot: Decimal | None
    atm_strike: Decimal | None
    pcr_oi: Decimal | None
    pcr_change: Decimal | None
    total_call_oi: int | None
    total_put_oi: int | None
    max_pain: Decimal | None
    #: The heaviest call and put strikes. Named "wall" by convention; the UI
    #: must present them as where positioning sits, not as levels that hold.
    call_wall: Decimal | None
    put_wall: Decimal | None
    gamma_flip: Decimal | None
    atm_iv: Decimal | None
    iv_percentile: Decimal | None
    #: CE + PE at the money — the market's own price for a one-expiry move.
    atm_straddle: Decimal | None
    india_vix: Decimal | None
    india_vix_change_percent: Decimal | None
    source: str = "live"


@dataclass(frozen=True, slots=True)
class GiftReading:
    """GIFT NIFTY, and the overnight range it traded through."""

    level: Decimal | None
    change: Decimal | None
    change_percent: Decimal | None
    overnight_high: Decimal | None
    overnight_low: Decimal | None
    #: GIFT against the NIFTY close the next session opens from.
    gap_points: Decimal | None
    gap_percent: Decimal | None
    signal: str | None


@dataclass(frozen=True, slots=True)
class GlobalContribution:
    """One market's share of the overnight composite."""

    key: str
    label: str
    region: str
    change_percent: Decimal
    points: Decimal


@dataclass(frozen=True, slots=True)
class GlobalReading:
    """What the world did overnight, already weighed."""

    pressure_score: Decimal | None
    pressure_band: str | None
    contributions: tuple[GlobalContribution, ...] = ()
    #: Weighted markets that had no quote. A composite built from four of nine
    #: inputs is a different claim from one built from all nine.
    missing: tuple[str, ...] = ()
    gift: GiftReading | None = None
    #: Crude, gold, the rupee, the ten-year — context, not inputs.
    macro: tuple[GlobalContribution, ...] = ()


@dataclass(frozen=True, slots=True)
class BreadthReading:
    """Participation across an index's members."""

    advances: int | None
    declines: int | None
    unchanged: int | None
    #: How many members were actually priced, and how many the index has. Every
    #: percentage this context derives ships with both.
    priced: int | None
    universe: int | None


@dataclass(frozen=True, slots=True)
class FlowReading:
    """Yesterday's institutional net, in rupees crore."""

    session_date: date | None
    fii_net: Decimal | None
    dii_net: Decimal | None


@dataclass(frozen=True, slots=True)
class MarketPhase:
    """Where the clock is, relative to the Indian session."""

    is_open: bool
    session_date: str
    time_ist: str
    opens_ist: str
    closes_ist: str


@dataclass(frozen=True, slots=True)
class NarrativeReading:
    """The stored morning prose, if a briefing has been written today."""

    markdown: str
    trading_day: date
    generated_at: datetime | None
    source: str


@dataclass(frozen=True, slots=True)
class IndexDefinition:
    """One of the three headline indices the page follows."""

    symbol: str
    label: str
    #: ``False`` for SENSEX today: no constituent weight table exists, so the
    #: participation panels have nothing to count. Named rather than left to
    #: render as an empty chart, which reads as a bug.
    breadth_tracked: bool = True


HEADLINE_INDICES: tuple[IndexDefinition, ...] = (
    IndexDefinition(symbol="NIFTY", label="NIFTY 50"),
    IndexDefinition(symbol="BANKNIFTY", label="BANK NIFTY"),
    IndexDefinition(symbol="SENSEX", label="SENSEX", breadth_tracked=False),
)

BY_SYMBOL: dict[str, IndexDefinition] = {index.symbol: index for index in HEADLINE_INDICES}


@dataclass(frozen=True, slots=True)
class Sources:
    """Which provider answered for each leg, for the page's badge.

    Collected rather than reduced to one flag: the board can be live while the
    option chain is mocked, and collapsing that to a single "live" would be a
    lie about half the page.
    """

    parts: dict[str, str] = field(default_factory=dict)

    def weakest(self) -> str:
        """The honest badge for the page as a whole.

        ``mock`` beats ``cached`` beats ``live`` — a page is only as live as
        its least live input, and claiming otherwise is how simulated numbers
        end up being traded on.
        """
        values = set(self.parts.values())
        for tier in ("mock", "cached"):
            if tier in values:
                return tier
        return "live" if values else "mock"
