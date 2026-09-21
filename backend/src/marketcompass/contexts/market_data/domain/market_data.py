"""Canonical market-data shapes.

Every provider — live broker or mock — returns exactly these types, so nothing
downstream can tell them apart by structure. What it *can* tell apart is
``source`` and ``age_seconds``, and it must: a chart drawn from an hour-old
cached snapshot looks identical to a live one, and acting on that difference is
the user's decision to make.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol


class DataSource(StrEnum):
    """Where a payload actually came from."""

    LIVE = "live"
    """Fetched from the broker just now."""

    CACHED = "cached"
    """A previous broker response, reused because the broker is unreachable or
    the value is still inside its freshness window."""

    MOCK = "mock"
    """Synthetic. No broker was involved. Never safe for a trading decision."""

    @property
    def is_real(self) -> bool:
        return self is not DataSource.MOCK


class OptionType(StrEnum):
    CALL = "CE"
    PUT = "PE"


@dataclass(frozen=True, slots=True)
class Provenance:
    """Attached to every payload so consumers can judge how much to trust it."""

    source: DataSource
    fetched_at: datetime
    age_seconds: float = 0.0

    @property
    def is_stale(self) -> bool:
        return self.source is not DataSource.LIVE


@dataclass(frozen=True, slots=True)
class Quote:
    """An index spot price."""

    instrument: InstrumentSymbol
    price: Decimal
    change: Decimal | None
    change_percent: Decimal | None
    provenance: Provenance


@dataclass(frozen=True, slots=True)
class FuturesQuote:
    """The underlying's front-month futures contract.

    ``contract`` is the broker symbol of the currently-active monthly contract
    (e.g. ``NSE:NIFTY25AUGFUT``); ``expiry`` is that contract's ISO expiry date.
    The active contract rolls forward the moment the current month's expiry
    passes, so this always tracks the near-month future without any hard-coded
    series.
    """

    instrument: InstrumentSymbol
    contract: str
    expiry: str
    price: Decimal
    change: Decimal | None
    change_percent: Decimal | None
    volume: int
    day_high: Decimal | None
    day_low: Decimal | None
    provenance: Provenance
    # Open interest on this contract, and the same figure at the previous
    # close. Both optional: the cash segment has no OI at all, and not every
    # broker payload carries the previous day's. The build-up read needs them,
    # and it must be able to tell "no OI reported" from "OI of zero".
    open_interest: int | None = None
    previous_open_interest: int | None = None
    # Yesterday's settlement, when the broker states it. Lets a day's move be
    # computed without waiting for this session's first snapshot.
    previous_close: Decimal | None = None
    # The session's opening print. With the day's high and low it answers
    # whether the contract opened on its low or its high, which is the
    # structural read the "O=L" / "O=H" badge shows.
    day_open: Decimal | None = None
    # Yesterday's traded volume. No broker payload observed so far carries it,
    # so expect None on live data until we archive our own daily volume —
    # which is precisely why volume change has to be nullable downstream.
    previous_volume: int | None = None


@dataclass(frozen=True, slots=True)
class OpenInterestReading:
    """Open interest on one contract, and where it stood at the last close.

    Separate from :class:`FuturesQuote` because the two come from different
    endpoints at different cadences: price ticks by the second, open interest
    is a slow daily aggregate fetched one contract at a time.
    """

    instrument: InstrumentSymbol
    open_interest: int
    previous_open_interest: int | None
    observed_at: datetime


class CandleInterval(StrEnum):
    """Bar sizes the history endpoint serves.

    A closed set rather than a free-form string: each maps to one broker
    resolution and one range limit, and an unrecognised value would reach the
    broker as a 4xx rather than a useful error here.
    """

    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    D1 = "1d"

    @property
    def seconds(self) -> int:
        return {
            CandleInterval.M1: 60,
            CandleInterval.M5: 300,
            CandleInterval.M15: 900,
            CandleInterval.H1: 3600,
            CandleInterval.D1: 86_400,
        }[self]

    @property
    def max_days(self) -> int:
        """How far back this resolution may be asked for.

        The broker caps the range per resolution — a year of one-minute bars is
        an error, not a slow response — and the cap is enforced here so both
        providers behave the same way.
        """
        return {
            CandleInterval.M1: 15,
            CandleInterval.M5: 60,
            CandleInterval.M15: 90,
            CandleInterval.H1: 180,
            CandleInterval.D1: 365,
        }[self]


@dataclass(frozen=True, slots=True)
class Candle:
    """One price bar. ``opened_at`` is the bar's start, in UTC."""

    opened_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


