"""Ports the report use cases depend on.

* ``ReportDataPort`` — gathers every deterministic number/series for an instrument
  (from market_data + options_analytics). Owns its own session (worker-friendly).
* ``ReportNarratorPort`` — the LLM (MME100), which writes ONLY prose from the
  gathered numbers. ``available`` is false with no key → a deterministic fallback
  narrative is used instead.
* ``BriefingReaderPort`` — reads today's stored MME100 briefing to reuse as the
  global-cues / outlook context (avoids a second web search).
* ``ReportRendererPort`` — renders the assembled report to PDF bytes.
* ``EnrollmentStorePort`` / ``TenantDirectoryPort`` — the per-tenant opt-in and
  the worker's tenant list.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from chartnexus.contexts.report.domain.report import (
    Candle,
    InstrumentSummary,
    MarketReport,
    OptionsSummary,
    OptionStrikeBar,
    ReportNarrative,
    SentimentScore,
    TechnicalRead,
)
from chartnexus.shared_kernel.types.identifiers import TenantId, UserId


@dataclass(frozen=True, slots=True)
class ReportInputs:
    """Everything the numbers/charts need — gathered deterministically."""

    summary: InstrumentSummary
    technical: TechnicalRead
    candles: tuple[Candle, ...]
    option_bars: tuple[OptionStrikeBar, ...]
    options: OptionsSummary
    source: str  # "live" | "mock"


@runtime_checkable
class ReportDataPort(Protocol):
    async def gather(self, tenant_id: TenantId, symbol: str) -> ReportInputs:
        """Read every figure for one instrument. Degrades field-by-field on failure."""
        ...


@runtime_checkable
class ReportNarratorPort(Protocol):
    @property
    def available(self) -> bool:
        """True when a model is configured; false → deterministic fallback prose."""
        ...

    async def narrate(
        self,
        symbol: str,
        inputs: ReportInputs,
        score: SentimentScore,
        outlook_context: str | None,
    ) -> ReportNarrative:
        """Write the section prose grounded in the gathered numbers (no new figures)."""
        ...


@runtime_checkable
class BriefingReaderPort(Protocol):
    async def today_markdown(self, tenant_id: TenantId) -> str | None:
        """Today's stored MME100 briefing markdown, if any (reused as outlook context)."""
        ...


@runtime_checkable
class ReportRendererPort(Protocol):
    def render(self, report: MarketReport) -> bytes:
        """Render the assembled report to a PDF document."""
        ...


@dataclass(frozen=True, slots=True)
class EnrolledTenant:
    tenant_id: TenantId
    owner_user_id: UserId


@runtime_checkable
class EnrollmentStorePort(Protocol):
    async def is_enabled(self, tenant_id: TenantId) -> bool: ...

    async def set_enabled(self, tenant_id: TenantId, enabled: bool) -> None: ...


@runtime_checkable
class TenantDirectoryPort(Protocol):
    async def enrolled_tenants(self) -> tuple[EnrolledTenant, ...]: ...


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...
