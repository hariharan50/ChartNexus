"""Synthetic price history, aggregated from the one intraday simulation.

Candles are not a separate model. ``session_model`` already owns a seeded
minute-by-minute walk per symbol-day, and a bar is just that walk grouped: open
is the first step in the bucket, close the last, high and low its extremes. Any
second generator here would drift from the spot the rest of the app reports,
which is the exact bug ``session_model``'s docstring exists to describe.

Everything is pure and seeded, so the same request always returns byte-identical
candles.

**Sessions are independent.** Each day's walk starts near the instrument's base
level rather than at the previous day's close, so a multi-day chart oscillates
around that level instead of trending. That is honest for data stamped
``MOCK`` — a synthetic series that looked like a convincing three-month trend
would be worse, not better.
"""

from __future__ import annotations

import random
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from chartnexus.contexts.market_data.domain.instruments import InstrumentSymbol
from chartnexus.contexts.market_data.domain.market_data import (
    Candle,
    CandleInterval,
    CandleSeries,
    DataSource,
    Provenance,
)
from chartnexus.infrastructure.brokers.mock.session_model import (
    MODEL_STEP_SECONDS,
    session_grid,
    spot_track,
)

# Enough that a bar looks traded without implying real turnover.
_BASE_VOLUME = 45_000

# Monday is 0, so anything below this is a weekday.
_SATURDAY = 5


def build_history(
    instrument: InstrumentSymbol,
    interval: CandleInterval,
    days: int,
    now: datetime,
) -> CandleSeries:
    """``days`` trading sessions of bars, oldest first."""
    sessions = _recent_sessions(now.astimezone(UTC).date(), days)

    candles: list[Candle] = []
    for session_date in sessions:
        if interval is CandleInterval.D1:
            daily = _daily_candle(instrument, session_date, now)
            if daily is not None:
                candles.append(daily)
        else:
            candles.extend(_intraday_candles(instrument, session_date, interval, now))

    return CandleSeries(
        instrument=instrument,
        interval=interval,
        candles=tuple(candles),
        provenance=Provenance(source=DataSource.MOCK, fetched_at=now),
    )


def _recent_sessions(today: date, days: int) -> list[date]:
    """The last ``days`` weekdays ending today, oldest first.

    Weekends only — exchange holidays are the market calendar's business, and
    mock data inventing its own holiday list would disagree with it.
    """
    found: list[date] = []
    cursor = today
    while len(found) < days:
        if cursor.weekday() < _SATURDAY:
            found.append(cursor)
        cursor -= timedelta(days=1)
    return list(reversed(found))


def _steps(
    instrument: InstrumentSymbol, session_date: date, now: datetime
) -> tuple[tuple[datetime, ...], tuple[float, ...]]:
    """A session's grid and walk, truncated at ``now``.

    Truncation is what stops today's last bar from being a forecast: without it
    a chart opened at 11:00 would show the whole session to the close.
    """
    grid = session_grid(session_date)
    track = spot_track(instrument, session_date)

    cutoff = sum(1 for stamp in grid if stamp <= now)
    return grid[:cutoff], track[:cutoff]


def _intraday_candles(
    instrument: InstrumentSymbol,
    session_date: date,
    interval: CandleInterval,
    now: datetime,
) -> list[Candle]:
    grid, track = _steps(instrument, session_date, now)
    if not track:
        return []

    per_bar = max(1, interval.seconds // MODEL_STEP_SECONDS)
    bars: list[Candle] = []

    for start in range(0, len(track), per_bar):
        window = track[start : start + per_bar]
        bars.append(
            _candle(
                instrument,
                session_date,
                opened_at=grid[start],
                window=window,
                bucket=start // per_bar,
                # A minute of a session is a fraction of its volume; a whole day
                # is all of it.
                weight=len(window) / len(track),
            )
        )
    return bars


def _daily_candle(instrument: InstrumentSymbol, session_date: date, now: datetime) -> Candle | None:
    grid, track = _steps(instrument, session_date, now)
    if not track:
        return None
    return _candle(instrument, session_date, opened_at=grid[0], window=track, bucket=0, weight=1.0)


def _candle(
    instrument: InstrumentSymbol,
    session_date: date,
    *,
    opened_at: datetime,
    window: tuple[float, ...],
    bucket: int,
    weight: float,
) -> Candle:
    # Seeded on the bar's own identity, so a bar carries the same volume whether
    # it was asked for alone or as part of a longer range.
    rng = random.Random(  # noqa: S311
        f"{instrument.value}:{session_date.isoformat()}:{bucket}:volume"
    )
    volume = int(_BASE_VOLUME * weight * len(window) * rng.uniform(0.6, 1.6))

    return Candle(
        opened_at=opened_at,
        open=_money(window[0]),
        high=_money(max(window)),
        low=_money(min(window)),
        close=_money(window[-1]),
        volume=volume,
    )


def _money(value: float) -> Decimal:
    return Decimal(str(round(value, 2)))
