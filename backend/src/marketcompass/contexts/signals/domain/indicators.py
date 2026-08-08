"""Small pure indicators the skills share.

Kept separate so EMA, ATR and the squashing helpers are unit-tested once and
reused by both the Price-Action and Level-Based skills. No numpy — the series
are a few dozen bars at most, and a dependency-free loop is easier to reason
about than a vectorised one for that size.
"""

from __future__ import annotations

from collections.abc import Sequence


def clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    """Pin ``value`` into ``[low, high]`` — every skill score lives there."""
    return max(low, min(high, value))


def ema(values: Sequence[float], period: int) -> float | None:
    """Exponential moving average of the last ``period`` bars.

    ``None`` when there are fewer than ``period`` samples: an EMA seeded on a
    couple of bars is just those bars, and a trend read off it would be noise
    dressed as signal.
    """
    if period <= 0 or len(values) < period:
        return None
    alpha = 2.0 / (period + 1.0)
    # Seed on the simple average of the first `period` samples, then walk.
    seed = sum(values[:period]) / period
    result = seed
    for value in values[period:]:
        result = alpha * value + (1.0 - alpha) * result
    return result


def atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> float | None:
    """Average true range over ``period`` bars.

    ``None`` when the three series are not aligned or too short. True range uses
    the prior close, so the first bar is skipped; ``period`` true ranges need
    ``period + 1`` bars.
    """
    n = len(closes)
    if n != len(highs) or n != len(lows) or n < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, n):
        prev_close = closes[i - 1]
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - prev_close),
            abs(lows[i] - prev_close),
        )
        trs.append(tr)
    window = trs[-period:]
    return sum(window) / len(window)


def slope_pct(values: Sequence[float], lookback: int) -> float | None:
    """Percentage change of the last ``lookback`` bars, latest vs. that far back.

    A cheap trend proxy when there are too few bars for a clean EMA cross.
    ``None`` when there is not enough history or the reference price is zero.
    """
    if lookback <= 0 or len(values) <= lookback:
        return None
    past = values[-1 - lookback]
    if past == 0.0:
        return None
    return (values[-1] - past) / abs(past)
