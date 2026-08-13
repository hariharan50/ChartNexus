"""Hella's technical read — a bundle over the shared indicator maths.

The per-series formulas (RSI/EMA/VWAP/ATR/swings) live once in
``shared_kernel.domain.indicators``; this module only composes them into the
``TechnicalRead`` the ``get_indicators`` tool formats. Keeping the maths shared
means the agent and the signals engine can never drift apart on the numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

from marketcompass.shared_kernel.domain import indicators as ind

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
        rsi14=ind.rsi(closes, _RSI_PERIOD),
        ema20=ind.ema(closes, _EMA_FAST),
        ema50=ind.ema(closes, _EMA_SLOW),
        vwap=ind.vwap(highs, lows, closes, volumes),
        atr14=ind.atr(highs, lows, closes, _ATR_PERIOD),
        swing_support=ind.recent_min(lows, _SWING_WINDOW),
        swing_resistance=ind.recent_max(highs, _SWING_WINDOW),
    )
