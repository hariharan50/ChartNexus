"""Shared indicator maths — the primitives the signals engine and copilot share."""

from __future__ import annotations

import pytest

from chartnexus.shared_kernel.domain import indicators as ind


def test_clamp_and_sigmoid() -> None:
    assert ind.clamp(5.0) == 1.0
    assert ind.clamp(-5.0) == -1.0
    assert ind.sigmoid(0.0) == pytest.approx(0.5)
    assert ind.sigmoid(100.0) == pytest.approx(1.0, abs=1e-6)
    assert ind.sigmoid(-100.0) == pytest.approx(0.0, abs=1e-6)


def test_ema_none_below_period_and_flat_series() -> None:
    assert ind.ema([1.0, 2.0], 5) is None
    assert ind.ema([100.0] * 30, 20) == pytest.approx(100.0)


def test_rsi_extremes_and_short_guard() -> None:
    assert ind.rsi([float(i) for i in range(1, 40)], 14) == pytest.approx(100.0)
    assert ind.rsi([float(i) for i in range(40, 1, -1)], 14) == pytest.approx(0.0)
    assert ind.rsi([1.0, 2.0, 3.0], 14) is None


def test_atr_of_constant_range() -> None:
    highs, lows, closes = [102.0] * 30, [98.0] * 30, [100.0] * 30
    assert ind.atr(highs, lows, closes, 14) == pytest.approx(4.0)


def test_adx_is_high_on_a_clean_trend_and_none_when_short() -> None:
    n = 60
    highs = [100.0 + i for i in range(n)]
    lows = [98.0 + i for i in range(n)]
    closes = [99.0 + i for i in range(n)]
    value = ind.adx(highs, lows, closes, 14)
    assert value is not None and value > 40.0  # strong, clean uptrend
    assert ind.adx([1.0, 2.0], [1.0, 2.0], [1.0, 2.0], 14) is None


def test_bollinger_width_and_realized_vol() -> None:
    assert ind.bollinger_width([100.0] * 20, 20) == pytest.approx(0.0)
    assert ind.realized_vol([100.0] * 25, 20) == pytest.approx(0.0)
    assert ind.realized_vol([1.0, 2.0], 20) is None


def test_vwap_weights_by_volume() -> None:
    v = ind.vwap([10.0, 20.0], [10.0, 20.0], [10.0, 20.0], [1.0, 3.0])
    assert v == pytest.approx(17.5)
    assert ind.vwap([10.0], [10.0], [10.0], [0.0]) is None
