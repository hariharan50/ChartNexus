"""Canonical instrument identity.

The rest of the application only ever says ``NIFTY`` or ``RELIANCE``.
Broker-specific strings like ``NSE:NIFTY50-INDEX`` exist solely inside a
provider adapter — if one leaks past this boundary, swapping brokers stops
being a local change.

This was a three-member enum until the app grew past three instruments. It is
now an open, validated string, for a reason worth stating: *which* instruments
exist is reference data that the exchange revises by circular several times a
year, and a domain type is the wrong place to encode a fact that changes on
someone else's schedule. The ``instrument_catalog`` context owns that list.

So this type guarantees **shape**, not **existence**. Asking for an instrument
that does not exist fails at the point where something actually needs the
catalog row — the symbol mapper, or the mock generator — which is also the only
layer that can tell you why. The domain stays free of that lookup, and of the
import it would require.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from marketcompass.shared_kernel.domain.errors import ValidationError

# Real tickers reach ten characters (``MIDCPNIFTY``, ``BAJAJ-AUTO``). The cap
# matches the ``String(20)`` symbol columns every snapshot table already uses,
# so anything that validates here fits everywhere it will later be written.
MAX_SYMBOL_LENGTH = 20

# ``M&M``, ``GVT&D``, ``BAJAJ-AUTO`` and ``NAM-INDIA`` are all real NSE
# tickers, so ampersands, hyphens and digits all have to be legal. Anything
# outside this set is a malformed request rather than an unknown instrument.
_ALLOWED_EXTRA = frozenset("&-.")


class InstrumentSymbol(str):
    """A well-formed instrument symbol.

    Subclasses ``str`` deliberately. Every symbol column, cache key, log field
    and broker payload in this codebase already treats an instrument as text,
    and the enum this replaced was a ``StrEnum`` for the same reason. Keeping
    that property means the change is a widening rather than a rewrite.

    Construction validates, so there is no way to hold an ill-formed value:
    ``InstrumentSymbol(" nifty ")`` is ``NIFTY``.
    """

    __slots__ = ()

    def __new__(cls, raw: Any) -> InstrumentSymbol:
        text = str(raw or "").strip().upper()
        if not text:
            raise ValidationError("An instrument is required.", field="instrument")
        if len(text) > MAX_SYMBOL_LENGTH:
            raise ValidationError(
                f"Instrument symbols are at most {MAX_SYMBOL_LENGTH} characters.",
                field="instrument",
            )
        if not all(char.isalnum() or char in _ALLOWED_EXTRA for char in text):
            raise ValidationError(
                "An instrument symbol may only contain letters, digits, & - and .",
                field="instrument",
            )
        return super().__new__(cls, text)

    @classmethod
    def parse(cls, raw: Any) -> InstrumentSymbol:
        """Kept as the name every call site already uses."""
        return cls(raw)

    @property
    def value(self) -> str:
        """The plain string. ``StrEnum`` exposed this and callers still ask."""
        return str(self)

    def __repr__(self) -> str:
        return f"InstrumentSymbol({str(self)!r})"


@dataclass(frozen=True, slots=True)
class InstrumentRef:
    """An instrument plus the lot size needed to price a position in it.

    Lot sizes change by exchange circular; they are supplied by the provider
    rather than hard-coded here.
    """

    symbol: InstrumentSymbol
    lot_size: int

    def __post_init__(self) -> None:
        if self.lot_size <= 0:
            raise ValidationError("lot size must be positive", field="lot_size")
