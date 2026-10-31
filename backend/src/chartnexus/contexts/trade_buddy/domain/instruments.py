"""The instruments Trade Buddy watches, by their canonical names.

Canonical (``NIFTY``), never the broker string (``NSE:NIFTY50-INDEX``). This
module previously keyed everything on the broker form, which was wrong twice
over: it diverged from every other page in the terminal, and it does not
generalise. ``infrastructure/brokers/fyers/symbol_mapper.py`` says why:

    "the index root is not even derivable from the canonical name
    (``BANKNIFTY`` maps to ``NIFTYBANK``)"

So a second instrument could not have been added by pattern — guessing
``NSE:BANKNIFTY-INDEX`` would simply have returned nothing. Translation belongs
at the adapter boundary, where the catalog lookup lives, and only the Fyers
socket ever sees a broker symbol.

Indices only, by decision. The watchlist is derived from which instruments have
levels marked, so a fourth is a marked level set rather than a code change —
but stock underlyings would additionally need a cap on concurrent watches and
halt handling (a circuit halt reads as a dead feed to the staleness watchdog),
and neither is built.
"""

from __future__ import annotations

#: The three indices the page offers, in the order it shows them.
WATCHABLE: tuple[str, ...] = ("NIFTY", "BANKNIFTY", "SENSEX")

DEFAULT_SYMBOL = "NIFTY"


def normalise(symbol: str) -> str:
    """Canonical form of a user- or URL-supplied symbol."""
    return symbol.strip().upper()


def is_watchable(symbol: str) -> bool:
    return normalise(symbol) in WATCHABLE
