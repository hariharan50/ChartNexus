"""What the API monitor needs from the outside world."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from chartnexus.shared_kernel.types.identifiers import TenantId, UserId

Resolution = Literal["minute", "hour"]


@dataclass(frozen=True, slots=True)
class MetricSample:
    """One stored counter: a metric of one call series in one time bucket."""

    at: int  # bucket start, epoch seconds
    provider: str
    endpoint: str
    origin: str
    app: str
    metric: str
    value: int


@dataclass(frozen=True, slots=True)
class RecentCall:
    at_ms: int
    provider: str
    endpoint: str
    origin: str
    app: str
    method: str
    status: int | None
    error: str | None
    elapsed_ms: int


@dataclass(frozen=True, slots=True)
class QuotaUsage:
    broker: str
    app: str  # fingerprint, for filtering
    app_label: str  # masked app id, e.g. "...XY12"
    used_today: int
    daily_limit: int
    window: str  # how the broker's counter is windowed


@dataclass(frozen=True, slots=True)
class AdminEntry:
    email: str
    since: str


class UsageSource(Protocol):
    async def samples(
        self, start_epoch: int, end_epoch: int, resolution: Resolution
    ) -> list[MetricSample]: ...

    async def recent(self, limit: int) -> list[RecentCall]: ...

    async def quotas(self) -> list[QuotaUsage]: ...


class AccessGate(Protocol):
    async def is_admin(self, user_id: UserId) -> bool:
        """Re-read from the database on every call, never trusted from the token."""
        ...

    async def own_apps(self, tenant_id: TenantId) -> frozenset[str]:
        """Fingerprints of the app ids on this tenant's own broker connections."""
        ...


class AdminRoster(Protocol):
    async def admins(self) -> list[AdminEntry]: ...

    async def audit(self, limit: int) -> list[dict[str, str]]: ...
