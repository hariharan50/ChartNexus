"""What the signals context needs from the outside world, and nothing more.

Two ports, both satisfied by ``infrastructure`` adapters so this context never
imports ``options_analytics`` or ``market_data``:

* ``MarketReadPort`` — hands the skills one assembled ``MarketSnapshot``. The
  adapter that fills it does all the cross-context fetching and the
  worst-provenance merge; the domain only ever sees plain numbers.
* ``GuidanceRepositoryPort`` — persists a decision when it changes and reads the
  history back, so the console can show how the call has evolved through the day.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from marketcompass.contexts.signals.domain.ensemble import ModelArtifact
from marketcompass.contexts.signals.domain.inputs import MarketSnapshot
from marketcompass.contexts.signals.domain.models import Decision, Guidance, Provenance
from marketcompass.shared_kernel.types.identifiers import TenantId


class MarketReadPort(Protocol):
    """Assembles everything the engine needs for one instrument."""

    async def read(self, tenant_id: TenantId, symbol: str) -> MarketSnapshot: ...


class ModelPort(Protocol):
    """Supplies the calibrated model artifact (weights + calibration per horizon).

    An infrastructure adapter loads the fitted artifact from disk when present,
    else the hand-set default — so the engine always has weights to run with.
    """

    def artifact(self) -> ModelArtifact: ...


@dataclass(frozen=True, slots=True)
class GuidanceRecord:
    """A past decision, thin enough to render a history strip without the whole
    factor breakdown."""

    generated_at: datetime
    symbol: str
    decision: Decision
    confidence: int
    score: float
    provenance: Provenance


class GuidanceRepositoryPort(Protocol):
    """Stores decisions and reads them back. Implementations decide storage."""

    async def latest(self, tenant_id: TenantId, symbol: str) -> GuidanceRecord | None: ...

    async def save(self, tenant_id: TenantId, guidance: Guidance) -> GuidanceRecord: ...

    async def history(
        self, tenant_id: TenantId, symbol: str, *, limit: int
    ) -> tuple[GuidanceRecord, ...]: ...
