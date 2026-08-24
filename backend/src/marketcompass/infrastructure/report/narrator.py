"""The report's LLM narrator — MME100 writing prose, never numbers.

A single structured call turns the already-computed facts into four short
commentaries (technicals, options, sentiment, outlook). It is told to ground
strictly in the supplied facts and invent no figures. With no model (no user key)
or on any failure, a deterministic fallback composes plain prose from the same
facts — so the report always has readable commentary and never blocks.

Token-light by design: one call, compact facts in, short prose out. Global cues
reuse today's MME100 briefing (passed in as ``outlook_context``) instead of a
second web search.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from marketcompass.contexts.report.application.ports import ReportInputs, ReportNarratorPort
from marketcompass.contexts.report.domain.report import ReportNarrative, SentimentScore

_MAX_OUTLOOK_CONTEXT = 8000
_FLAT_PCT = 0.1  # |day change| below this reads as "flat" in the fallback prose


class _Sections(BaseModel):
    technicals: str = Field(description="2-3 sentences on price action, trend, key levels.")
    options: str = Field(description="2-3 sentences on OI, PCR, max pain, positioning.")
    sentiment: str = Field(description="2-3 sentences explaining the composite score.")
    outlook: str = Field(
        description=(
            "A DETAILED global-cues & pre-market outlook, drawn from the briefing "
            "context. Use short labelled lines (one per cue), each starting with the "
            "label and a colon, in this order:\n"
            "US Markets: Dow/S&P/Nasdaq levels, % move and driver.\n"
            "Asian Markets: Nikkei/Hang Seng/Shanghai/Kospi direction.\n"
            "Crude Oil: level, trend and India read-through.\n"
            "Gold: level and safe-haven read.\n"
            "USD-INR: rate, direction and sector read.\n"
            "Bond Yields: US 10Y and India 10Y levels.\n"
            "GIFT Nifty: level and premium/discount to spot.\n"
            "Opening View: expected gap (points and %) and gap-up/down/flat.\n"
            "Bias: overall bullish/bearish/sideways with reasoning.\n"
            "Then one short 'Summary:' paragraph tying the cues to today's setup. "
            "Ground every figure in the briefing context; if a cue is missing there, "
            "write 'Data unavailable' for that line rather than inventing a number."
        )
    )


class Mme100ReportNarrator:
    """Implements ``ReportNarratorPort`` over the user's chat model."""

    def __init__(self, model: Any | None) -> None:
        # ``model`` is a langchain BaseChatModel, but typed ``Any`` so this module
        # stays free of the langchain_core import (confined to infrastructure/agent).
        self._model = model

    @property
    def available(self) -> bool:
        return self._model is not None

    async def narrate(
        self,
        symbol: str,
        inputs: ReportInputs,
        score: SentimentScore,
        outlook_context: str | None,
    ) -> ReportNarrative:
        facts = _facts(symbol, inputs, score, outlook_context)
        if self._model is None:
            return _fallback(symbol, inputs, score)
        prompt = (
            "You are MME100, a disciplined Indian market analyst writing a paid daily report.\n"
            "Write professional commentary for four sections. Keep technicals, options and "
            "sentiment concise (2-3 sentences each), but make the OUTLOOK section DETAILED — a "
            "full global-cues breakdown with a labelled line per cue as instructed, followed by "
            "a short summary. Ground EVERY statement strictly in the FACTS below — do NOT invent "
            "any number, level, or figure not present there; where a cue is missing from the "
            "briefing context, write 'Data unavailable' for that line. Measured tone, no hype, "
            "no guarantees. Do not add a disclaimer (the report has one).\n\n"
            f"FACTS:\n{facts}\n\n"
            "Return the four sections."
        )
        try:
            structured = self._model.with_structured_output(_Sections)
            result = await structured.ainvoke(prompt)
        except Exception:
            return _fallback(symbol, inputs, score)
        if not isinstance(result, _Sections):
            return _fallback(symbol, inputs, score)
        return ReportNarrative(
            technicals=result.technicals.strip(),
            options=result.options.strip(),
            sentiment=result.sentiment.strip(),
            outlook=result.outlook.strip(),
        )


def _facts(
    symbol: str, inputs: ReportInputs, score: SentimentScore, outlook_context: str | None
) -> str:
    s, t, o = inputs.summary, inputs.technical, inputs.options
    lines = [
        f"Instrument: {symbol}  (data source: {inputs.source})",
        f"LTP: {s.ltp}  change: {s.change} ({s.change_pct}%)  prev_close: {s.prev_close}",
        f"Day: open {s.day_open}, high {s.day_high}, low {s.day_low}; "
        f"52W {s.week52_low}-{s.week52_high}",
        f"Technicals: EMA20 {t.ema20}, EMA50 {t.ema50}, RSI14 {t.rsi14}, VWAP {t.vwap}, "
        f"ATR14 {t.atr14}",
        "Resistances: " + ", ".join(f"{lv.price:.0f} ({lv.label})" for lv in t.resistances),
        "Supports: " + ", ".join(f"{lv.price:.0f} ({lv.label})" for lv in t.supports),
        f"Options: PCR {o.pcr} (chg {o.pcr_change}), max_pain {o.max_pain}, ATM {o.atm_strike}, "
        f"gamma_flip {o.gamma_flip}, total_CE_OI {o.total_call_oi}, total_PE_OI {o.total_put_oi}, "
        f"India_VIX {o.india_vix}",
        f"MarketCompass Score: {score.score}/100 ({score.label}); signals: "
        + "; ".join(f"{sig.name}={sig.stance.value}" for sig in score.signals),
    ]
    if outlook_context:
        lines.append(
            "Today's global cues / pre-market briefing (reuse for the outlook section):\n"
            + outlook_context[:_MAX_OUTLOOK_CONTEXT]
        )
    return "\n".join(lines)


def _fallback(symbol: str, inputs: ReportInputs, score: SentimentScore) -> ReportNarrative:
    """Deterministic prose from the numbers — used when no LLM key is configured."""
    s, t, o = inputs.summary, inputs.technical, inputs.options
    direction = "little changed"
    if s.change_pct is not None:
        direction = (
            "up" if s.change_pct > _FLAT_PCT else "down" if s.change_pct < -_FLAT_PCT else "flat"
        )
    trend = ""
    if s.ltp is not None and t.ema20 is not None:
        trend = " above its EMA20" if s.ltp > t.ema20 else " below its EMA20"
    technicals = (
        f"{symbol} is trading {direction}"
        + (f" ({s.change_pct:+.2f}%)" if s.change_pct is not None else "")
        + (f", currently{trend}." if trend else ".")
    )
    options = (
        f"PCR is {o.pcr if o.pcr is not None else 'n/a'}"
        + (f" with max pain near {o.max_pain:.0f}" if o.max_pain is not None else "")
        + (f"; India VIX at {o.india_vix:.2f}." if o.india_vix is not None else ".")
    )
    sentiment = (
        f"The composite MarketCompass Score is {score.score}/100 ({score.label}), built from "
        + ", ".join(f"{sig.name.lower()} {sig.stance.value.lower()}" for sig in score.signals[:4])
        + "."
    )
    outlook = (
        "Automated summary (add an LLM key in Settings -> AI for a full written outlook). "
        "Review the levels and options positioning above before the open."
    )
    return ReportNarrative(
        technicals=technicals, options=options, sentiment=sentiment, outlook=outlook
    )


# Structural check: the narrator satisfies the port.
_: type[ReportNarratorPort] = Mme100ReportNarrator
