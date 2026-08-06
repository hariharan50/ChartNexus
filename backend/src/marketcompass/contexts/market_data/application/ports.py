"""Ports the market-data use cases depend on."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable

from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.contexts.market_data.domain.market_data import (
    CandleInterval,
    CandleSeries,
    ExpiryList,
    FuturesQuote,
    OptionChain,
    Quote,
)
from marketcompass.shared_kernel.types.identifiers import TenantId


@runtime_checkable
class MarketDataProvider(Protocol):
    """A source of market data.

    Implemented by the broker adapter and by the mock. Implementations raise
    ``UpstreamError`` on failure and never substitute synthetic data
    themselves — choosing to degrade is the caller's decision, and it has to be
    visible in the result.
    """

    @property
    def name(self) -> str: ...

    async def get_quote(self, instrument: InstrumentSymbol) -> Quote: ...

    async def get_futures_quote(self, instrument: InstrumentSymbol) -> FuturesQuote: ...

    async def get_option_chain(
        self, instrument: InstrumentSymbol, expiry: str | None = None
    ) -> OptionChain: ...

    async def get_expiries(self, instrument: InstrumentSymbol) -> ExpiryList: ...

    async def get_history(
        self, instrument: InstrumentSymbol, interval: CandleInterval, days: int
    ) -> CandleSeries: ...


@runtime_checkable
class ProviderResolver(Protocol):
    """Chooses the provider for a tenant.

    Built per request from the tenant's stored broker connection, so a
    connect or disconnect takes effect on the very next call without any
    process-wide cache to invalidate.
    """

    async def resolve(self, tenant_id: TenantId) -> MarketDataProvider: ...

    async def is_live(self, tenant_id: TenantId) -> bool:
        """True when the tenant has a working broker connection."""
        ...


@runtime_checkable
class MarketDataCache(Protocol):
    """Two-tier cache behind the degradation ladder.

    ``fresh`` is a normal TTL read. ``last_good`` outlives it deliberately: when
    the broker is down, week-old-but-real data plus a visible staleness marker
    beats synthetic data that looks live.
    """

    async def get_fresh(self, key: str, max_age_seconds: float) -> tuple[str, float] | None: ...

    async def get_last_good(self, key: str) -> tuple[str, float] | None: ...

    async def put(self, key: str, payload: str, *, ttl_seconds: int) -> None: ...

    async def invalidate_prefix(self, prefix: str) -> None: ...


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...


@runtime_checkable
class MarketCalendar(Protocol):
    """Exchange hours, so the UI can explain a flat tape at 4pm."""

    def is_open(self, moment: datetime) -> bool: ...

    @property
    def opens_at(self) -> str: ...

    @property
    def closes_at(self) -> str: ...


@runtime_checkable
class IvHistoryRecorder(Protocol):
    """Tracks today's ATM IV readings so a percentile can be ranked against them.

    Intraday only — there is no cross-day IV history yet (FYERS never quoted
    IV until it was back-solved locally, so the archive has none to draw on).
    The store resets every session.
    """

    async def record_and_rank(self, *, symbol: str, session_date: date, atm_iv: Decimal) -> Decimal:
        """Store ``atm_iv`` and return its percentile rank (0-100) among every
        reading recorded for ``symbol`` so far today, this one included."""
        ...
