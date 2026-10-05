"""The tracked global markets, and where each one sits in the trading day.

An Indian trader reads these instruments for one reason: to work out where
NIFTY will open. That purpose shapes every field here.

**Session hours are stored in the exchange's own timezone, never in IST.**
London and New York shift an hour against India twice a year, and India does
not observe daylight saving at all, so a hardcoded "US opens 19:00 IST" is
wrong for roughly half the calendar. :func:`session_window` converts at read
time through ``zoneinfo``, which is the only way the timeline places a band on
the right hour in March and again in November.

**A market's weight is its pull on the Indian open, not its size.** The Dow is
a smaller index than the S&P by every measure that matters to an American; to
someone predicting NIFTY's gap it carries less information than the S&P
because the two move together and the S&P is the cleaner read. The weights are
declared — and declared *unfitted* — in :mod:`.handoff`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Final
from zoneinfo import ZoneInfo

#: India has no daylight saving, so a fixed offset is exact here and avoids a
#: tzdata lookup on a value read on every band of every render.
IST: Final = timezone(timedelta(hours=5, minutes=30), "IST")

#: The NSE cash session, which is what the whole module is oriented around:
#: the overnight window runs from one close to the next open.
NIFTY_OPEN: Final = time(9, 15)
NIFTY_CLOSE: Final = time(15, 30)


class Region(StrEnum):
    """Where a market sits in the relay.

    Ordered the way the baton actually passes on an Indian trading day, which
    is the order the board and the timeline render in.
    """

    ASIA = "asia"
    EUROPE = "europe"
    AMERICAS = "americas"
    INDIA = "india"
    MACRO = "macro"


#: Regions in handoff order. Iterating a ``StrEnum`` gives declaration order,
#: but naming the sequence makes the intent explicit at the call sites.
REGION_ORDER: Final[tuple[Region, ...]] = (
    Region.ASIA,
    Region.EUROPE,
    Region.AMERICAS,
    Region.INDIA,
    Region.MACRO,
)

REGION_LABELS: Final[dict[Region, str]] = {
    Region.ASIA: "Asia",
    Region.EUROPE: "Europe",
    Region.AMERICAS: "Americas",
    Region.INDIA: "India",
    Region.MACRO: "Macro",
}


@dataclass(frozen=True, slots=True)
class GlobalMarket:
    """One tracked instrument and its place in the trading day."""

    key: str
    label: str
    #: The provider's identifier. Kept out of the domain's vocabulary
    #: everywhere else — only the adapter should care what Yahoo calls this.
    symbol: str
    region: Region
    #: IANA zone of the exchange, e.g. ``America/New_York``.
    tz: str
    opens: time
    closes: time
    #: Signed pull on the NIFTY gap. Zero for instruments that are context
    #: rather than signal, and for GIFT — see :mod:`.handoff`.
    gap_weight: Decimal
    #: A macro row is shown beside the board, not scored or placed on the
    #: timeline: crude has no "session" an Indian open hands off from.
    macro: bool = False
    #: Moves against the market it measures. VIX is the only one: it is a
    #: volatility gauge, not a directional index, so it carries a negative
    #: weight in the composite and is excluded from any regional average -
    #: averaging a 6.8% VIX spike in with three falling US indices would print
    #: "Americas +1.07%" on a night New York sold off hard.
    inverted: bool = False
    #: Trades effectively around the clock - FX and the energy/metal futures.
    #: The board prints "24h" for these rather than a window: an instrument
    #: with no close has no opening hours, and deriving a pair of times from a
    #: 00:00-23:59 span renders as the nonsensical "04:30-04:29".
    round_the_clock: bool = False

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.tz)


def _w(value: str) -> Decimal:
    return Decimal(value)


#: Every tracked instrument.
#:
#: The nine indices are the ones on the reference board. The macro rows below
#: them are what explains *why* those indices moved — an Indian trader reading
#: a red S&P wants to know whether crude and the dollar moved with it.
MARKETS: Final[tuple[GlobalMarket, ...]] = (
    # -- Asia: trades alongside India, so it is the least "overnight" of the
    # three blocs and the first to hand the baton on.
    GlobalMarket(
        key="NIKKEI",
        label="Nikkei 225",
        symbol="^N225",
        region=Region.ASIA,
        tz="Asia/Tokyo",
        opens=time(9, 0),
        closes=time(15, 30),
        gap_weight=_w("0.30"),
    ),
    GlobalMarket(
        key="HSI",
        label="Hang Seng",
        symbol="^HSI",
        region=Region.ASIA,
        tz="Asia/Hong_Kong",
        opens=time(9, 30),
        closes=time(16, 0),
        gap_weight=_w("0.25"),
    ),
    GlobalMarket(
        key="SHANGHAI",
        label="SSE Composite",
        symbol="000001.SS",
        region=Region.ASIA,
        tz="Asia/Shanghai",
        opens=time(9, 30),
        closes=time(15, 0),
        gap_weight=_w("0.10"),
    ),
    # -- Europe: overlaps the Indian afternoon and runs past its close.
    GlobalMarket(
        key="FTSE",
        label="FTSE 100",
        symbol="^FTSE",
        region=Region.EUROPE,
        tz="Europe/London",
        opens=time(8, 0),
        closes=time(16, 30),
        gap_weight=_w("0.30"),
    ),
    GlobalMarket(
        key="DAX",
        label="DAX",
        symbol="^GDAXI",
        region=Region.EUROPE,
        tz="Europe/Berlin",
        opens=time(9, 0),
        closes=time(17, 30),
        gap_weight=_w("0.30"),
    ),
    # -- Americas: closes at 01:30 IST, hours before the Indian open, and is
    # the single loudest input to the gap.
    GlobalMarket(
        key="SPX",
        label="S&P 500",
        symbol="^GSPC",
        region=Region.AMERICAS,
        tz="America/New_York",
        opens=time(9, 30),
        closes=time(16, 0),
        gap_weight=_w("1.00"),
    ),
    GlobalMarket(
        key="NASDAQ",
        label="NASDAQ",
        symbol="^IXIC",
        region=Region.AMERICAS,
        tz="America/New_York",
        opens=time(9, 30),
        closes=time(16, 0),
        gap_weight=_w("0.70"),
    ),
    GlobalMarket(
        key="DJIA",
        label="Dow Jones",
        symbol="^DJI",
        region=Region.AMERICAS,
        tz="America/New_York",
        opens=time(9, 30),
        closes=time(16, 0),
        gap_weight=_w("0.40"),
    ),
    GlobalMarket(
        key="VIX",
        label="CBOE VIX",
        symbol="^VIX",
        region=Region.AMERICAS,
        tz="America/New_York",
        opens=time(9, 30),
        closes=time(16, 0),
        # Negative: a VIX spike is risk coming off, which pulls the Indian
        # open down. This is the one row whose sign is inverted, and getting
        # it wrong would quietly flip part of the composite.
        gap_weight=_w("-0.25"),
        inverted=True,
    ),
    # -- India: the thing being predicted. Weight zero — scoring NIFTY's own
    # move into a forecast of NIFTY's open would be circular.
    GlobalMarket(
        key="NIFTY",
        label="NIFTY 50",
        symbol="^NSEI",
        region=Region.INDIA,
        tz="Asia/Kolkata",
        opens=NIFTY_OPEN,
        closes=NIFTY_CLOSE,
        gap_weight=_w("0"),
    ),
    # -- Macro: context beside the board, never scored.
    GlobalMarket(
        key="CRUDE",
        label="Crude Oil",
        symbol="CL=F",
        region=Region.MACRO,
        tz="America/New_York",
        opens=time(9, 0),
        closes=time(14, 30),
        gap_weight=_w("0"),
        macro=True,
        round_the_clock=True,
    ),
    GlobalMarket(
        key="GOLD",
        label="Gold",
        symbol="GC=F",
        region=Region.MACRO,
        tz="America/New_York",
        opens=time(9, 0),
        closes=time(14, 30),
        gap_weight=_w("0"),
        macro=True,
        round_the_clock=True,
    ),
    GlobalMarket(
        key="USDINR",
        label="USD / INR",
        symbol="USDINR=X",
        region=Region.MACRO,
        tz="Europe/London",
        opens=time(0, 0),
        closes=time(23, 59),
        gap_weight=_w("0"),
        macro=True,
        round_the_clock=True,
    ),
    GlobalMarket(
        key="US10Y",
        label="US 10Y Yield",
        symbol="^TNX",
        region=Region.MACRO,
        tz="America/New_York",
        opens=time(9, 30),
        closes=time(16, 0),
        gap_weight=_w("0"),
        macro=True,
    ),
)

#: The synthetic key GIFT NIFTY is served under. Not in :data:`MARKETS`
#: because no quote provider carries it — it has its own port and its own
#: adapter, and it is read separately everywhere.
GIFT_KEY: Final = "GIFTNIFTY"
GIFT_LABEL: Final = "GIFT NIFTY"

BY_KEY: Final[dict[str, GlobalMarket]] = {market.key: market for market in MARKETS}

#: The instruments that carry a gap weight, in board order. The composite
#: iterates this rather than filtering :data:`MARKETS` at each call site.
SCORED: Final[tuple[GlobalMarket, ...]] = tuple(
    market for market in MARKETS if market.gap_weight != 0
)


def session_window(market: GlobalMarket, session: date) -> tuple[datetime, datetime]:
    """``market``'s session on ``session``, as two aware IST instants.

    ``session`` is the market's **own** local date, so a US session dated the
    24th returns 19:00 on the 24th to 01:30 on the 25th, IST. Built through
    the exchange's zone so the offset is whatever was actually in force that
    day — the reason this is a function and not a table.
    """
    zone = market.zone
    opens = datetime.combine(session, market.opens, tzinfo=zone)
    closes = datetime.combine(session, market.closes, tzinfo=zone)
    if closes <= opens:
        # A session that crosses local midnight. None of the tracked rows do
        # today, but a futures row added later would, and silently returning
        # a negative-length band would be worse than handling it here.
        closes += timedelta(days=1)
    return opens.astimezone(IST), closes.astimezone(IST)
