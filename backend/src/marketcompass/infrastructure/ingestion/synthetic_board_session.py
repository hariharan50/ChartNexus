"""Fabricate a session of futures-board frames.

The sibling of :mod:`synthetic_session`, which does the same for option chains.
Both exist for one reason: on a machine with no broker connected the archive is
empty, and an empty archive makes every intraday page in the app look broken
rather than unconfigured.

Frames come from the same mock simulation the rest of the app reads — the one
price walk in ``mock.session_model`` — so a seeded session agrees with what the
mock provider would have reported at those instants, instead of being a second,
disagreeing invention.

Everything here is stamped ``mock``. Nothing in this module may produce a
``live`` frame; the capture worker is the only writer allowed to do that.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal

from marketcompass.contexts.futures_analytics.application.ports import BoardFrame
from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.infrastructure.brokers.mock.quote_factory import (
    open_interest_at,
    spot_price,
    volume_at,
)
from marketcompass.infrastructure.brokers.mock.session_model import (
    SESSION_CLOSE,
    SESSION_OPEN,
)

_IST = timezone(timedelta(hours=5, minutes=30))

#: Provenance every frame here carries. Never ``live`` — see the module docstring.
MOCK = "mock"

#: The basis the mock futures quote applies over spot, so a seeded frame and a
#: live-mock quote report the same number rather than two plausible ones.
_FUTURES_BASIS = Decimal("1.0008")
_CENTS = Decimal("0.01")


def build_synthetic_board_session(
    *,
    symbol: str,
    session_date: date,
    expiry: str | None,
    interval_seconds: int = 60,
    until: datetime | None = None,
    start: time = SESSION_OPEN,
    end: time = SESSION_CLOSE,
) -> list[BoardFrame]:
    """One frame per interval across the trading session.

    ``until`` clips the run — today's session must not claim captures that have
    not happened yet. A past date gets the whole session, because for that day
    they all did.
    """
    instrument = InstrumentSymbol(symbol)
    step = timedelta(seconds=max(interval_seconds, 1))
    moment = _at(session_date, start)
    close = _at(session_date, end)
    ceiling = min(close, until) if until is not None else close

    frames: list[BoardFrame] = []
    while moment <= ceiling:
        price = spot_price(instrument, moment) * _FUTURES_BASIS
        frames.append(
            BoardFrame(
                symbol=symbol,
                session_date=session_date,
                captured_at=moment,
                price=price.quantize(_CENTS),
                open_interest=open_interest_at(instrument, moment),
                volume=volume_at(instrument, moment),
                expiry=expiry,
                source=MOCK,
            )
        )
        moment += step
    return frames


def _at(session_date: date, clock: time) -> datetime:
    """An exchange-local wall time on a session date, as a UTC instant."""
    return datetime.combine(session_date, clock, tzinfo=_IST).astimezone(UTC)
