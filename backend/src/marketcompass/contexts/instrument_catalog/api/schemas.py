"""Wire shapes for the instrument catalog."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from marketcompass.contexts.instrument_catalog.domain.instrument import Instrument


class InstrumentResponse(BaseModel):
    """One catalog row.

    Contract geometry (lot size, tick, strike step) is included because the
    picker shows it and the charts need it to label an axis — not because the
    client should compute prices from it.
    """

    model_config = ConfigDict(from_attributes=True)

    symbol: str = Field(description="Canonical symbol, e.g. NIFTY or RELIANCE")
    kind: str = Field(description="index or stock")
    name: str
    exchange: str
    lot_size: int
    tick_size: Decimal
    strike_step: Decimal | None = None
    isin: str | None = None
    sector: str | None = None
    indices: list[str] = Field(default_factory=list)

    @classmethod
    def of(cls, instrument: Instrument) -> InstrumentResponse:
        return cls(
            symbol=instrument.symbol,
            kind=instrument.kind.value,
            name=instrument.name,
            exchange=instrument.exchange,
            lot_size=instrument.lot_size,
            tick_size=instrument.tick_size,
            strike_step=instrument.strike_step,
            isin=instrument.isin,
            sector=instrument.sector,
            indices=list(instrument.indices),
        )


class InstrumentListResponse(BaseModel):
    """The catalog, indices first then alphabetical — the order to render in."""

    instruments: list[InstrumentResponse]
    count: int

    @classmethod
    def of(cls, instruments: list[Instrument]) -> InstrumentListResponse:
        rows = [InstrumentResponse.of(instrument) for instrument in instruments]
        return cls(instruments=rows, count=len(rows))
