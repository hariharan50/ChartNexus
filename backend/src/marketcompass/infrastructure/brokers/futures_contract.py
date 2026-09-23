"""Which futures contract is the front month, and what is it called.

Index futures trade as monthly series that expire on the last Thursday of their
month; the near-month contract is the one to show until its expiry passes, after
which the next month becomes the front month.

A contract is addressed by **series index** rather than by date — 0 is the
near month, 1 the next, 2 the far — because the dates themselves do not agree
across the universe: NSE and BSE settle on different days, and a
holiday-shifted contract differs from its neighbours. One date could therefore
never name "the same contract" for every row on a board, and a series index
always can. :func:`expiries_for` turns an index back into the date to show.

Two ways to find the front month live here:

* :func:`resolve_front_month` reads it off the broker's own expiry list. Expiry
  days move for holidays and have shifted by exchange circular, so a
  broker-supplied date is trusted over anything computed locally.
* :func:`local_front_month` is the fallback for when no expiry list is available
  (the mock, or a broker response that omitted it). It computes the last
  Thursday and is deliberately the second choice.

Only the *month and year* of the returned date reach the symbol, so a
holiday-shifted day never changes which contract is priced.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.infrastructure.catalog import registry

_THURSDAY = 3  # date.weekday(): Monday=0 … Sunday=6
_DECEMBER = 12

_MONTHS = (
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
)


def last_thursday(year: int, month: int) -> date:
    """The last Thursday of ``month`` — the standard monthly expiry day."""
    last_day = date(year, month, calendar.monthrange(year, month)[1])
    return last_day - timedelta(days=(last_day.weekday() - _THURSDAY) % 7)


def _add_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == _DECEMBER else (year, month + 1)


def local_front_month(today: date) -> date:
    """Front-month expiry from the calendar alone.

    **A fallback, and a poor one.** It assumes the last Thursday, which NSE no
    longer uses — September 2026 expires on Tuesday the 29th, not Thursday the
    24th. Between those two dates the guess rolls to October while September
    contracts are still trading, which builds symbols for the wrong series.

    Prefer :func:`front_month_for`, which reads the date the exchange actually
    published. This remains only for the case where the catalog has no entry.
    """
    this_month = last_thursday(today.year, today.month)
    if today <= this_month:
        return this_month
    return last_thursday(*_add_month(today.year, today.month))


def front_month_for(instrument: InstrumentSymbol, today: date) -> date:
    """The front-month expiry for one instrument.

    Taken from the catalog, which carries the exchange's own published expiry
    and is refreshed daily. Falls back to the calendar only when the catalog
    has nothing — a symbol newly listed between syncs.
    """
    row = registry.current().find(instrument)
    if row is not None and row.front_expiry is not None and row.front_expiry >= today:
        return row.front_expiry
    return local_front_month(today)


#: How many monthly series the exchange lists at once — near, next and far.
#: The picker offers exactly these, because a fourth does not trade.
MAX_SERIES = 3


def expiries_for(instrument: InstrumentSymbol, today: date) -> tuple[date, ...]:
    """Every tradeable series for one instrument, nearest first.

    Taken from the catalog, which carries the exchange's own published dates.
    Expired series are dropped rather than returned and skipped by the caller:
    "series 1" has to mean the same contract everywhere, and a list that still
    held yesterday's near month would shift every index behind it.

    Falls back to the calendar when the catalog has nothing — a symbol listed
    between syncs — which is wrong about the *day* but right about the month,
    and only the month reaches the broker symbol.
    """
    row = registry.current().find(instrument)
    listed = tuple(day for day in (row.futures_expiries if row else ()) if day >= today)
    if listed:
        return listed[:MAX_SERIES]
    return _calendar_series(front_month_for(instrument, today))


def _calendar_series(front: date) -> tuple[date, ...]:
    """Near, next and far month computed from the front month.

    The same fallback ``local_front_month`` is, with the same caveat: the day
    is a guess and the month is not. Used only where the catalog is silent.
    """
    series = [front]
    year, month = front.year, front.month
    for _ in range(MAX_SERIES - 1):
        year, month = _add_month(year, month)
        series.append(last_thursday(year, month))
    return tuple(series)


def contract_for(instrument: InstrumentSymbol, today: date, series: int = 0) -> date:
    """The expiry of one instrument's ``series``-th contract, near month first.

    Clamped rather than raising: a page asking for a far month on an
    instrument that lists only two series should show the furthest it has,
    which is what the exchange would tell you, rather than an error.
    """
    listed = expiries_for(instrument, today)
    if not listed:
        return front_month_for(instrument, today)
    return listed[min(max(series, 0), len(listed) - 1)]


def resolve_front_month(expiries: tuple[str, ...], today: date) -> date:
    """Front-month expiry from the broker's expiry list.

    The monthly expiry is the last expiry within each calendar month; the front
    month is the earliest monthly that has not yet passed. Falls back to
    :func:`local_front_month` when the list is empty or unparseable.
    """
    parsed: list[date] = []
    for raw in expiries:
        try:
            parsed.append(date.fromisoformat(raw))
        except (ValueError, TypeError):
            continue

    if not parsed:
        return local_front_month(today)

    # Last expiry per (year, month) — the monthly contract for that month.
    monthly: dict[tuple[int, int], date] = {}
    for d in sorted(parsed):
        monthly[(d.year, d.month)] = d

    fronts = sorted(monthly.values())
    for d in fronts:
        if d >= today:
            return d
    return fronts[-1]


def to_futures_symbol(instrument: InstrumentSymbol, contract: date) -> str:
    """Broker symbol for a contract, e.g. ``NSE:NIFTY25AUGFUT``.

    Only the month and year of ``contract`` are encoded, so the exact expiry day
    never matters to which series this names.
    """
    # Root and exchange both come from the catalog: the futures root is
    # distinct from the spot symbol (``NSE:NIFTY50-INDEX`` spot but
    # ``NSE:NIFTY26SEPFUT`` future), and the exchange is per-instrument —
    # SENSEX and BANKEX are BSE while everything else is NSE.
    row = registry.current().get(instrument)
    return f"{row.exchange}:{row.futures_root}{contract:%y}{_MONTHS[contract.month - 1]}FUT"
