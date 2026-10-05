"""MME100's opt-in use cases over a fake store."""

from __future__ import annotations

import uuid

from chartnexus.contexts.mme100.application.enrollment import (
    GetMme100Enrollment,
    SetMme100Enrollment,
)
from chartnexus.shared_kernel.types.identifiers import TenantId

TENANT = TenantId(uuid.uuid4())


class _FakeStore:
    def __init__(self) -> None:
        self._enabled: dict[TenantId, bool] = {}

    async def is_enabled(self, tenant_id: TenantId) -> bool:
        return self._enabled.get(tenant_id, False)

    async def set_enabled(self, tenant_id: TenantId, enabled: bool) -> None:
        self._enabled[tenant_id] = enabled


async def test_absent_tenant_reads_as_disabled() -> None:
    store = _FakeStore()
    assert await GetMme100Enrollment(store)(TENANT) is False


async def test_set_then_get_round_trips() -> None:
    store = _FakeStore()
    assert await SetMme100Enrollment(store)(TENANT, enabled=True) is True
    assert await GetMme100Enrollment(store)(TENANT) is True
    await SetMme100Enrollment(store)(TENANT, enabled=False)
    assert await GetMme100Enrollment(store)(TENANT) is False
