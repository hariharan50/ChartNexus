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

from chartnexus.contexts.report.application.enrollment import (
    GetReportEnrollment,
    SetReportEnrollment,
)
from chartnexus.contexts.report.application.generate import GenerateReport
from chartnexus.contexts.report.application.ports import TenantDirectoryPort
from chartnexus.infrastructure.agent.langgraph.user_llm import build_user_chat_model
from chartnexus.infrastructure.persistence.postgresql.repositories.report.enrollment_repository import (
    SqlAlchemyReportEnrollmentRepository,
)
from chartnexus.infrastructure.report.briefing_reader import Mme100BriefingReader
from chartnexus.infrastructure.report.data_gatherer import ReportDataGatherer
from chartnexus.infrastructure.report.narrator import Mme100ReportNarrator
from chartnexus.infrastructure.report.pdf_renderer import ReportPdfRenderer
from chartnexus.infrastructure.report.tenant_directory import SqlAlchemyReportTenantDirectory
from chartnexus.infrastructure.time.clock import SystemClock
from chartnexus.infrastructure.transport.http.dependencies import get_container
from chartnexus.shared_kernel.types.identifiers import UserId


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
