"""MarketReaderPort — HUGIN's hourly market snapshot over the existing tools.

Reuses the *same* read-only toolset HELLA/STRYX reason over
(``build_agent_tools``), so no new market tool is added. Unlike the agents,
HUGIN does not let the model call tools ad hoc: it invokes all nine once, up front,
and hands the collected readings to a single reflection call. The result is a
compact ``{tool_name: reading}`` dict — the same evidence HELLA sees — stored as
the observation's ``readings`` and fed to the judge/reflect step.

The context never imports this: it is wired through ``build_hugin``. Cross-context
and LangChain imports are deferred into the method body, per the bridge rule, so
importing this module stays cheap and adds no static edge.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from chartnexus.contexts.hugin.application.ports import MarketReaderPort
from chartnexus.infrastructure.observability.structured_logging import get_logger
from chartnexus.shared_kernel.types.identifiers import TenantId

log = get_logger(__name__)


class ToolMarketReader:
    """Snapshots the market for one tenant x instrument via the shared agent tools."""

    def __init__(self, container: Any) -> None:
        self._container = container

    async def snapshot(self, tenant_id: TenantId, instrument: str) -> dict[str, Any]:
        from chartnexus.contexts.copilot.domain import skills  # noqa: PLC0415
        from chartnexus.contexts.market_data.api.dependencies import (  # noqa: PLC0415
            build_market_services_from,
        )
        from chartnexus.contexts.options_analytics.api.dependencies import (  # noqa: PLC0415
            build_options_analytics_services_from,
        )
        from chartnexus.infrastructure.agent.langgraph.tools import (  # noqa: PLC0415
            build_agent_tools,
        )

        readings: dict[str, Any] = {
            "_meta": {
                "instrument": instrument,
                "captured_at": datetime.now(UTC).isoformat(),
            }
        }
        # A committing session so any write-through cache the reads populate (e.g.
        # the candle cache) persists, matching how the ingest loop reads.
        async with self._container.database.session() as session:
            market = build_market_services_from(self._container, session)
            options = build_options_analytics_services_from(self._container, session)
            tools = build_agent_tools(tenant_id, market, options)

            for tool in tools:
                args = {} if tool.name == skills.GET_MARKET_STATUS else {"symbol": instrument}
                try:
                    readings[tool.name] = await tool.ainvoke(args)
                except Exception as exc:
                    log.warning(
                        "hugin_snapshot_tool_failed",
                        tool=tool.name,
                        instrument=instrument,
                        error=repr(exc),
                    )
                    readings[tool.name] = f"unavailable ({exc!r})"

        return readings


# Structural check: the adapter satisfies the port.
_: type[MarketReaderPort] = ToolMarketReader
