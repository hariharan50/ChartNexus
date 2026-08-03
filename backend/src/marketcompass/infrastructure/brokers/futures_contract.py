"""Which futures contract is the front month, and what is it called.

Index futures trade as monthly series that expire on the last Thursday of their
month; the near-month contract is the one to show until its expiry passes, after
which the next month becomes the front month.

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

# The tradeable root FYERS uses for each index future — distinct from the spot
# index symbol (``NSE:NIFTY50-INDEX`` spot, ``NSE:NIFTY…FUT`` future).
_FUTURES_ROOT: dict[InstrumentSymbol, str] = {
    InstrumentSymbol.NIFTY: "NIFTY",
    InstrumentSymbol.BANKNIFTY: "BANKNIFTY",
    InstrumentSymbol.SENSEX: "SENSEX",
}


def last_thursday(year: int, month: int) -> date:
    """The last Thursday of ``month`` — the standard monthly expiry day."""
    last_day = date(year, month, calendar.monthrange(year, month)[1])
    return last_day - timedelta(days=(last_day.weekday() - _THURSDAY) % 7)


def _add_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == _DECEMBER else (year, month + 1)


def local_front_month(today: date) -> date:
    """Front-month expiry from the calendar alone (fallback path)."""
    this_month = last_thursday(today.year, today.month)
    if today <= this_month:
        return this_month
    return last_thursday(*_add_month(today.year, today.month))


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
    root = _FUTURES_ROOT[instrument]
    return f"{instrument.exchange}:{root}{contract:%y}{_MONTHS[contract.month - 1]}FUT"
