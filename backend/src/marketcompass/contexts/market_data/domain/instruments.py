"""Canonical instrument identity.

The rest of the application only ever says ``NIFTY``. Broker-specific strings
like ``NSE:NIFTY50-INDEX`` exist solely inside a provider adapter — if one leaks
past this boundary, swapping brokers stops being a local change.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from marketcompass.shared_kernel.domain.errors import ValidationError


class InstrumentSymbol(StrEnum):
    """Indices MarketCompass covers."""

    NIFTY = "NIFTY"
    BANKNIFTY = "BANKNIFTY"
    SENSEX = "SENSEX"

    @classmethod
    def parse(cls, raw: str) -> InstrumentSymbol:
        try:
            return cls(str(raw or "").strip().upper())
        except ValueError as exc:
            supported = ", ".join(item.value for item in cls)
            raise ValidationError(
                f"Unknown instrument. Supported: {supported}.", field="instrument"
            ) from exc

    @property
    def exchange(self) -> str:
        return "BSE" if self is InstrumentSymbol.SENSEX else "NSE"


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
