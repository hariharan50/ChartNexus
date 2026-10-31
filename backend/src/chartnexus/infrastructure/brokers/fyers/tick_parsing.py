"""Reading a price out of a Fyers tick frame. Pure, and deliberately paranoid.

Split out of ``data_socket.py`` so it carries no ``fyers_apiv3`` import: these
are the functions most worth testing and they should not need the vendor SDK
installed to run. The socket class imports them.

Why this is defensive rather than a single ``message["ltp"]``: the frame shape
varies between litemode and full mode, and the key carrying last price has
differed across SDK releases. Every branch that cannot produce a trustworthy
number returns ``None``, because the engine treating a missing price as a real
one is precisely how a level gets reported broken on a frame that said nothing.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from typing import Any

#: Keys that have carried last-traded price across SDK versions and modes, in
#: the order we trust them. ``ltp`` is litemode's; the rest appear in full mode.
PRICE_KEYS = ("ltp", "last_price", "lp", "LTP", "last_traded_price")

#: Keys that have carried the exchange timestamp. Absent in some litemode frames.
TIME_KEYS = ("last_traded_time", "exch_feed_time", "timestamp", "tt")

SYMBOL_KEYS = ("symbol", "Symbol", "s", "ticker")

#: A sanity window on exchange timestamps. Anything outside it is a clock bug,
#: not a trade, and arrival time is the safer reading.
_MIN_YEAR = 2000
_MAX_YEAR = 2100


def extract_price(message: Any) -> float | None:
    """Last price from a tick frame, or ``None`` if it is not reliably there."""
    if not isinstance(message, dict):
        return None
    for key in PRICE_KEYS:
        raw = message.get(key)
        if raw is None:
            continue
        # Explicitly reject bools: `float(True)` is 1.0, and a flag landing in a
        # price field would become a price of one rupee.
        if isinstance(raw, bool):
            continue
        try:
            price = float(raw)
        except (TypeError, ValueError):
            continue
        # Zero and negatives appear in warm-up and malformed frames. An index is
        # never at zero, so this is a sentinel, not a price.
        if price > 0:
            return price
    return None


def extract_symbol(message: Any) -> str | None:
    if not isinstance(message, dict):
        return None
    for key in SYMBOL_KEYS:
        value = message.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def extract_time(message: Any, *, fallback: datetime) -> datetime:
    """The exchange timestamp if the frame carries a sane one, else ``fallback``.

    Arrival time is the safer default: a wrong exchange timestamp would key the
    daily cap and the session-gap check to the wrong day, and a frame whose
    clock reads 1970 is far more likely than a market that traded then.
    """
    if not isinstance(message, dict):
        return fallback
    for key in TIME_KEYS:
        raw = message.get(key)
        if raw is None or isinstance(raw, bool):
            continue
        try:
            seconds = float(raw)
        except (TypeError, ValueError):
            continue
        if seconds <= 0:
            continue
        with contextlib.suppress(OSError, OverflowError, ValueError):
            moment = datetime.fromtimestamp(seconds, tz=UTC)
            if _MIN_YEAR < moment.year < _MAX_YEAR:
                return moment
    return fallback
