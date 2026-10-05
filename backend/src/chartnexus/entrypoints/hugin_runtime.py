"""The HUGIN worker loop, shared by every caller that runs it.

Lives in entrypoints — not infrastructure — because it wires a ``Container`` (a
composition root), which adapters may not import. Two entry points drive the exact
same loop so they cannot drift:

* the standalone ``chartnexus-hugin`` process (:mod:`entrypoints.main_hugin`),
  what a deployed environment runs; and
* a background task the API starts in its lifespan **in local development only**,
  so a developer running just the API still sees HUGIN's memory accrue.

Each tick, during the IST session, HUGIN enumerates enrolled tenants, builds each
tenant's reflector from its owner's key, and runs one cycle per instrument. It
sleeps to the next aligned :15 boundary (or the next session open when closed),
waking instantly on ``stop``. A bad tenant or cycle is logged and swallowed: the
loop must outlive any single failure.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime

from chartnexus.bootstrap.container import Container
from chartnexus.bootstrap.settings import HuginSettings, Settings
from chartnexus.contexts.hugin.application.run_cycle import RunHuginCycle
from chartnexus.contexts.hugin.domain.schedule import (
    SessionWindow,
    is_session_open,
    next_wake,
)
from chartnexus.infrastructure.hugin.build_hugin import HuginCycleServices, build_hugin_cycle
from chartnexus.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)


async def run_hugin_loop(
    container: Container,
    settings: Settings,
    *,
    stop: asyncio.Event,
) -> None:
    """Run HUGIN on its cadence until ``stop`` is set."""
    hugin = settings.hugin
    if not hugin.enabled:
        log.info("hugin_loop_disabled")
        return

    window = SessionWindow.from_strings(settings.market.session_open, settings.market.session_close)
    services = build_hugin_cycle(container)
    log.info(
        "hugin_loop_starting",
        interval_seconds=hugin.interval_seconds,
        instruments=list(hugin.instruments),
        align_to_open=hugin.align_to_open,
    )
    try:
        while not stop.is_set():
            now = datetime.now(UTC)
            if is_session_open(now, window):
                await _run_tick(services, hugin, tick_at=now)

            wake = next_wake(now, window, hugin.interval_seconds, align_to_open=hugin.align_to_open)
            delay = max(1.0, (wake - now).total_seconds())
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=delay)
    finally:
        log.info("hugin_loop_stopping")


async def _run_tick(
    services: HuginCycleServices,
    hugin: HuginSettings,
    *,
    tick_at: datetime,
) -> None:
    """One pass over enrolled tenants. Never propagates — the loop must survive."""
    max_tenants = hugin.max_tenants_per_tick
    instruments = tuple(hugin.instruments)
    top_k = hugin.lessons_top_k

    try:
        tenants = await services.directory.enrolled_tenants()
    except Exception as exc:
        log.error("hugin_tick_directory_failed", error=repr(exc))
        return

    persisted = 0
    graded = 0
    for tenant in tenants[:max_tenants]:
        try:
            reflector = await services.reflector_for(tenant.owner_user_id)
        except Exception as exc:
            log.warning(
                "hugin_reflector_build_failed",
                tenant_id=str(tenant.tenant_id),
                error=repr(exc),
            )
            continue
        if not reflector.available:
            continue

        cycle = RunHuginCycle(
            market=services.market,
            reflector=reflector,
            store=services.store,
            lessons_top_k=top_k,
        )
        for instrument in instruments:
            result = await cycle(tenant.tenant_id, instrument, tick_at=tick_at)
            if result.observation is not None:
                persisted += 1
            if result.graded_prior:
                graded += 1

    log.info(
        "hugin_tick",
        tenants=len(tenants),
        persisted=persisted,
        graded=graded,
        tick_at=tick_at.isoformat(),
    )
