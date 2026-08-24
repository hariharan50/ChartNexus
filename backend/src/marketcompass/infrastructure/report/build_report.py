"""Composition bridge for the report context — assembles services from the container.

The one module the ``report`` context imports from infrastructure. Provides the
request-side services (on-demand generate + enrollment) and the worker-side
generator/directory used by the scheduled report loop. The narrator runs on the
user's own key (built per user), so a keyless user still gets a report with
deterministic fallback prose.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Request

from marketcompass.contexts.report.application.enrollment import (
    GetReportEnrollment,
    SetReportEnrollment,
)
from marketcompass.contexts.report.application.generate import GenerateReport
from marketcompass.contexts.report.application.ports import TenantDirectoryPort
from marketcompass.infrastructure.agent.langgraph.user_llm import build_user_chat_model
from marketcompass.infrastructure.persistence.postgresql.repositories.report.enrollment_repository import (
    SqlAlchemyReportEnrollmentRepository,
)
from marketcompass.infrastructure.report.briefing_reader import Mme100BriefingReader
from marketcompass.infrastructure.report.data_gatherer import ReportDataGatherer
from marketcompass.infrastructure.report.narrator import Mme100ReportNarrator
from marketcompass.infrastructure.report.pdf_renderer import ReportPdfRenderer
from marketcompass.infrastructure.report.tenant_directory import SqlAlchemyReportTenantDirectory
from marketcompass.infrastructure.time.clock import SystemClock
from marketcompass.infrastructure.transport.http.dependencies import get_container
from marketcompass.shared_kernel.types.identifiers import UserId


@dataclass(slots=True)
class ReportServices:
    generate: GenerateReport
    get_enrollment: GetReportEnrollment
    set_enrollment: SetReportEnrollment


async def _build_generator(container: Any, user_id: UserId) -> GenerateReport:
    async with container.database.read_session() as session:
        model = await build_user_chat_model(container, session, user_id)
    return GenerateReport(
        data=ReportDataGatherer(container),
        narrator=Mme100ReportNarrator(model),
        briefing=Mme100BriefingReader(container),
        renderer=ReportPdfRenderer(),
        clock=SystemClock(),
    )


async def build_report_services(request: Request, user_id: UserId) -> ReportServices:
    container = get_container(request)
    generator = await _build_generator(container, user_id)
    enrollment = SqlAlchemyReportEnrollmentRepository(container.database)
    return ReportServices(
        generate=generator,
        get_enrollment=GetReportEnrollment(enrollment),
        set_enrollment=SetReportEnrollment(enrollment),
    )


async def build_report_generator(container: Any, user_id: UserId) -> GenerateReport:
    """The generator for one tenant's owner — used by the scheduled worker."""
    return await _build_generator(container, user_id)


def build_report_directory(container: Any) -> TenantDirectoryPort:
    return SqlAlchemyReportTenantDirectory(container.database)
