"""Synthetic quotes.

Deterministic by design: the same instrument at the same minute always produces
the same price, so tests are stable and a developer's screen does not flicker
with meaningless noise.

The price itself comes from :mod:`session_model`, which is the single simulation
behind every mock number in the app. This module used to run its own sine wave;
the option-chain factory and the snapshot seeder ran two more, and the three
disagreed. Everything price-shaped now reads the one walk.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from random import Random

from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.contexts.market_data.domain.market_data import (
    DataSource,
    FuturesQuote,
    Provenance,
    Quote,
)
from marketcompass.infrastructure.brokers.mock.session_model import (
    IST,
    base_level,
    lot_size,
    session_open_and_previous_close,
    spot_at,
    strike_step,
)

__all__ = [
    "base_level",
    "build_futures_quote",
    "build_quote",
    "in_ist",
    "lot_size",
    "open_interest_at",
    "previous_volume_at",
    "spot_price",
    "strike_step",
    "volume_at",
]

_SWING_PERCENT = Decimal("0.006")


def spot_price(instrument: InstrumentSymbol, moment: datetime) -> Decimal:
    """The simulated index level at ``moment``.

    Thin by design — it is the seam every existing caller already imports, so
    pointing it at the shared walk is what makes the dashboard, the futures
    strip, the option chain and the Open Interest page agree on one number.
    """
    return spot_at(instrument.value, moment)


def build_quote(instrument: InstrumentSymbol, moment: datetime) -> Quote:
    price = spot_price(instrument, moment)
    base = base_level(instrument)
    change = (price - base).quantize(Decimal("0.01"))
    change_percent = ((change / base) * Decimal(100)).quantize(Decimal("0.01"))
    # Both read off the same walk as ``price``, so the opening print a gap card
    # shows stays within the day's range of the spot beside it.
    day_open, previous_close = session_open_and_previous_close(instrument, moment)

    return Quote(
        instrument=instrument,
        price=price,
        change=change,
        change_percent=change_percent,
        day_open=day_open,
        previous_close=previous_close,
        provenance=Provenance(source=DataSource.MOCK, fetched_at=moment),
    )


# Futures trade at a small cost-of-carry premium to spot; a flat 7 bps keeps the
# synthetic number visibly a future without pretending to model the basis.
_FUTURES_BASIS = Decimal("0.0007")


# Open interest for the synthetic board.
#
# The Future Dashboard classifies a contract by price direction against OI
# direction, so a mock that returned a constant OI would leave every row
# NEUTRAL and the page permanently empty. These two functions give each
# instrument its own OI level and its own intraday drift, deterministically,
# so all four build-up quadrants actually populate.
# Roughly what the real board shows: a minority of contracts open exactly on
# the day's extreme, most somewhere inside the range.
_OPENS_ON_LOW_BELOW = 0.18
_OPENS_ON_HIGH_ABOVE = 0.88

_OI_BASE_LOTS = 40_000
_OI_SPREAD_LOTS = 360_000


# A day's volume spans four orders of magnitude across this universe — tens of
# thousands of lots on a sleepy mid-cap against millions on an index heavyweight
# — so the base is drawn log-uniformly rather than uniformly. A linear draw
# would cluster every instrument around the midpoint and make the column
# useless for telling names apart.
_VOLUME_FLOOR = 40_000
_VOLUME_SPAN = 200.0


def _volume_base(instrument: InstrumentSymbol, session_date: date) -> int:
    """What this contract trades in a full session."""
    rng = Random(f"volume:{instrument.value}:{session_date.isoformat()}")  # noqa: S311
    return int(_VOLUME_FLOOR * (_VOLUME_SPAN ** rng.random()))


def _session_fraction(local: datetime) -> float:
    """How much of the trading session has elapsed, 0 before the open."""
    minutes = local.hour * 60 + local.minute
    return min(max((minutes - _OPEN_MINUTES) / _SESSION_MINUTES, 0.0), 1.0)


def volume_at(instrument: InstrumentSymbol, moment: datetime) -> int:
    """Volume traded so far today.

    Accumulates through the session, and — like a real terminal — shows the
    previous session's completed total before the opening bell rather than a
    row of zeros.
    """
    local = in_ist(moment)
    elapsed = _session_fraction(local)
    if elapsed <= 0:
        return _volume_base(instrument, local.date() - timedelta(days=1))
    return max(1, int(_volume_base(instrument, local.date()) * elapsed))


def _volume_drift(instrument: InstrumentSymbol, session_date: date) -> float:
    """How today's volume compares with yesterday's, in roughly +/-45%.

    Yesterday is derived from today rather than drawn independently. Two
    independent log-uniform draws are uncorrelated, which produced day-on-day
    changes of +9,900% — arithmetically fine and financially nonsense. A
    contract's liquidity is a property of the contract; it varies session to
    session, it does not get re-rolled.
    """
    rng = Random(f"voldrift:{instrument.value}:{session_date.isoformat()}")  # noqa: S311
    return (rng.random() - 0.5) * 0.9


def previous_volume_at(instrument: InstrumentSymbol, moment: datetime) -> int:
    """Yesterday's volume at the same point in the session.

    Like-for-like on purpose: comparing this morning's first hour against
    yesterday's *whole* day would report every contract down 80% at 10am.
    """
    local = in_ist(moment)
    elapsed = _session_fraction(local)
    # Before the open both figures are completed sessions, so the comparison is
    # yesterday against the day before.
    session_date = local.date() if elapsed > 0 else local.date() - timedelta(days=1)
    today = _volume_base(instrument, session_date)
    yesterday = today / (1 + _volume_drift(instrument, session_date))
    return max(1, int(yesterday * (elapsed if elapsed > 0 else 1.0)))


#: What fraction of the near month's book a back month carries: roughly a
#: tenth for the next month, a fiftieth for the far. Open interest concentrates
#: overwhelmingly in the front contract and only rolls outwards near expiry,
#: and a mock that gave all three series the same figures would make the expiry
#: picker look broken — three identical boards under three different dates.
_SERIES_LIQUIDITY: tuple[float, ...] = (1.0, 0.11, 0.02)


def _liquidity(series: int) -> float:
    """How liquid the ``series``-th contract is against the near month."""
    return _SERIES_LIQUIDITY[min(max(series, 0), len(_SERIES_LIQUIDITY) - 1)]


def _oi_seed(instrument: InstrumentSymbol, session_date: date, series: int = 0) -> Random:
    """A generator keyed to the instrument, the day and the contract.

    The series is part of the seed, so a back month has its own drift rather
    than a scaled copy of the near month's — two contracts on one underlying
    really do move their books independently, and a board where every series
    classified into the same build-up quadrant would teach the page nothing.
    """
    suffix = "" if series == 0 else f":s{series}"
    return Random(f"oi:{instrument.value}:{session_date.isoformat()}{suffix}")  # noqa: S311


def previous_open_interest(
    instrument: InstrumentSymbol, session_date: date, *, series: int = 0
) -> int:
    """Yesterday's close, which is where today's build-up is measured from."""
    drawn = _OI_BASE_LOTS + int(
        _oi_seed(instrument, session_date, series).random() * _OI_SPREAD_LOTS
    )
    return max(1, int(drawn * _liquidity(series)))


def open_interest_at(instrument: InstrumentSymbol, moment: datetime, *, series: int = 0) -> int:
    """Open interest now.

    Drifts away from yesterday's close as the session runs, by a per-instrument
    factor in roughly +/-12%. The sign is independent of the price walk, which
    is the point: an instrument whose price rises while OI falls has to be able
    to come out as short covering rather than a long buildup.

    Before the open the drift is zero, so every contract sits flat at
    yesterday's figure and classifies as neutral — which is the honest answer
    for a market that has not traded yet.
    """
    local = in_ist(moment)
    session_date = local.date()
    previous = previous_open_interest(instrument, session_date, series=series)

    rng = _oi_seed(instrument, session_date, series)
    rng.random()  # consume the draw that set the base, so the drift differs
    full_day_drift = (rng.random() - 0.5) * 0.24

    minutes = local.hour * 60 + local.minute
    elapsed = min(max((minutes - _OPEN_MINUTES) / _SESSION_MINUTES, 0.0), 1.0)
    return max(1, int(previous * (1 + full_day_drift * elapsed)))


def in_ist(moment: datetime) -> datetime:
    """The moment in exchange-local time.

    Load-bearing. The session bounds below are IST wall-clock minutes, and the
    clock feeding this is UTC — comparing the two directly shifted the whole
    drift window by five and a half hours, so open interest sat frozen at
    yesterday's close for the entire Indian trading day and every contract
    classified as neutral.
    """
    aware = moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    return aware.astimezone(IST)


# 09:15 IST in minutes, and the length of the derivatives session.
_OPEN_MINUTES = 9 * 60 + 15
_SESSION_MINUTES = 6 * 60 + 25


def build_futures_quote(
    instrument: InstrumentSymbol,
    moment: datetime,
    *,
    contract: str,
    expiry: date,
    series: int = 0,
) -> FuturesQuote:
    spot = spot_price(instrument, moment)
    # Carry compounds with time to expiry, so each further series trades at a
    # wider premium to spot. Without this the three contracts would print the
    # same price under three different dates, which no futures board does.
    price = (spot * (Decimal(1) + _FUTURES_BASIS * (series + 1))).quantize(Decimal("0.01"))
    base = base_level(instrument)
    change = (price - base).quantize(Decimal("0.01"))
    change_percent = ((change / base) * Decimal(100)).quantize(Decimal("0.01"))

    # Deterministic day range, keyed to the minute like the spot. Volume is
    # per instrument: a single shared formula gave all 210 contracts the same
    # figure, which made the column pure noise on the movers board.
    swing = (price * _SWING_PERCENT).quantize(Decimal("0.01"))
    # Turnover thins out down the curve exactly as the book does.
    liquidity = _liquidity(series)
    volume = max(1, int(volume_at(instrument, moment) * liquidity))

    # The open sits inside the day's range. A deterministic slice of instruments
    # open exactly on the low or the high so the O=L / O=H badge has something
    # to show; the rest open somewhere in between, as most really do.
    high = (price + swing).quantize(Decimal("0.01"))
    low = (price - swing).quantize(Decimal("0.01"))
    edge = _oi_seed(instrument, moment.date(), series).random()
    if edge < _OPENS_ON_LOW_BELOW:
        day_open = low
    elif edge > _OPENS_ON_HIGH_ABOVE:
        day_open = high
    else:
        day_open = price

    return FuturesQuote(
        instrument=instrument,
        contract=contract,
        expiry=expiry.isoformat(),
        price=price,
        change=change,
        change_percent=change_percent,
        volume=volume,
        day_high=high,
        day_low=low,
        open_interest=open_interest_at(instrument, moment, series=series),
        previous_open_interest=previous_open_interest(instrument, moment.date(), series=series),
        previous_close=base,
        day_open=day_open,
        # The live path has no previous-volume field, but the mock can supply
        # one so the Vol % column is exercised in development rather than being
        # permanently blank and untested.
        previous_volume=max(1, int(previous_volume_at(instrument, moment) * liquidity)),
        provenance=Provenance(source=DataSource.MOCK, fetched_at=moment),
    )
