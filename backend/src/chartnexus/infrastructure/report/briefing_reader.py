"""Reads today's MME100 briefing to reuse as the report's outlook context.

Reusing the morning briefing's global cues avoids a second web search (the
heaviest token item). Best-effort: returns ``None`` when no briefing exists yet.
Lives in infrastructure, so reaching into the MME100 briefing store is fine.
"""

from __future__ import annotations

from typing import Any

from chartnexus.contexts.report.application.ports import BriefingReaderPort
from chartnexus.infrastructure.persistence.postgresql.repositories.mme100.briefing_repository import (
    SqlAlchemyMme100BriefingRepository,
)
from chartnexus.shared_kernel.types.identifiers import TenantId


class Mme100BriefingReader:
    def __init__(self, container: Any) -> None:
        self._repo = SqlAlchemyMme100BriefingRepository(container.database)

    async def today_markdown(self, tenant_id: TenantId) -> str | None:
        briefing = await self._repo.today(tenant_id)
        return briefing.markdown if briefing is not None else None


# Structural check: the adapter satisfies the port.
_: type[BriefingReaderPort] = Mme100BriefingReader
