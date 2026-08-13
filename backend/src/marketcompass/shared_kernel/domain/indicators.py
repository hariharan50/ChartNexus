"""Pure technical-indicator and math primitives, shared across contexts.

The one home for EMA/RSI/ATR/ADX/VWAP and the small squashing helpers, so the
signals engine and the copilot agent read the same numbers rather than keeping
divergent copies. No numpy and no I/O — the series a caller passes are at most a
few hundred bars, and a dependency-free loop is easier to reason about and test
than a vectorised one at that size. (Bulk historical computation over the archive
is done vectorised in infrastructure; this module is the per-series maths.)

Every function returns ``None`` when the series is too short to compute honestly,
so a thin history never yields a fabricated reading.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

# Below this many usable returns, a standard deviation is noise, not vol.
_MIN_RETURNS = 2


def clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    """Pin ``value`` into ``[low, high]``."""
    return max(low, min(high, value))


def sigmoid(x: float) -> float:
    """Logistic squash to ``(0, 1)`` — the ensemble's link function."""
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def ema(values: Sequence[float], period: int) -> float | None:
    """Exponential moving average, seeded on the SMA of the first ``period``."""
    if period <= 0 or len(values) < period:
        return None
    alpha = 2.0 / (period + 1.0)
    result = sum(values[:period]) / period
    for value in values[period:]:
        result = alpha * value + (1.0 - alpha) * result
    return result


def slope_pct(values: Sequence[float], lookback: int) -> float | None:
    """Fractional change of the last ``lookback`` bars, latest vs that far back."""
    if lookback <= 0 or len(values) <= lookback:
        return None
    past = values[-1 - lookback]
    if past == 0.0:
        return None
    return (values[-1] - past) / abs(past)


def rsi(closes: Sequence[float], period: int = 14) -> float | None:
    """Wilder's RSI in ``0-100``. ``None`` below ``period + 1`` closes."""
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


def atr(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14
) -> float | None:
    """Wilder's Average True Range. ``None`` below ``period + 1`` aligned bars."""
    n = min(len(highs), len(lows), len(closes))
    if period <= 0 or n <= period:
        return None
    trs = _true_ranges(highs, lows, closes, n)
    value = sum(trs[:period]) / period
    for tr in trs[period:]:
        value = (value * (period - 1) + tr) / period
    return value


def adx(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14
) -> float | None:
    """Wilder's Average Directional Index in ``0-100`` — trend strength.

    Above ~25 reads as a trending market, below ~20 as rangebound. ``None`` until
    there are enough bars for the double smoothing (``2*period + 1``).
    """
    n = min(len(highs), len(lows), len(closes))
    if period <= 0 or n < 2 * period + 1:
        return None

    plus_dm, minus_dm, trs = [], [], []
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if (up > down and up > 0) else 0.0)
        minus_dm.append(down if (down > up and down > 0) else 0.0)
        prev_close = closes[i - 1]
        trs.append(max(highs[i] - lows[i], abs(highs[i] - prev_close), abs(lows[i] - prev_close)))

    def _wilder(seq: list[float]) -> list[float]:
        smoothed = [sum(seq[:period])]
        for value in seq[period:]:
            smoothed.append(smoothed[-1] - smoothed[-1] / period + value)
        return smoothed

    tr_s, plus_s, minus_s = _wilder(trs), _wilder(plus_dm), _wilder(minus_dm)
    dxs: list[float] = []
    for tr_v, plus_v, minus_v in zip(tr_s, plus_s, minus_s, strict=True):
        if tr_v == 0.0:
            continue
        plus_di = 100.0 * plus_v / tr_v
        minus_di = 100.0 * minus_v / tr_v
        denom = plus_di + minus_di
        dxs.append(0.0 if denom == 0.0 else 100.0 * abs(plus_di - minus_di) / denom)
    if len(dxs) < period:
        return None
    return sum(dxs[-period:]) / period


def bollinger_width(closes: Sequence[float], period: int = 20, mult: float = 2.0) -> float | None:
    """Band width as a fraction of the middle band — a volatility/expansion read."""
    if period <= 0 or len(closes) < period:
        return None
    window = list(closes[-period:])
    mid = sum(window) / period
    if mid == 0.0:
        return None
    variance = sum((c - mid) ** 2 for c in window) / period
    return (2.0 * mult * math.sqrt(variance)) / abs(mid)


def realized_vol(closes: Sequence[float], period: int = 20) -> float | None:
    """Standard deviation of simple returns over the window (unannualised)."""
    if period <= 1 or len(closes) < period + 1:
        return None
    returns: list[float] = []
    for i in range(len(closes) - period, len(closes)):
        prev = closes[i - 1]
        if prev != 0.0:
            returns.append((closes[i] - prev) / prev)
    if len(returns) < _MIN_RETURNS:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / len(returns)
    return math.sqrt(variance)


def vwap(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[float],
) -> float | None:
    """Volume-weighted average of the typical price over the series."""
    n = min(len(highs), len(lows), len(closes), len(volumes))
    if n == 0:
        return None
    pv, vol = 0.0, 0.0
    for i in range(n):
        typical = (highs[i] + lows[i] + closes[i]) / 3.0
        pv += typical * volumes[i]
        vol += volumes[i]
    return pv / vol if vol > 0 else None


def recent_min(values: Sequence[float], window: int) -> float | None:
    return min(values[-window:]) if values else None


def recent_max(values: Sequence[float], window: int) -> float | None:
    return max(values[-window:]) if values else None


def _true_ranges(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], n: int
) -> list[float]:
    return [
        max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        for i in range(1, n)
    ]
