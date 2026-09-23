"""Renders a ``MarketReport`` to a branded multi-page PDF with fpdf2.

Pure-Python: fpdf2 composes the pages and draws the three charts (candlestick,
OI-by-strike bar, sentiment gauge) with vector primitives — no matplotlib, no
headless browser. Core fonts are latin-1, so text is sanitised (₹ → "Rs", dashes
and arrows normalised, emoji dropped) rather than embedding a TTF.
"""

# The sanitiser map deliberately contains ambiguous unicode (curly quotes, dashes)
# that it normalises to ASCII, so RUF001 is not meaningful in this file.
# ruff: noqa: RUF001
from __future__ import annotations

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from marketcompass.contexts.report.application.ports import ReportRendererPort
from marketcompass.contexts.report.domain.report import (
    Candle,
    MarketReport,
    OptionStrikeBar,
    SentimentScore,
    Stance,
)

# -- palette (RGB) ----------------------------------------------------------
EMERALD = (16, 185, 129)
SKY = (14, 165, 233)
INK = (31, 39, 51)
MUTE = (100, 116, 139)
AMBER = (245, 158, 11)
GREEN = (22, 163, 74)
RED = (220, 38, 38)
LIGHT = (238, 242, 246)
CARD = (247, 249, 251)
WHITE = (255, 255, 255)

_PAGE_W = 210.0
_MARGIN = 16.0
_CONTENT_W = _PAGE_W - 2 * _MARGIN


