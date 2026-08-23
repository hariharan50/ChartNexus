"""The MME100 pre-market worker loop, shared by every caller that runs it.

Lives in entrypoints — not infrastructure — because it wires a ``Container`` (a
composition root), which adapters may not import. Two entry points drive the exact
same loop so they cannot drift:

* the standalone ``marketcompass-mme100`` process (:mod:`entrypoints.main_mme100`),
  what a deployed environment runs; and
* a background task the API starts in its lifespan **in local development only**,
  so a developer running just the API still gets the morning briefing.

Unlike HUGIN's hourly cadence, MME100 fires **once per trading day** at the
configured pre-market time. Each run enumerates enrolled tenants, builds each
tenant's agent from its owner's key, and writes one briefing per tenant covering
the configured instruments. A bad tenant is logged and swallowed: the loop must
outlive any single failure.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime

from marketcompass.bootstrap.container import Container
from marketcompass.bootstrap.settings import Mme100Settings, Settings
from marketcompass.contexts.messaging.application.deliver import DeliverText
from marketcompass.contexts.mme100.application.ports import BriefingStorePort, TenantDirectoryPort
from marketcompass.contexts.mme100.application.run_briefing import RunMme100Briefing
from marketcompass.contexts.mme100.domain.briefing import Briefing
from marketcompass.contexts.mme100.domain.schedule import next_briefing_wake, parse_hhmm
from marketcompass.infrastructure.messaging.build_messaging import build_text_delivery
from marketcompass.infrastructure.mme100.build_mme100 import (
    build_mme100_briefing_store,
    build_mme100_directory,
    build_mme100_worker_agent,
)
from marketcompass.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)

_DELIVERY_SOURCE = "mme100_briefing"


async def run_mme100_loop(
    container: Container,
    settings: Settings,
    *,
    stop: asyncio.Event,
) -> None:
    """Run the MME100 pre-market briefing on its daily cadence until ``stop`` is set."""
    mme100 = settings.mme100
    if not mme100.enabled:
        log.info("mme100_loop_disabled")
        return

    briefing_time = parse_hhmm(mme100.briefing_time_ist)
    directory = build_mme100_directory(container)
    store = build_mme100_briefing_store(container)
    # Reuse the messaging context's delivery entry point to push each briefing to
    # the owner's connected channels (Telegram). Composed here in the entrypoint so
    # the mme100 and messaging contexts never import each other.
    deliver = build_text_delivery(container)
    log.info(
        "mme100_loop_starting",
        briefing_time_ist=mme100.briefing_time_ist,
        instruments=list(mme100.instruments),
    )
    try:
        while not stop.is_set():
            now = datetime.now(UTC)
            wake = next_briefing_wake(now, briefing_time)
            delay = max(1.0, (wake - now).total_seconds())
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=delay)
            if stop.is_set():
                break
            await _run_tick(container, directory, store, deliver, mme100, tick_at=datetime.now(UTC))
    finally:
        log.info("mme100_loop_stopping")


async def _run_tick(
    container: Container,
    directory: TenantDirectoryPort,
    store: BriefingStorePort,
    deliver: DeliverText,
    mme100: Mme100Settings,
    *,
    tick_at: datetime,
) -> None:
    """One morning's pass over enrolled tenants. Never propagates — the loop survives."""
    instruments = tuple(mme100.instruments)

    try:
        tenants = await directory.enrolled_tenants()
    except Exception as exc:
        log.error("mme100_tick_directory_failed", error=repr(exc))
        return

    written = 0
    delivered = 0
    for tenant in tenants[: mme100.max_tenants_per_tick]:
        result: Briefing | None = None
        try:
            # One committing session for the whole tenant's briefing: the agent
            # calls tools ad hoc across all instruments, so the session must stay
            # open for the entire run (write-through caches persist on commit).
            async with container.database.session() as session:
                agent = await build_mme100_worker_agent(
                    container, session, tenant.owner_user_id
                )
                if not agent.available:
                    continue
                briefing = RunMme100Briefing(
                    agent=agent, store=store, instruments=instruments
                )
                result = await briefing(tenant.tenant_id, tick_at=tick_at)
                if result is not None:
                    written += 1
        except Exception as exc:
            log.warning(
                "mme100_tenant_briefing_failed",
                tenant_id=str(tenant.tenant_id),
                error=repr(exc),
            )
            continue

        # Deliver after the DB session closes — DeliverText owns its own sessions
        # and does HTTP. Delivery failure must never affect the stored briefing.
        if result is not None:
            try:
                count = await deliver(
                    tenant.owner_user_id,
                    format_briefing_text(result),
                    source=_DELIVERY_SOURCE,
                )
                delivered += count
            except Exception as exc:  # defensive — DeliverText already swallows
                log.warning(
                    "mme100_briefing_delivery_failed",
                    tenant_id=str(tenant.tenant_id),
                    error=repr(exc),
                )

    log.info(
        "mme100_tick",
        tenants=len(tenants),
        written=written,
        delivered=delivered,
        tick_at=tick_at.isoformat(),
    )


def format_briefing_text(briefing: Briefing) -> str:
    """Render a stored briefing as plain text suitable for a chat channel.

    The briefing markdown uses ``#``/``**``/``---``; chat channels send with no
    parse mode, so those would render literally. Strip them to clean text, keep
    bullets, and add a dated header.
    """
    header = f"📊 MME100 Pre-Market Briefing — {briefing.trading_day.isoformat()}"
    body_lines: list[str] = []
    for raw in briefing.markdown.split("\n"):
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("#"):
            line = stripped.lstrip("#").strip()
        elif stripped.startswith("---") and set(stripped) == {"-"}:
            line = "———"  # a markdown horizontal rule → a short divider
        line = line.replace("**", "").replace("__", "")
        body_lines.append(line)
    if briefing.source == "mock":
        body_lines.append("\n(Data was simulated — illustrative only.)")
    return f"{header}\n\n" + "\n".join(body_lines).strip()
