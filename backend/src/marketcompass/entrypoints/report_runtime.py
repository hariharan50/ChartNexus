"""The daily-report worker loop, shared by the standalone process and the API.

Once each trading morning (default 08:35 IST — just after the MME100 briefing at
08:30, so it can reuse it) it enumerates enrolled tenants, generates the report
for the owner's key per configured instrument, and delivers the PDF to the
owner's connected channels. Swallow-and-survive per tenant: the loop outlives any
single failure.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime

from marketcompass.bootstrap.container import Container
from marketcompass.bootstrap.settings import ReportSettings, Settings
from marketcompass.contexts.messaging.application.deliver import DeliverDocument
from marketcompass.contexts.mme100.domain.schedule import next_briefing_wake, parse_hhmm
from marketcompass.contexts.report.application.ports import TenantDirectoryPort
from marketcompass.infrastructure.messaging.build_messaging import build_document_delivery
from marketcompass.infrastructure.observability.structured_logging import get_logger
from marketcompass.infrastructure.report.build_report import (
    build_report_directory,
    build_report_generator,
)

log = get_logger(__name__)

_SOURCE = "daily_report"


async def run_report_loop(container: Container, settings: Settings, *, stop: asyncio.Event) -> None:
    report = settings.report
    if not report.enabled:
        log.info("report_loop_disabled")
        return

    report_time = parse_hhmm(report.report_time_ist)
    directory = build_report_directory(container)
    deliver = build_document_delivery(container)
    log.info(
        "report_loop_starting",
        report_time_ist=report.report_time_ist,
        instruments=list(report.instruments),
    )
    try:
        while not stop.is_set():
            now = datetime.now(UTC)
            wake = next_briefing_wake(now, report_time)
            delay = max(1.0, (wake - now).total_seconds())
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=delay)
            if stop.is_set():
                break
            await _run_tick(container, directory, deliver, report, tick_at=datetime.now(UTC))
    finally:
        log.info("report_loop_stopping")


async def _run_tick(
    container: Container,
    directory: TenantDirectoryPort,
    deliver: DeliverDocument,
    report: ReportSettings,
    *,
    tick_at: datetime,
) -> None:
    instruments = tuple(report.instruments)
    try:
        tenants = await directory.enrolled_tenants()
    except Exception as exc:
        log.error("report_tick_directory_failed", error=repr(exc))
        return

    delivered = 0
    for tenant in tenants[: report.max_tenants_per_tick]:
        try:
            generator = await build_report_generator(container, tenant.owner_user_id)
            for instrument in instruments:
                generated = await generator(tenant.tenant_id, instrument)
                day = generated.report.trading_day.isoformat()
                count = await deliver(
                    tenant.owner_user_id,
                    filename=f"MarketCompass-{instrument}-{day}.pdf",
                    content=generated.pdf,
                    caption=f"MarketCompass daily report - {instrument} - {day}",
                    source=_SOURCE,
                )
                delivered += count
        except Exception as exc:
            log.warning(
                "report_tenant_failed", tenant_id=str(tenant.tenant_id), error=repr(exc)
            )
            continue

    log.info("report_tick", tenants=len(tenants), delivered=delivered, tick_at=tick_at.isoformat())
