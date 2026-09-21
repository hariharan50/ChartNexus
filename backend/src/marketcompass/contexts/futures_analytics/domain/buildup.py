"""Pure futures build-up math.

No framework, no I/O. Turns a list of futures readings into the six buckets the
Future Dashboard ranks: top gainers and losers by price, and the four
positioning states derived from price direction against open-interest
direction.

The classification is the standard 2x2 read of the futures tape:

===========  ==========  ==================  ===========================
Price        Open int.   State               What it means
===========  ==========  ==================  ===========================
up           up          LONG_BUILDUP        fresh longs entering
down         up          SHORT_BUILDUP       fresh shorts entering
up           down        SHORT_COVERING      shorts closing out
down         down        LONG_UNWINDING      longs closing out
===========  ==========  ==================  ===========================

Rising open interest means money is *entering* the contract, so price
direction tells you which side is doing it. Falling open interest means
positions are being closed, so price direction tells you which side is
capitulating. That is the whole model, and it is why both deltas must be
measured over the same window — comparing a price change since yesterday's
close against an OI change since this morning's open would classify nonsense
with complete confidence.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class BuildupState(StrEnum):
    """Where a contract sits in the 2x2."""

    LONG_BUILDUP = "long_buildup"
    SHORT_BUILDUP = "short_buildup"
    SHORT_COVERING = "short_covering"
    LONG_UNWINDING = "long_unwinding"
    #: Neither delta moved enough to call. Not a fifth quadrant — an honest
    #: refusal to read signal into noise.
    NEUTRAL = "neutral"


# Below this, a move is rounding rather than direction. Applied to both axes:
# a contract that ticked one paisa on four lots is not "building longs".
DEFAULT_DEADBAND_PERCENT = Decimal("0.05")

#: Opened on the low — bullish structure. Opened on the high — bearish.
OPEN_EQUALS_LOW = "O=L"
OPEN_EQUALS_HIGH = "O=H"


@dataclass(frozen=True, slots=True)
class FuturesReading:
    """One contract's price and open interest, and where both started.

    ``*_open`` are the values at the start of the comparison window. Keeping
    them rather than a pre-computed delta means the deadband and the percentage
    are derived here, once, instead of by every caller.
    """

    symbol: str
    price: Decimal
    price_open: Decimal
    #: Optional because not every feed carries it. FYERS' quote endpoint does
    #: not, and dropping an otherwise good price for want of open interest is
    #: how a whole live board ends up replaced by simulated data.
    open_interest: int | None = None
    open_interest_open: int | None = None
    name: str | None = None
    # "index" or "stock", as the catalog classifies it. A plain string rather
    # than the catalog's enum: this context may not import that one, and the
    # maths here does not branch on it — it is carried so a caller can ask for
    # the stock universe without joining against a second endpoint.
    kind: str | None = None
    #: ISO date of this contract's expiry. Per reading, not per board: NSE and
    #: BSE settle on different days, so one date cannot describe the universe.
    expiry: str | None = None
    lot_size: int | None = None
    volume: int | None = None
    #: Yesterday's volume, when known. Usually absent on live data.
    volume_open: int | None = None
    #: The session's open, high and low, for the open-marker read below.
    day_open: Decimal | None = None
    day_high: Decimal | None = None
    day_low: Decimal | None = None
    sector: str | None = None

    @property
    def price_change_percent(self) -> Decimal | None:
        return _percent_change(self.price, self.price_open)

    @property
    def oi_change_percent(self) -> Decimal | None:
        if self.open_interest is None or self.open_interest_open is None:
            return None
        return _percent_change(Decimal(self.open_interest), Decimal(self.open_interest_open))

    @property
    def volume_change_percent(self) -> Decimal | None:
        """Today's volume against yesterday's, or ``None`` when unknown."""
        if self.volume is None or self.volume_open is None:
            return None
        return _percent_change(Decimal(self.volume), Decimal(self.volume_open))

    @property
    def open_marker(self) -> str | None:
        """``O=L`` when the contract opened on its low, ``O=H`` on its high.

        A day that has not traded below its opening print means every buyer
        since the bell is in profit — the classic intraday strength read, and
        its mirror for weakness. Requires all three prints; any missing one
        makes the question unanswerable rather than false.
        """
        if self.day_open is None or self.day_high is None or self.day_low is None:
            return None
        if self.day_open == self.day_low:
            return OPEN_EQUALS_LOW
        if self.day_open == self.day_high:
            return OPEN_EQUALS_HIGH
        return None


@dataclass(frozen=True, slots=True)
class BuildupRow:
    """A reading with its verdict attached — one row of the dashboard."""

    symbol: str
    name: str | None
    price: Decimal
    price_change_percent: Decimal | None
    open_interest: int | None
    oi_change_percent: Decimal | None
    state: BuildupState
    kind: str | None = None
    lot_size: int | None = None
    volume: int | None = None
    volume_change_percent: Decimal | None = None
    open_marker: str | None = None
    sector: str | None = None


def _percent_change(now: Decimal, start: Decimal) -> Decimal | None:
    """Percentage move, or ``None`` when there is no baseline to move from.

    Returning ``None`` rather than ``0`` matters: "we have no opening value for
    this contract" and "this contract has not moved" are different facts, and a
    dashboard that renders them identically is lying about the second one.
    """
    if start == 0:
        return None
    return (now - start) / start * 100


def classify(
    reading: FuturesReading,
    *,
    deadband_percent: Decimal = DEFAULT_DEADBAND_PERCENT,
) -> BuildupState:
    """Which quadrant this contract sits in.

    Both deltas are required. Without open interest the question is
    unanswerable — price alone cannot separate fresh longs from short
    covering — so the honest answer is NEUTRAL rather than a guess.
    """
    price_delta = reading.price_change_percent
    oi_delta = reading.oi_change_percent

    if price_delta is None or oi_delta is None:
        return BuildupState.NEUTRAL
    if abs(price_delta) < deadband_percent or abs(oi_delta) < deadband_percent:
        return BuildupState.NEUTRAL

    if oi_delta > 0:
        return BuildupState.LONG_BUILDUP if price_delta > 0 else BuildupState.SHORT_BUILDUP
    return BuildupState.SHORT_COVERING if price_delta > 0 else BuildupState.LONG_UNWINDING


def to_rows(
    readings: Iterable[FuturesReading],
    *,
    deadband_percent: Decimal = DEFAULT_DEADBAND_PERCENT,
) -> list[BuildupRow]:
    return [
        BuildupRow(
            symbol=reading.symbol,
            name=reading.name,
            price=reading.price,
            price_change_percent=reading.price_change_percent,
            open_interest=reading.open_interest,
            oi_change_percent=reading.oi_change_percent,
            state=classify(reading, deadband_percent=deadband_percent),
            kind=reading.kind,
            lot_size=reading.lot_size,
            volume=reading.volume,
            volume_change_percent=reading.volume_change_percent,
            open_marker=reading.open_marker,
            sector=reading.sector,
        )
        for reading in readings
    ]


def top_gainers(rows: Sequence[BuildupRow], *, limit: int) -> list[BuildupRow]:
    """Biggest positive price moves. Contracts with no baseline are excluded
    rather than sorted as zero."""
    return _ranked(rows, key=lambda row: row.price_change_percent, descending=True, limit=limit)


def top_losers(rows: Sequence[BuildupRow], *, limit: int) -> list[BuildupRow]:
    return _ranked(rows, key=lambda row: row.price_change_percent, descending=False, limit=limit)


def in_state(rows: Sequence[BuildupRow], state: BuildupState, *, limit: int) -> list[BuildupRow]:
    """The strongest examples of one positioning state.

    Ranked by open-interest move, because that is what the bucket is about: the
    question "which contracts are seeing the most fresh shorts" is answered by
    OI, not by which of them happened to fall furthest.
    """
    matching = [row for row in rows if row.state is state]
    return _ranked(
        matching,
        key=lambda row: row.oi_change_percent,
        descending=state in _OI_RISING,
        limit=limit,
    )


_OI_RISING = frozenset({BuildupState.LONG_BUILDUP, BuildupState.SHORT_BUILDUP})


def _ranked(
    rows: Sequence[BuildupRow],
    *,
    key: Callable[[BuildupRow], Decimal | None],
    descending: bool,
    limit: int,
) -> list[BuildupRow]:
    """Sort by ``key``, dropping rows that have none.

    A missing percentage is missing, not zero — ranking it as zero would park
    contracts we know nothing about in the middle of the table as though that
    were a measurement.
    """
    scored = [(row, key(row)) for row in rows]
    present = [(row, value) for row, value in scored if value is not None]
    present.sort(key=lambda pair: pair[1], reverse=descending)
    return [row for row, _ in present[:limit]]
