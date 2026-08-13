"""Pure technical-indicator math over a candle series.

No I/O, no market_data types — just number arrays in, a :class:`TechnicalRead`
out — so every formula is unit-testable in isolation and the copilot domain stays
free of infrastructure. The ``get_indicators`` tool fetches candles, hands the
float arrays here, and formats the result for the model.

Every value is ``None`` when the series is too short to compute it, so a thin
history never yields a fabricated reading.
"""

from __future__ import annotations

from dataclasses import dataclass

_RSI_PERIOD = 14
_ATR_PERIOD = 14
_EMA_FAST = 20
_EMA_SLOW = 50
# Bars scanned for the nearest swing high/low.
_SWING_WINDOW = 20


@dataclass(frozen=True, slots=True)
class TechnicalRead:
    rsi14: float | None
    ema20: float | None
    ema50: float | None
    vwap: float | None
    atr14: float | None
    swing_support: float | None
    swing_resistance: float | None


def compute(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    volumes: list[float],
) -> TechnicalRead:
    return TechnicalRead(
        rsi14=rsi(closes, _RSI_PERIOD),
        ema20=ema(closes, _EMA_FAST),
        ema50=ema(closes, _EMA_SLOW),
        vwap=vwap(highs, lows, closes, volumes),
        atr14=atr(highs, lows, closes, _ATR_PERIOD),
        swing_support=_recent_min(lows, _SWING_WINDOW),
        swing_resistance=_recent_max(highs, _SWING_WINDOW),
    )


def ema(values: list[float], period: int) -> float | None:
    """Exponential moving average, seeded with the SMA of the first ``period``."""
    if period <= 0 or len(values) < period:
        return None
    multiplier = 2 / (period + 1)
    avg = sum(values[:period]) / period
    for value in values[period:]:
        avg = (value - avg) * multiplier + avg
    return avg


def rsi(closes: list[float], period: int = _RSI_PERIOD) -> float | None:
    """Wilder's RSI in 0-100. ``None`` below ``period + 1`` closes."""
    if period <= 0 or len(closes) <= period:
        return None
    gains, losses = 0.0, 0.0
    for i in range(1, period + 1):
        change = closes[i] - closes[i - 1]
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    avg_gain, avg_loss = gains / period, losses / period
    for i in range(period + 1, len(closes)):
        change = closes[i] - closes[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(change, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-change, 0.0)) / period
    if avg_loss == 0.0:
        return 100.0 if avg_gain > 0.0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def vwap(
    highs: list[float], lows: list[float], closes: list[float], volumes: list[float]
) -> float | None:
    """Volume-weighted average of the typical price over the series.

    An approximation of session VWAP across whatever window the caller passes;
    with no volume it is undefined.
    """
    n = min(len(highs), len(lows), len(closes), len(volumes))
    if n == 0:
        return None
    pv, vol = 0.0, 0.0
    for i in range(n):
        typical = (highs[i] + lows[i] + closes[i]) / 3
        pv += typical * volumes[i]
        vol += volumes[i]
    return pv / vol if vol > 0 else None


def atr(
    highs: list[float], lows: list[float], closes: list[float], period: int = _ATR_PERIOD
) -> float | None:
    """Wilder's Average True Range. ``None`` below ``period + 1`` bars."""
    n = min(len(highs), len(lows), len(closes))
    if period <= 0 or n <= period:
        return None
    true_ranges: list[float] = []
    for i in range(1, n):
        prev_close = closes[i - 1]
        true_ranges.append(
            max(highs[i] - lows[i], abs(highs[i] - prev_close), abs(lows[i] - prev_close))
        )
    atr_value = sum(true_ranges[:period]) / period
    for tr in true_ranges[period:]:
        atr_value = (atr_value * (period - 1) + tr) / period
    return atr_value


def _recent_min(values: list[float], window: int) -> float | None:
    return min(values[-window:]) if values else None


def _recent_max(values: list[float], window: int) -> float | None:
    return max(values[-window:]) if values else None
