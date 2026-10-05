"""Feature computation — the vector the calibrated engine reads."""

from __future__ import annotations

import pytest

from chartnexus.contexts.signals.domain import features
from chartnexus.contexts.signals.domain.features import FeatureInputs, Regime


def _rising(n: int, base: float = 100.0) -> tuple[float, ...]:
    return tuple(base + i for i in range(n))


def test_empty_inputs_yield_no_features_and_rangebound() -> None:
    fv = features.compute(FeatureInputs(spot=100.0))
    assert fv.values == {}
    assert fv.coverage == 0.0
    assert fv.regime is Regime.RANGEBOUND


def test_rising_series_reads_bullish_and_trending_up() -> None:
    closes = _rising(60)
    highs = tuple(c + 2 for c in closes)
    lows = tuple(c - 2 for c in closes)
    fv = features.compute(
        FeatureInputs(
            spot=closes[-1],
            closes=closes,
            highs=highs,
            lows=lows,
            volumes=tuple(1000.0 for _ in closes),
            daily_closes=_rising(30),
        )
    )
    assert fv.values["ret_5"] > 0  # upward momentum
    assert fv.values["rsi_norm"] > 0  # overbought side
    assert fv.values["ema_gap"] > 0  # fast EMA above slow
    assert "adx" in fv.values
    assert fv.regime is Regime.TRENDING_UP
    assert 0.0 < fv.coverage <= 1.0


def test_flow_and_level_features_are_signed_correctly() -> None:
    fv = features.compute(
        FeatureInputs(
            spot=100.0,
            pcr_series=(0.9, 1.0, 1.2),  # rising PCR (puts building) = bullish velocity
            call_oi_chg=1_000,
            put_oi_chg=3_000,  # puts building faster -> bullish buildup
            gex_net=500.0,
            max_pain=98.0,  # spot above max pain -> positive distance
            put_wall=95.0,
        )
    )
    assert fv.values["buildup_bias"] > 0
    assert fv.values["pcr_velocity"] > 0
    assert fv.values["gex_sign"] == 1.0
    assert fv.values["dist_max_pain"] == pytest.approx((100.0 - 98.0) / 100.0)
    assert fv.values["dist_put_wall"] > 0


def test_coverage_reflects_how_many_features_computed() -> None:
    full = features.compute(
        FeatureInputs(
            spot=100.0,
            closes=_rising(60),
            highs=_rising(60, 102),
            lows=_rising(60, 98),
            volumes=tuple(1000.0 for _ in range(60)),
            daily_closes=_rising(30),
            pcr_series=(1.0, 1.1),
            call_oi_chg=1,
            put_oi_chg=2,
            gex_net=1.0,
            max_pain=99.0,
            iv_percentile=50.0,
            atm_call_iv=12.0,
            atm_put_iv=13.0,
        )
    )
    sparse = features.compute(FeatureInputs(spot=100.0, pcr_series=(1.0,)))
    assert full.coverage > sparse.coverage