def _ascii(text: str) -> str:
    """Make text safe for fpdf2 core (latin-1) fonts."""
    replacements = {
        "₹": "Rs ",  # ₹
        "—": "-",
        "–": "-",
        "•": "-",
        "→": "->",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "…": "...",
        "✅": "",
        "⚠": "",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", "ignore").decode("latin-1")


def _money(value: float | None) -> str:
    return "n/a" if value is None else f"Rs {value:,.2f}"


def _num(value: float | None, digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:,.{digits}f}"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.2f}%"


def _lakh(value: float | None) -> str:
    return "n/a" if value is None else f"{value / 100000:,.1f} L"


class ReportPdfRenderer:
    """Implements ``ReportRendererPort`` with fpdf2."""

    def render(self, report: MarketReport) -> bytes:
        pdf = FPDF(unit="mm", format="A4")
        pdf.set_auto_page_break(auto=False)
        pdf.set_title(f"MarketCompass {report.instrument} {report.trading_day.isoformat()}")

        self._page_summary(pdf, report)
        self._page_options(pdf, report)
        self._page_sentiment(pdf, report)
        self._page_outlook(pdf, report)
        self._page_legal(pdf, report)

        out = pdf.output()
        return bytes(out)

    # -- chrome -------------------------------------------------------------

    def _header(self, pdf: FPDF, report: MarketReport, subtitle: str) -> None:
        pdf.add_page()
        # Header band (a two-tone split suggests the app's emerald→sky gradient).
        _fill(pdf, SKY)
        pdf.rect(0, 0, _PAGE_W, 30, "F")
        _fill(pdf, EMERALD)
        pdf.rect(0, 0, _PAGE_W * 0.62, 30, "F")
        # decorative dot
        _fill(pdf, AMBER)
        pdf.ellipse(_PAGE_W - 22, 9, 6, 6, "F")

        pdf.set_xy(_MARGIN, 8)
        pdf.set_text_color(*WHITE)
        pdf.set_font("Helvetica", "B", 20)
        pdf.cell(120, 8, "MME100", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_xy(_MARGIN, 17)
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(120, 5, "MARKET MADE EASY 100%  -  MarketCompass")
        pdf.set_xy(_PAGE_W - 76, 11)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(60, 6, report.trading_day.strftime("%a, %d %b %Y"), align="R")

        pdf.set_xy(_MARGIN, 37)
        pdf.set_text_color(*_darker(EMERALD))
        pdf.set_font("Helvetica", "B", 15)
        pdf.cell(_CONTENT_W, 8, _ascii(subtitle.upper()), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        _fill(pdf, AMBER)
        pdf.rect(_MARGIN, 47, 26, 1.4, "F")
        pdf.set_y(52)

    def _footer(self, pdf: FPDF, page_no: int) -> None:
        pdf.set_draw_color(*LIGHT)
        pdf.set_line_width(0.3)
        pdf.line(_MARGIN, 285, _PAGE_W - _MARGIN, 285)
        pdf.set_xy(_MARGIN, 287)
        pdf.set_text_color(*MUTE)
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(
            _CONTENT_W, 5, f"MarketCompass  |  Not investment advice  |  Page {page_no}", align="C"
        )

    def _bullets(self, pdf: FPDF, text: str, *, height: float) -> None:
        pdf.set_text_color(*INK)
        pdf.set_font("Helvetica", "", 10)
        clean = _ascii(text).strip() or "No commentary available."
        pdf.set_x(_MARGIN)
        pdf.multi_cell(_CONTENT_W, 5.2, clean)
        _ = height

    # -- pages --------------------------------------------------------------

    def _page_summary(self, pdf: FPDF, r: MarketReport) -> None:
        self._header(pdf, r, f"Summary & Technicals - {r.instrument}")
        s = r.summary

        # Summary card
        _fill(pdf, CARD)
        pdf.rect(_MARGIN, 54, _CONTENT_W, 30, "F")
        pdf.set_xy(_MARGIN + 4, 57)
        pdf.set_text_color(*INK)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(60, 8, _ascii(r.instrument))
        pdf.set_font("Helvetica", "B", 18)
        pdf.set_xy(_MARGIN + 60, 56)
        pdf.cell(70, 9, _money(s.ltp), align="R")
        chg_color = GREEN if (s.change or 0) >= 0 else RED
        pdf.set_text_color(*chg_color)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_xy(_MARGIN + 130, 58)
        pdf.cell(_CONTENT_W - 134, 7, f"{_num(s.change)} ({_pct(s.change_pct)})", align="R")

        pdf.set_text_color(*MUTE)
        pdf.set_font("Helvetica", "", 8)
        cells = [
            ("Prev Close", _money(s.prev_close)),
            ("Open", _money(s.day_open)),
            ("Day Range", f"{_num(s.day_low)} - {_num(s.day_high)}"),
            ("52W Range", f"{_num(s.week52_low)} - {_num(s.week52_high)}"),
        ]
        cw = _CONTENT_W / 4
        for i, (label, value) in enumerate(cells):
            x = _MARGIN + i * cw
            pdf.set_xy(x + 4, 70)
            pdf.set_text_color(*MUTE)
            pdf.set_font("Helvetica", "", 8)
            pdf.cell(cw - 4, 4, label, new_x=XPos.LEFT, new_y=YPos.NEXT)
            pdf.set_x(x + 4)
            pdf.set_text_color(*INK)
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(cw - 4, 5, _ascii(value))

        # Candlestick
        pdf.set_y(90)
        self._section_title(pdf, "Price Action (15m)")
        self._candlestick(pdf, r.candles, x=_MARGIN, y=98, w=_CONTENT_W, h=62)

        # Technical commentary + levels
        pdf.set_y(166)
        self._bullets(pdf, r.narrative.technicals, height=26)
        y = max(pdf.get_y() + 3, 196)
        self._levels(pdf, r, y)
        self._footer(pdf, 1)

    def _levels(self, pdf: FPDF, r: MarketReport, y: float) -> None:
        pdf.set_xy(_MARGIN, y)
        pdf.set_text_color(*RED)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(_CONTENT_W / 2, 6, "Key Resistance")
        pdf.set_text_color(*GREEN)
        pdf.cell(_CONTENT_W / 2, 6, "Key Support", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 9)
        rows = max(len(r.technical.resistances), len(r.technical.supports), 1)
        for i in range(rows):
            pdf.set_x(_MARGIN)
            res = r.technical.resistances[i] if i < len(r.technical.resistances) else None
            sup = r.technical.supports[i] if i < len(r.technical.supports) else None
            pdf.set_text_color(*INK)
            pdf.cell(
                _CONTENT_W / 2,
                5,
                _ascii(f"{_num(res.price)} ({res.label})") if res else "-",
            )
            pdf.cell(
                _CONTENT_W / 2,
                5,
                _ascii(f"{_num(sup.price)} ({sup.label})") if sup else "-",
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )

    def _page_options(self, pdf: FPDF, r: MarketReport) -> None:
        self._header(pdf, r, f"Options & PCR - {r.instrument}")
        o = r.options
        self._section_title(pdf, "Open Interest by Strike")
        self._oi_bars(pdf, r.option_bars, x=_MARGIN, y=62, w=_CONTENT_W, h=62)

        # Options summary grid
        pdf.set_y(130)
        cells = [
            ("PCR", _num(o.pcr)),
            ("Max Pain", _num(o.max_pain, 0)),
            ("ATM", _num(o.atm_strike, 0)),
            ("Gamma Flip", _num(o.gamma_flip, 0)),
            ("Total CE OI", _lakh(o.total_call_oi)),
            ("Total PE OI", _lakh(o.total_put_oi)),
            ("India VIX", _num(o.india_vix, 2)),
            ("PCR chg", _num(o.pcr_change)),
        ]
        self._stat_grid(pdf, cells, y=130, cols=4)

        pdf.set_y(158)
        self._section_title(pdf, "Options Read")
        pdf.set_y(166)
        self._bullets(pdf, r.narrative.options, height=100)
        self._footer(pdf, 2)

    def _page_sentiment(self, pdf: FPDF, r: MarketReport) -> None:
        self._header(pdf, r, "Volatility & Sentiment")
        self._section_title(pdf, "MarketCompass Score")
        self._gauge(pdf, r.sentiment, x=_MARGIN, y=64, w=_CONTENT_W)

        pdf.set_y(96)
        self._section_title(pdf, "Signal Breakdown")
        self._signal_cards(pdf, r.sentiment, y=104)

        pdf.set_y(198)
        self._section_title(pdf, "What It Means")
        pdf.set_y(206)
        self._bullets(pdf, r.narrative.sentiment, height=60)
        self._footer(pdf, 3)

    def _page_outlook(self, pdf: FPDF, r: MarketReport) -> None:
        self._header(pdf, r, "Global Cues & Pre-Market Outlook")
        pdf.set_y(56)
        # The outlook is the report's most detailed prose; let it flow onto a
        # continuation page if it runs long rather than overwriting the footer.
        pdf.set_auto_page_break(auto=True, margin=20)
        self._bullets(pdf, r.narrative.outlook, height=210)
        pdf.set_auto_page_break(auto=False)
        self._footer(pdf, 4)

    def _page_legal(self, pdf: FPDF, r: MarketReport) -> None:
        self._header(pdf, r, "Disclaimer & Sources")
        pdf.set_y(58)
        self._section_title(pdf, "Disclaimer")
        pdf.set_y(66)
        self._bullets(
            pdf,
            "This report is for educational and informational purposes only and must not be "
            "treated as investment advice or a recommendation. Market data may change or "
            "contain errors. Consult a SEBI-registered investment adviser before making any "
            "decision. Past performance is not indicative of future results.",
            height=34,
        )
        pdf.set_y(104)
        self._section_title(pdf, "Data Sources")
        pdf.set_y(112)
        self._bullets(pdf, "\n".join(f"- {src}" for src in r.sources), height=30)
        if r.source == "mock":
            pdf.set_y(140)
            pdf.set_text_color(*AMBER)
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_x(_MARGIN)
            pdf.multi_cell(
                _CONTENT_W,
                5,
                "Note: some readings in this report were simulated (mock data) - treat as "
                "illustrative.",
            )
        self._footer(pdf, 5)

    # -- primitives ---------------------------------------------------------

    def _section_title(self, pdf: FPDF, title: str) -> None:
        pdf.set_x(_MARGIN)
        pdf.set_text_color(*_darker(EMERALD))
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(_CONTENT_W, 6, _ascii(title), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def _stat_grid(self, pdf: FPDF, cells: list[tuple[str, str]], *, y: float, cols: int) -> None:
        cw = _CONTENT_W / cols
        ch = 13.0
        for i, (label, value) in enumerate(cells):
            col = i % cols
            row = i // cols
            x = _MARGIN + col * cw
            cy = y + row * ch
            _fill(pdf, CARD)
            pdf.rect(x + 1, cy, cw - 2, ch - 2, "F")
            pdf.set_xy(x + 3, cy + 1.5)
            pdf.set_text_color(*MUTE)
            pdf.set_font("Helvetica", "", 7.5)
            pdf.cell(cw - 5, 4, _ascii(label), new_x=XPos.LEFT, new_y=YPos.NEXT)
            pdf.set_x(x + 3)
            pdf.set_text_color(*INK)
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(cw - 5, 5, _ascii(value))

    def _candlestick(
        self, pdf: FPDF, candles: tuple[Candle, ...], *, x: float, y: float, w: float, h: float
    ) -> None:
        _fill(pdf, CARD)
        pdf.rect(x, y, w, h, "F")
        if not candles:
            _placeholder(pdf, x, y, w, h)
            return
        hi = max(c.high for c in candles)
        lo = min(c.low for c in candles)
        if hi <= lo:
            _placeholder(pdf, x, y, w, h)
            return
        pad = 4.0
        plot_x, plot_y = x + pad, y + pad
        plot_w, plot_h = w - 2 * pad, h - 2 * pad

        def py(price: float) -> float:
            return plot_y + plot_h * (hi - price) / (hi - lo)

        n = len(candles)
        slot = plot_w / n
        body = max(1.0, slot * 0.55)
        for i, c in enumerate(candles):
            cx = plot_x + i * slot + slot / 2
            up = c.close >= c.open
            color = GREEN if up else RED
            pdf.set_draw_color(*color)
            pdf.set_line_width(0.3)
            pdf.line(cx, py(c.high), cx, py(c.low))  # wick
            top = py(max(c.open, c.close))
            bot = py(min(c.open, c.close))
            _fill(pdf, color)
            pdf.rect(cx - body / 2, top, body, max(0.6, bot - top), "F")
        # last price line
        pdf.set_draw_color(*SKY)
        pdf.set_line_width(0.2)
        last_y = py(candles[-1].close)
        _dashed_h(pdf, plot_x, plot_x + plot_w, last_y)

    def _oi_bars(
        self,
        pdf: FPDF,
        bars: tuple[OptionStrikeBar, ...],
        *,
        x: float,
        y: float,
        w: float,
        h: float,
    ) -> None:
        _fill(pdf, CARD)
        pdf.rect(x, y, w, h, "F")
        if not bars:
            _placeholder(pdf, x, y, w, h)
            return
        peak = max((max(b.call_oi, b.put_oi) for b in bars), default=0.0)
        if peak <= 0:
            _placeholder(pdf, x, y, w, h)
            return
        pad = 5.0
        plot_x, plot_y = x + pad, y + pad
        plot_w, plot_h = w - 2 * pad, h - 2 * pad - 4  # leave room for x labels
        n = len(bars)
        slot = plot_w / n
        bw = max(0.8, slot * 0.34)
        for i, b in enumerate(bars):
            base = plot_x + i * slot + slot / 2
            ch_call = plot_h * (b.call_oi / peak)
            ch_put = plot_h * (b.put_oi / peak)
            _fill(pdf, SKY)
            pdf.rect(base - bw - 0.4, plot_y + plot_h - ch_call, bw, ch_call, "F")
            _fill(pdf, AMBER)
            pdf.rect(base + 0.4, plot_y + plot_h - ch_put, bw, ch_put, "F")
            if i % 2 == 0:
                pdf.set_xy(base - slot / 2, plot_y + plot_h + 1)
                pdf.set_text_color(*MUTE)
                pdf.set_font("Helvetica", "", 6)
                pdf.cell(slot, 3, f"{b.strike:.0f}", align="C")
        # legend
        pdf.set_xy(x + 4, y + 2)
        _fill(pdf, SKY)
        pdf.rect(x + 4, y + 3, 3, 3, "F")
        pdf.set_xy(x + 8, y + 2)
        pdf.set_text_color(*MUTE)
        pdf.set_font("Helvetica", "", 7)
        pdf.cell(20, 4, "Call OI")
        _fill(pdf, AMBER)
        pdf.rect(x + 30, y + 3, 3, 3, "F")
        pdf.set_xy(x + 34, y + 2)
        pdf.cell(20, 4, "Put OI")

    def _gauge(self, pdf: FPDF, score: SentimentScore, *, x: float, y: float, w: float) -> None:
        _fill(pdf, CARD)
        pdf.rect(x, y, w, 26, "F")
        bar_x, bar_y, bar_w, bar_h = x + 8, y + 14, w - 16, 4.0
        seg = bar_w / 4
        for i, color in enumerate((RED, AMBER, (132, 204, 22), GREEN)):
            _fill(pdf, color)
            pdf.rect(bar_x + i * seg, bar_y, seg, bar_h, "F")
        # marker
        mx = bar_x + bar_w * (score.score / 100)
        _fill(pdf, INK)
        pdf.rect(mx - 0.6, bar_y - 2, 1.2, bar_h + 4, "F")
        # score text
        pdf.set_xy(x, y + 3)
        pdf.set_text_color(*_darker(EMERALD))
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(w, 8, _ascii(f"{score.score}%  {score.label}"), align="C")
        pdf.set_xy(bar_x, bar_y + 5)
        pdf.set_text_color(*MUTE)
        pdf.set_font("Helvetica", "", 7)
        pdf.cell(bar_w / 2, 4, "Bearish")
        pdf.cell(bar_w / 2, 4, "Bullish", align="R")

    def _signal_cards(self, pdf: FPDF, score: SentimentScore, *, y: float) -> None:
        cols = 3
        cw = _CONTENT_W / cols
        ch = 22.0
        for i, sig in enumerate(score.signals):
            col = i % cols
            row = i // cols
            cx = _MARGIN + col * cw
            cy = y + row * ch
            _fill(pdf, CARD)
            pdf.rect(cx + 1, cy, cw - 2, ch - 2, "F")
            pdf.set_xy(cx + 3, cy + 2)
            pdf.set_text_color(*INK)
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(cw - 5, 5, _ascii(sig.name), new_x=XPos.LEFT, new_y=YPos.NEXT)
            pdf.set_x(cx + 3)
            pdf.set_text_color(*MUTE)
            pdf.set_font("Helvetica", "", 7.5)
            pdf.multi_cell(cw - 5, 3.6, _ascii(sig.note))
            color = {Stance.BULLISH: GREEN, Stance.BEARISH: RED, Stance.NEUTRAL: MUTE}[sig.stance]
            pdf.set_xy(cx + 3, cy + ch - 7)
            pdf.set_text_color(*color)
            pdf.set_font("Helvetica", "B", 8)
            pdf.cell(cw - 5, 4, sig.stance.value)


def _fill(pdf: FPDF, color: tuple[int, int, int]) -> None:
    pdf.set_fill_color(*color)


def _darker(color: tuple[int, int, int]) -> tuple[int, int, int]:
    return tuple(max(0, int(c * 0.7)) for c in color)  # type: ignore[return-value]


def _dashed_h(pdf: FPDF, x1: float, x2: float, y: float) -> None:
    step = 3.0
    x = x1
    while x < x2:
        pdf.line(x, y, min(x + 1.5, x2), y)
        x += step


def _placeholder(pdf: FPDF, x: float, y: float, w: float, h: float) -> None:
    pdf.set_xy(x, y + h / 2 - 3)
    pdf.set_text_color(*MUTE)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(w, 6, "Data unavailable", align="C")


# Structural check: the renderer satisfies the port.
_: type[ReportRendererPort] = ReportPdfRenderer
