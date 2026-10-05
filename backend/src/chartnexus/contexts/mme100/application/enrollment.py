"""MME100 opt-in use cases.

The autonomous pre-market briefing spends the owner's LLM tokens, so it is off by
default and a tenant turns it on explicitly. These two tiny use cases read and
write that flag through the store port; the worker's tenant directory reads the
same table to decide who to run for.
"""

from __future__ import annotations

from chartnexus.contexts.mme100.application.ports import EnrollmentStorePort
from chartnexus.shared_kernel.types.identifiers import TenantId


class GetMme100Enrollment:
    def __init__(self, store: EnrollmentStorePort) -> None:
        self._store = store

    async def __call__(self, tenant_id: TenantId) -> bool:
        return await self._store.is_enabled(tenant_id)


class SetMme100Enrollment:
    def __init__(self, store: EnrollmentStorePort) -> None:
        self._store = store

    async def __call__(self, tenant_id: TenantId, *, enabled: bool) -> bool:
        await self._store.set_enabled(tenant_id, enabled)
        return enabled
