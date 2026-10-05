"""Report opt-in use cases — the scheduled daily report spends the owner's LLM
tokens, so it is off by default and enabled explicitly (mirrors HUGIN/MME100)."""

from __future__ import annotations

from chartnexus.contexts.report.application.ports import EnrollmentStorePort
from chartnexus.shared_kernel.types.identifiers import TenantId


class GetReportEnrollment:
    def __init__(self, store: EnrollmentStorePort) -> None:
        self._store = store

    async def __call__(self, tenant_id: TenantId) -> bool:
        return await self._store.is_enabled(tenant_id)


class SetReportEnrollment:
    def __init__(self, store: EnrollmentStorePort) -> None:
        self._store = store

    async def __call__(self, tenant_id: TenantId, *, enabled: bool) -> bool:
        await self._store.set_enabled(tenant_id, enabled)
        return enabled
