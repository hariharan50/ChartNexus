"""The deterministic "MarketCompass Score" — a transparent composite, not the LLM.

Each sub-signal is derived from a gathered number and contributes a fixed weight
to a 0-100 score centred at 50. Reproducible: the same inputs always give the same
score, and every card on the report shows which reading drove it. No model, no
randomness, no network.
"""

from __future__ import annotations

from collections.abc import Callable

from marketcompass.contexts.report.domain.report import (
    InstrumentSummary,
    OptionsSummary,
    SentimentScore,
    SentimentSignal,
    Stance,
    TechnicalRead,
)

_START = 50

# Thresholds (named so the scoring is auditable and lint-clean).
_RSI_BULL, _RSI_BEAR = 55.0, 45.0
_CHG_BULL, _CHG_BEAR = 0.15, -0.15
_PCR_BULL, _PCR_BEAR = 1.0, 0.85
_OI_SKEW = 1.1
_VIX_HIGH, _VIX_LOW = 18.0, 13.0

# Band boundaries.
_BAND_STRONG_BEAR, _BAND_BEAR, _BAND_NEUTRAL, _BAND_BULL = 30, 45, 55, 70

_Contribution = tuple[float, SentimentSignal]
_Rule = Callable[[InstrumentSummary, OptionsSummary, TechnicalRead], "_Contribution | None"]


def _band(score: int) -> str:
    if score < _BAND_STRONG_BEAR:
        return "Strongly Bearish"
    if score < _BAND_BEAR:
        return "Bearish"
    if score <= _BAND_NEUTRAL:
        return "Neutral"
    if score <= _BAND_BULL:
        return "Bullish"
    return "Strongly Bullish"


def _clamp(value: float) -> int:
    return max(0, min(100, round(value)))


def _trend(s: InstrumentSummary, _o: OptionsSummary, t: TechnicalRead) -> _Contribution | None:
    if s.ltp is None or t.ema20 is None:
        return None
    below_chain = t.ema50 is None or t.ema20 <= t.ema50
    above_chain = t.ema50 is None or t.ema20 >= t.ema50
    if s.ltp > t.ema20 and above_chain:
        return 12.0, SentimentSignal("Trend", Stance.BULLISH, "Price above EMA20")
    if s.ltp < t.ema20 and below_chain:
        return -12.0, SentimentSignal("Trend", Stance.BEARISH, "Price below EMA20")
    return 0.0, SentimentSignal("Trend", Stance.NEUTRAL, "Price around EMA20")


def _momentum(_s: InstrumentSummary, _o: OptionsSummary, t: TechnicalRead) -> _Contribution | None:
    if t.rsi14 is None:
        return None
    note = f"RSI {t.rsi14:.0f}"
    if t.rsi14 >= _RSI_BULL:
        return 8.0, SentimentSignal("Momentum", Stance.BULLISH, note)
    if t.rsi14 <= _RSI_BEAR:
        return -8.0, SentimentSignal("Momentum", Stance.BEARISH, note)
    return 0.0, SentimentSignal("Momentum", Stance.NEUTRAL, note)


def _day_move(s: InstrumentSummary, _o: OptionsSummary, _t: TechnicalRead) -> _Contribution | None:
    if s.change_pct is None:
        return None
    note = f"{s.change_pct:+.2f}%"
    if s.change_pct > _CHG_BULL:
        return 6.0, SentimentSignal("Day Move", Stance.BULLISH, note)
    if s.change_pct < _CHG_BEAR:
        return -6.0, SentimentSignal("Day Move", Stance.BEARISH, note)
    return 0.0, SentimentSignal("Day Move", Stance.NEUTRAL, note)


def _pcr(_s: InstrumentSummary, o: OptionsSummary, _t: TechnicalRead) -> _Contribution | None:
    if o.pcr is None:
        return None
    note = f"PCR {o.pcr:.2f}"
    if o.pcr >= _PCR_BULL:
        return 8.0, SentimentSignal("PCR", Stance.BULLISH, note)
    if o.pcr < _PCR_BEAR:
        return -8.0, SentimentSignal("PCR", Stance.BEARISH, note)
    return 0.0, SentimentSignal("PCR", Stance.NEUTRAL, note)


def _oi_skew(_s: InstrumentSummary, o: OptionsSummary, _t: TechnicalRead) -> _Contribution | None:
    ce, pe = o.total_call_oi, o.total_put_oi
    if ce is None or pe is None or (ce + pe) <= 0:
        return None
    if ce > pe * _OI_SKEW:
        return -6.0, SentimentSignal("OI Skew", Stance.BEARISH, "Call OI > Put OI")
    if pe > ce * _OI_SKEW:
        return 6.0, SentimentSignal("OI Skew", Stance.BULLISH, "Put OI > Call OI")
    return 0.0, SentimentSignal("OI Skew", Stance.NEUTRAL, "Balanced OI")


def _volatility(_s: InstrumentSummary, o: OptionsSummary, _t: TechnicalRead) -> _Contribution | None:
    if o.india_vix is None:
        return None
    if o.india_vix >= _VIX_HIGH:
        return -5.0, SentimentSignal("Volatility", Stance.BEARISH, f"VIX {o.india_vix:.1f} elevated")
    if o.india_vix < _VIX_LOW:
        return 3.0, SentimentSignal("Volatility", Stance.BULLISH, f"VIX {o.india_vix:.1f} calm")
    return 0.0, SentimentSignal("Volatility", Stance.NEUTRAL, f"VIX {o.india_vix:.1f}")


_RULES: tuple[_Rule, ...] = (_trend, _momentum, _day_move, _pcr, _oi_skew, _volatility)


def compute_score(
    summary: InstrumentSummary,
    technical: TechnicalRead,
    options: OptionsSummary,
) -> SentimentScore:
    total = float(_START)
    signals: list[SentimentSignal] = []
    for rule in _RULES:
        result = rule(summary, options, technical)
        if result is None:
            continue
        delta, signal = result
        total += delta
        signals.append(signal)
    score = _clamp(total)
    return SentimentScore(score=score, label=_band(score), signals=tuple(signals))
