"""GenerateReport orchestration, the narrator fallback, and a real PDF render."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from marketcompass.contexts.report.application.generate import GenerateReport
from marketcompass.contexts.report.application.ports import ReportInputs
from marketcompass.contexts.report.domain.report import (
    Candle,
    InstrumentSummary,
    Level,
    MarketReport,
    OptionsSummary,
    OptionStrikeBar,
    ReportNarrative,
    TechnicalRead,
)
from marketcompass.contexts.report.domain.scoring import compute_score
from marketcompass.infrastructure.report.narrator import Mme100ReportNarrator
from marketcompass.infrastructure.report.pdf_renderer import ReportPdfRenderer
from marketcompass.shared_kernel.types.identifiers import TenantId

TENANT = TenantId(uuid.uuid4())


def _inputs(source: str = "live") -> ReportInputs:
    return ReportInputs(
        summary=InstrumentSummary(
            "NIFTY",
            24634.9,
            -19.8,
            -0.08,
            24654.7,
            24728.55,
            24791.3,
            24606.2,
            21743.65,
            26134.7,
            source,
        ),
        technical=TechnicalRead(
            24700.0,
            24800.0,
            42.0,
            24680.0,
            120.0,
            (Level(24768.0, "Call wall"),),
            (Level(24612.0, "Put wall"),),
        ),
        candles=tuple(
            Candle(f"d{i}", 24600 + i, 24650 + i, 24580 + i, 24620 + i) for i in range(30)
        ),
        option_bars=tuple(
            OptionStrikeBar(24400 + i * 100, float(i * 1e5), float((17 - i) * 1e5))
            for i in range(17)
        ),
        options=OptionsSummary(0.62, -0.03, 24700.0, 24650.0, 2.6e8, 1.6e8, 24720.0, 11.37),
        source=source,
    )


class _FakeData:
    def __init__(self, inputs: ReportInputs) -> None:
        self._inputs = inputs

    async def gather(self, tenant_id: TenantId, symbol: str) -> ReportInputs:
        return self._inputs


class _FakeNarrator:
    available = True

    async def narrate(self, symbol, inputs, score, outlook_context):  # type: ignore[no-untyped-def]
        return ReportNarrative("tech", "opts", "sent", f"outlook ctx={bool(outlook_context)}")


class _FakeBriefing:
    def __init__(self, md: str | None) -> None:
        self._md = md

    async def today_markdown(self, tenant_id: TenantId) -> str | None:
        return self._md


class _CapturingRenderer:
    def __init__(self) -> None:
        self.last: MarketReport | None = None

    def render(self, report: MarketReport) -> bytes:
        self.last = report
        return b"%PDF-fake"


class _Clock:
    def now(self) -> datetime:
        return datetime(2026, 9, 30, 3, 0, tzinfo=UTC)  # 08:30 IST


async def test_generate_assembles_report_and_pdf() -> None:
    renderer = _CapturingRenderer()
    gen = GenerateReport(
        data=_FakeData(_inputs()),
        narrator=_FakeNarrator(),
        briefing=_FakeBriefing("today's briefing"),
        renderer=renderer,
        clock=_Clock(),
    )
    out = await gen(TENANT, "NIFTY")
    assert out.pdf == b"%PDF-fake"
    assert out.report.instrument == "NIFTY"
    assert out.report.trading_day == date(2026, 9, 30)
    assert (
        out.report.sentiment.score
        == compute_score(_inputs().summary, _inputs().technical, _inputs().options).score
    )
    # briefing context reached the narrator
    assert "ctx=True" in out.report.narrative.outlook
    assert renderer.last is out.report


async def test_generate_survives_briefing_failure() -> None:
    class _Boom:
        async def today_markdown(self, tenant_id: TenantId) -> str | None:
            raise RuntimeError("boom")

    gen = GenerateReport(
        data=_FakeData(_inputs()),
        narrator=_FakeNarrator(),
        briefing=_Boom(),
        renderer=_CapturingRenderer(),
        clock=_Clock(),
    )
    out = await gen(TENANT, "NIFTY")
    assert "ctx=False" in out.report.narrative.outlook  # None context, no crash


async def test_narrator_fallback_without_model() -> None:
    narrator = Mme100ReportNarrator(None)
    assert narrator.available is False
    inputs = _inputs()
    score = compute_score(inputs.summary, inputs.technical, inputs.options)
    narrative = await narrator.narrate("NIFTY", inputs, score, None)
    assert narrative.technicals and narrative.options and narrative.sentiment and narrative.outlook
    assert str(score.score) in narrative.sentiment


def test_pdf_renderer_produces_a_pdf() -> None:
    inputs = _inputs()
    score = compute_score(inputs.summary, inputs.technical, inputs.options)
    report = MarketReport(
        trading_day=date(2026, 9, 30),
        instrument="NIFTY",
        summary=inputs.summary,
        technical=inputs.technical,
        candles=inputs.candles,
        option_bars=inputs.option_bars,
        options=inputs.options,
        sentiment=score,
        narrative=ReportNarrative("a", "b", "c", "d"),
        source="live",
        generated_at=datetime.now(UTC),
        sources=("NSE", "MarketCompass"),
    )
    pdf = ReportPdfRenderer().render(report)
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 2000


def test_pdf_renderer_handles_empty_data() -> None:
    empty = ReportInputs(
        summary=InstrumentSummary(
            "NIFTY", None, None, None, None, None, None, None, None, None, "mock"
        ),
        technical=TechnicalRead(None, None, None, None, None),
        candles=(),
        option_bars=(),
        options=OptionsSummary(None, None, None, None, None, None, None, None),
        source="mock",
    )
    score = compute_score(empty.summary, empty.technical, empty.options)
    report = MarketReport(
        trading_day=date(2026, 9, 30),
        instrument="NIFTY",
        summary=empty.summary,
        technical=empty.technical,
        candles=empty.candles,
        option_bars=empty.option_bars,
        options=empty.options,
        sentiment=score,
        narrative=ReportNarrative("", "", "", ""),
        source="mock",
        generated_at=datetime.now(UTC),
        sources=("x",),
    )
    pdf = ReportPdfRenderer().render(report)  # must not crash on all-None / empty charts
    assert pdf[:5] == b"%PDF-"
