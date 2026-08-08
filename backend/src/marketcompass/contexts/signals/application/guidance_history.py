"""Read past decisions for one instrument, newest first."""

from __future__ import annotations

from marketcompass.contexts.signals.application.ports import (
    GuidanceRecord,
    GuidanceRepositoryPort,
)
from marketcompass.shared_kernel.types.identifiers import TenantId

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200


class GetGuidanceHistory:
    def __init__(self, *, repository: GuidanceRepositoryPort) -> None:
        self._repository = repository

    async def __call__(
        self, tenant_id: TenantId, symbol: str, *, limit: int = _DEFAULT_LIMIT
    ) -> tuple[GuidanceRecord, ...]:
        capped = max(1, min(limit, _MAX_LIMIT))
        return await self._repository.history(tenant_id, symbol, limit=capped)
