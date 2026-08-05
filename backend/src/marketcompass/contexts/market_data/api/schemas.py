"""Wire contract for market data.

Every payload carries ``source`` and ``age_seconds``. A client that ignores
them will render cached or simulated numbers as though they were live, so they
are required fields rather than optional metadata.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from marketcompass.contexts.market_data.domain.market_data import (
    ExpiryList,
    FuturesQuote,
    MarketStatus,
    OptionChain,
    OptionQuote,
    Provenance,
    Quote,
    StrikeRow,
)


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProvenanceResponse(_Schema):
    source: str
    """``live``, ``cached``, or ``mock``."""

    fetched_at: datetime
    age_seconds: float
    is_stale: bool

    @classmethod
    def of(cls, provenance: Provenance) -> ProvenanceResponse:
        return cls(
            source=provenance.source.value,
            fetched_at=provenance.fetched_at,
            age_seconds=round(provenance.age_seconds, 3),
            is_stale=provenance.is_stale,
        )


class QuoteResponse(_Schema):
    instrument: str
    price: Decimal
    change: Decimal | None
    change_percent: Decimal | None
    provenance: ProvenanceResponse

    @classmethod
    def of(cls, quote: Quote) -> QuoteResponse:
        return cls(
            instrument=quote.instrument.value,
            price=quote.price,
            change=quote.change,
            change_percent=quote.change_percent,
            provenance=ProvenanceResponse.of(quote.provenance),
        )


class FuturesQuoteResponse(_Schema):
    instrument: str
    contract: str
    expiry: str
    price: Decimal
    change: Decimal | None
    change_percent: Decimal | None
    volume: int
    day_high: Decimal | None
    day_low: Decimal | None
    provenance: ProvenanceResponse

    @classmethod
    def of(cls, quote: FuturesQuote) -> FuturesQuoteResponse:
        return cls(
            instrument=quote.instrument.value,
            contract=quote.contract,
            expiry=quote.expiry,
            price=quote.price,
            change=quote.change,
            change_percent=quote.change_percent,
            volume=quote.volume,
            day_high=quote.day_high,
            day_low=quote.day_low,
            provenance=ProvenanceResponse.of(quote.provenance),
        )


class OptionQuoteResponse(_Schema):
    ltp: Decimal
    oi: int
    oi_change: int
    volume: int
    iv: Decimal | None
    bid: Decimal | None
    ask: Decimal | None
    delta: Decimal | None

    @classmethod
    def of(cls, quote: OptionQuote) -> OptionQuoteResponse:
        return cls(
            ltp=quote.last_price,
            oi=quote.open_interest,
            oi_change=quote.open_interest_change,
            volume=quote.volume,
            iv=quote.implied_volatility,
            bid=quote.bid,
            ask=quote.ask,
            delta=quote.delta,
        )


class StrikeResponse(_Schema):
    strike: Decimal
    ce: OptionQuoteResponse | None
    pe: OptionQuoteResponse | None

    @classmethod
    def of(cls, row: StrikeRow) -> StrikeResponse:
        return cls(
            strike=row.strike,
            ce=OptionQuoteResponse.of(row.call) if row.call else None,
            pe=OptionQuoteResponse.of(row.put) if row.put else None,
        )


class OptionChainResponse(_Schema):
    instrument: str
    expiry: str
    expiries: tuple[str, ...]
    spot_price: Decimal
    atm_strike: Decimal | None
    pcr: Decimal | None
    lot_size: int | None
    change_percent: Decimal | None
    future_price: Decimal | None
    india_vix: Decimal | None
    india_vix_change_percent: Decimal | None
    iv_percentile: Decimal | None
    total_call_oi: int
    total_put_oi: int
    strikes: tuple[StrikeResponse, ...]
    provenance: ProvenanceResponse

    @classmethod
    def of(cls, chain: OptionChain) -> OptionChainResponse:
        return cls(
            instrument=chain.instrument.value,
            expiry=chain.expiry,
            expiries=chain.expiries,
            spot_price=chain.spot_price,
            atm_strike=chain.atm_strike,
            pcr=chain.put_call_ratio,
            lot_size=chain.lot_size,
            change_percent=chain.change_percent,
            future_price=chain.future_price,
            india_vix=chain.india_vix,
            india_vix_change_percent=chain.india_vix_change_percent,
            iv_percentile=chain.iv_percentile,
            total_call_oi=chain.total_call_open_interest,
            total_put_oi=chain.total_put_open_interest,
            strikes=tuple(StrikeResponse.of(row) for row in chain.strikes),
            provenance=ProvenanceResponse.of(chain.provenance),
        )


class ExpiriesResponse(_Schema):
    instrument: str
    expiries: tuple[str, ...]
    provenance: ProvenanceResponse

    @classmethod
    def of(cls, expiries: ExpiryList) -> ExpiriesResponse:
        return cls(
            instrument=expiries.instrument.value,
            expiries=expiries.expiries,
            provenance=ProvenanceResponse.of(expiries.provenance),
        )


class MarketStatusResponse(_Schema):
    is_open: bool
    session_date: str
    time_ist: str
    provider: str
    connected: bool
    source: str
    market_open: str
    market_close: str

    @classmethod
    def of(cls, status: MarketStatus) -> MarketStatusResponse:
        return cls(
            is_open=status.is_open,
            session_date=status.session_date,
            time_ist=status.time_ist,
            provider=status.provider,
            connected=status.connected,
            source=status.source.value,
            market_open=status.market_open,
            market_close=status.market_close,
        )