@dataclass(frozen=True, slots=True)
class CandleSeries:
    """A price history, oldest bar first."""

    instrument: InstrumentSymbol
    interval: CandleInterval
    candles: tuple[Candle, ...]
    provenance: Provenance


@dataclass(frozen=True, slots=True)
class OptionQuote:
    """One side of a strike."""

    last_price: Decimal
    open_interest: int
    open_interest_change: int
    volume: int
    implied_volatility: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    delta: Decimal | None = None


@dataclass(frozen=True, slots=True)
class StrikeRow:
    """A strike with its call and put legs.

    Either side may be missing: illiquid far strikes are not always quoted, and
    inventing a zero there would corrupt PCR and max-pain.
    """

    strike: Decimal
    call: OptionQuote | None = None
    put: OptionQuote | None = None


@dataclass(frozen=True, slots=True)
class OptionChain:
    instrument: InstrumentSymbol
    expiry: str
    """ISO ``YYYY-MM-DD``. Always normalised, never a broker-specific format."""

    spot_price: Decimal
    strikes: tuple[StrikeRow, ...]
    provenance: Provenance
    expiries: tuple[str, ...] = ()
    lot_size: int | None = None
    change_percent: Decimal | None = None
    future_price: Decimal | None = None
    india_vix: Decimal | None = None
    """India VIX's own LTP — the broker's options-chain response happens to
    include it alongside the chain, so no separate fetch is needed."""
    india_vix_change_percent: Decimal | None = None
    iv_percentile: Decimal | None = None
    """Where today's ATM IV ranks (0-100) among readings taken so far this
    session. Intraday only — there is no cross-day IV history yet."""
    _atm: Decimal | None = field(default=None, repr=False)

    @property
    def put_call_ratio(self) -> Decimal | None:
        """ΣPE open interest / ΣCE open interest.

        None rather than zero when there is no call interest — a ratio with an
        empty denominator is undefined, and returning 0 would read as
        "extremely bullish".
        """
        call_oi = sum(row.call.open_interest for row in self.strikes if row.call)
        put_oi = sum(row.put.open_interest for row in self.strikes if row.put)
        if call_oi <= 0:
            return None
        return (Decimal(put_oi) / Decimal(call_oi)).quantize(Decimal("0.0001"))

    @property
    def atm_strike(self) -> Decimal | None:
        """The listed strike nearest spot.

        Nearest *listed*, not a rounded spot: the chain decides which strikes
        exist, and a computed one may not be tradeable.
        """
        if self._atm is not None:
            return self._atm
        if not self.strikes:
            return None
        return min(self.strikes, key=lambda row: abs(row.strike - self.spot_price)).strike

    @property
    def total_call_open_interest(self) -> int:
        return sum(row.call.open_interest for row in self.strikes if row.call)

    @property
    def total_put_open_interest(self) -> int:
        return sum(row.put.open_interest for row in self.strikes if row.put)


@dataclass(frozen=True, slots=True)
class ExpiryList:
    instrument: InstrumentSymbol
    expiries: tuple[str, ...]
    provenance: Provenance


@dataclass(frozen=True, slots=True)
class MarketStatus:
    """Whether the exchange is open, and what is feeding us."""

    is_open: bool
    session_date: str
    time_ist: str
    provider: str
    connected: bool
    source: DataSource
    market_open: str
    market_close: str
