"""Pure technical-indicator math.

Small, deterministic series pin the formulas and the short-series guards, so a
regression in the tool's numbers is caught here, without a model or a broker.
"""

from __future__ import annotations

import pytest

from marketcompass.contexts.copilot.domain import indicators


def test_ema_is_none_below_period() -> None:
    assert indicators.ema([1.0, 2.0, 3.0], 5) is None


def test_ema_of_a_flat_series_is_the_level() -> None:
    assert indicators.ema([100.0] * 30, 20) == pytest.approx(100.0)


def test_ema_tracks_a_rising_series_below_the_last_close() -> None:
    values = [float(i) for i in range(1, 31)]  # 1..30
    e = indicators.ema(values, 10)
    assert e is not None
    assert e < values[-1]  # EMA lags a rising series
    assert e > values[len(values) // 2]  # but leads the mid-point


def test_rsi_all_gains_is_100() -> None:
    closes = [float(i) for i in range(1, 40)]  # strictly rising
    assert indicators.rsi(closes, 14) == pytest.approx(100.0)


def test_rsi_all_losses_is_0() -> None:
    closes = [float(i) for i in range(40, 1, -1)]  # strictly falling
    assert indicators.rsi(closes, 14) == pytest.approx(0.0)


def test_rsi_none_when_too_short() -> None:
    assert indicators.rsi([1.0, 2.0, 3.0], 14) is None


def test_vwap_weights_by_volume() -> None:
    # Two bars: typical prices 10 and 20, volumes 1 and 3 -> (10*1 + 20*3)/4 = 17.5
    v = indicators.vwap([10.0, 20.0], [10.0, 20.0], [10.0, 20.0], [1.0, 3.0])
    assert v == pytest.approx(17.5)


def test_vwap_none_without_volume() -> None:
    assert indicators.vwap([10.0], [10.0], [10.0], [0.0]) is None


def test_atr_of_constant_range_is_that_range() -> None:
    # Every bar spans exactly 4 points and doesn't gap -> ATR converges to 4.
    highs = [102.0] * 30
    lows = [98.0] * 30
    closes = [100.0] * 30
    assert indicators.atr(highs, lows, closes, 14) == pytest.approx(4.0)


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
