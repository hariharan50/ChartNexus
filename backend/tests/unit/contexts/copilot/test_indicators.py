"""Hella's TechnicalRead bundle.

The per-series maths (RSI/EMA/VWAP/ATR/swings) are tested once in
``tests/unit/shared_kernel/test_indicators.py``; here we only pin that ``compute``
wires them into the read and honours the short-series guards.
"""

from __future__ import annotations

import pytest

from marketcompass.contexts.copilot.domain import indicators


def test_compute_bundles_all_reads_and_swings() -> None:
    highs = [float(100 + i) for i in range(30)]
    lows = [float(90 + i) for i in range(30)]
    closes = [float(95 + i) for i in range(30)]
    volumes = [1000.0] * 30
    read = indicators.compute(highs, lows, closes, volumes)
    assert read.rsi14 == pytest.approx(100.0)  # strictly rising closes
    assert read.swing_resistance == max(highs[-20:])
    assert read.swing_support == min(lows[-20:])
    assert read.ema20 is not None and read.atr14 is not None and read.vwap is not None


def test_short_series_leaves_long_lookbacks_unavailable() -> None:
    # 30 bars: EMA50 can't be computed, but EMA20 and swings can.
    highs = [float(100 + i) for i in range(30)]
    lows = [float(90 + i) for i in range(30)]
    closes = [float(95 + i) for i in range(30)]
    read = indicators.compute(highs, lows, closes, [1000.0] * 30)
    assert read.ema50 is None
    assert read.ema20 is not None
