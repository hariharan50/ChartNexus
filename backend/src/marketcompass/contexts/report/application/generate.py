"""GenerateReport — assemble one instrument's daily report and render it to PDF.

Sequence: gather deterministic numbers → compute the score → pull today's briefing
as outlook context → have the LLM write the section prose → assemble the report →
render to PDF. Returns the domain report (for storage/JSON) and the PDF bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, timedelta, timezone

from marketcompass.contexts.report.application.ports import (
    BriefingReaderPort,
    Clock,
    ReportDataPort,
    ReportNarratorPort,
    ReportRendererPort,
)
from marketcompass.contexts.report.domain.report import MarketReport
from marketcompass.contexts.report.domain.scoring import compute_score
from marketcompass.shared_kernel.types.identifiers import TenantId

_IST = timezone(timedelta(hours=5, minutes=30))

_DEFAULT_SOURCES = (
    "NSE / BSE (via broker feed)",
    "MarketCompass options analytics",
    "Global cues via web search (MME100)",
)


@dataclass(frozen=True, slots=True)
class GeneratedReport:
    report: MarketReport
    pdf: bytes


@dataclass(frozen=True, slots=True)
class GenerateReport:
    data: ReportDataPort
    narrator: ReportNarratorPort
    briefing: BriefingReaderPort
    renderer: ReportRendererPort
    clock: Clock

    @property
    def available(self) -> bool:
        """The report always renders; this reports whether the LLM narrative is on."""
        return self.narrator.available

    async def __call__(self, tenant_id: TenantId, symbol: str) -> GeneratedReport:
        inputs = await self.data.gather(tenant_id, symbol)
        score = compute_score(inputs.summary, inputs.technical, inputs.options)

        outlook_context: str | None = None
        try:
            outlook_context = await self.briefing.today_markdown(tenant_id)
        except Exception:  # briefing is a best-effort enrichment, never fatal
            outlook_context = None

        narrative = await self.narrator.narrate(symbol, inputs, score, outlook_context)

        now = self.clock.now()
        report = MarketReport(
            trading_day=now.astimezone(_IST).date(),
            instrument=symbol,
            summary=inputs.summary,
            technical=inputs.technical,
            candles=inputs.candles,
            option_bars=inputs.option_bars,
            options=inputs.options,
            sentiment=score,
            narrative=narrative,
            source=inputs.source,
            generated_at=now.astimezone(UTC),
            sources=_DEFAULT_SOURCES,
        )
        pdf = self.renderer.render(report)
        return GeneratedReport(report=report, pdf=pdf)
