"""Value objects for a daily market report.

All figures are plain floats/strings produced by the data gatherer (which converts
from the market-data Decimals); the domain stays framework-free so the scorer and
tests need no infrastructure. ``None`` is allowed everywhere a reading can be
missing (mock day, a tool that failed) so the report degrades gracefully rather
than crashing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum


class Stance(StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


@dataclass(frozen=True, slots=True)
class InstrumentSummary:
    symbol: str
    ltp: float | None
    change: float | None
    change_pct: float | None
    prev_close: float | None
    day_open: float | None
    day_high: float | None
    day_low: float | None
    week52_low: float | None
    week52_high: float | None
    source: str  # "live" | "mock"


@dataclass(frozen=True, slots=True)
class Candle:
    label: str  # short axis label, e.g. "26 09:15"
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True, slots=True)
class Level:
    price: float
    label: str  # "Strong" / "Secondary" etc.


@dataclass(frozen=True, slots=True)
class TechnicalRead:
    ema20: float | None
    ema50: float | None
    rsi14: float | None
    vwap: float | None
    atr14: float | None
    resistances: tuple[Level, ...] = ()
    supports: tuple[Level, ...] = ()


@dataclass(frozen=True, slots=True)
class OptionStrikeBar:
    strike: float
    call_oi: float
    put_oi: float


@dataclass(frozen=True, slots=True)
class OptionsSummary:
    pcr: float | None
    pcr_change: float | None
    max_pain: float | None
    atm_strike: float | None
    total_call_oi: float | None
    total_put_oi: float | None
    gamma_flip: float | None
    india_vix: float | None


@dataclass(frozen=True, slots=True)
class SentimentSignal:
    name: str
    stance: Stance
    note: str


@dataclass(frozen=True, slots=True)
class SentimentScore:
    #: 0-100 composite; higher = more bullish.
    score: int
    label: str  # "Strongly Bearish" .. "Strongly Bullish"
    signals: tuple[SentimentSignal, ...]


@dataclass(frozen=True, slots=True)
class ReportNarrative:
    """The LLM-written prose per section. Numbers are never taken from here."""

    technicals: str
    options: str
    sentiment: str
    outlook: str


@dataclass(frozen=True, slots=True)
class MarketReport:
    trading_day: date
    instrument: str
    summary: InstrumentSummary
    technical: TechnicalRead
    candles: tuple[Candle, ...]
    option_bars: tuple[OptionStrikeBar, ...]
    options: OptionsSummary
    sentiment: SentimentScore
    narrative: ReportNarrative
    #: "live" | "mock" — whether any read was simulated.
    source: str
    generated_at: datetime | None = None
    #: Extra source references shown on the legal page (best-effort).
    sources: tuple[str, ...] = field(default_factory=tuple)
