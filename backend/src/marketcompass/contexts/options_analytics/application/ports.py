"""Ports the Open Interest use case depends on.

Both are satisfied by infrastructure adapters, keeping this context free of any
import of ``market_data`` or the persistence layer.

* ``ChainProvider`` yields a live option chain (rows + spot + contract meta).
* ``SnapshotReader`` yields stored intraday chains. There is no writer for these
  yet, so the shipped adapter returns nothing and the service serves the live
  tier; when ingestion lands, the intraday tier activates with no service change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

from marketcompass.contexts.options_analytics.domain.oi_math import ChainRow
from marketcompass.shared_kernel.types.identifiers import TenantId


@dataclass(frozen=True, slots=True)
class ProviderChain:
    """A live chain plus the contract metadata the payload needs."""

    rows: tuple[ChainRow, ...]
    spot: float | None
    lot_size: int | None = None
    expiry: str | None = None


@dataclass(frozen=True, slots=True)
class ChainSnapshot:
    """One stored option-chain observation for a tenant/symbol at a point in time.

    ``captured_at`` is naive-UTC as stored in the database; the service attaches
    the timezone on read.
    """

    captured_at: datetime
    rows: tuple[ChainRow, ...] = field(default_factory=tuple)


@runtime_checkable
class ChainProvider(Protocol):
    async def fetch(self, tenant_id: TenantId, symbol: str) -> ProviderChain: ...


@runtime_checkable
class SnapshotReader(Protocol):
    """Reads stored intraday snapshots. Never raises on absence — returns empty."""

    async def latest_in_session(
        self, tenant_id: TenantId, symbol: str, *, now_utc: datetime
    ) -> ChainSnapshot | None: ...

    async def day_snapshots(
        self, tenant_id: TenantId, symbol: str, *, trade_date_utc: datetime
    ) -> list[ChainSnapshot]: ...
