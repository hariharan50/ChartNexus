"""The calibrated ensemble and the multi-horizon guider."""

from __future__ import annotations

from marketcompass.contexts.signals.domain import ensemble, guider
from marketcompass.contexts.signals.domain.ensemble import HorizonModel, ModelArtifact
from marketcompass.contexts.signals.domain.features import FeatureVector, Regime
from marketcompass.contexts.signals.domain.inputs import MarketSnapshot
from marketcompass.contexts.signals.domain.models import Decision, Horizon


def _fv(values: dict[str, float], coverage: float = 1.0) -> FeatureVector:
    return FeatureVector(values=values, regime=Regime.RANGEBOUND, coverage=coverage)


def test_evaluate_bands_on_probability() -> None:
    model = HorizonModel(weights={"ret_5": 40.0}, band=0.06)
    buy = ensemble.evaluate(_fv({"ret_5": 0.02}), Horizon.INTRADAY, model)
    sell = ensemble.evaluate(_fv({"ret_5": -0.02}), Horizon.INTRADAY, model)
    hold = ensemble.evaluate(_fv({"ret_5": 0.0}), Horizon.INTRADAY, model)
    assert buy.decision is Decision.BUY and buy.probability > 0.5
    assert sell.decision is Decision.SELL and sell.probability < 0.5
    assert hold.decision is Decision.HOLD and hold.probability == 0.5


def test_confidence_scales_with_coverage() -> None:
    model = HorizonModel(weights={"ret_5": 40.0})
    full = ensemble.evaluate(_fv({"ret_5": 0.03}, coverage=1.0), Horizon.INTRADAY, model)
    thin = ensemble.evaluate(_fv({"ret_5": 0.03}, coverage=0.2), Horizon.INTRADAY, model)
    assert full.confidence > thin.confidence


def test_calibration_table_remaps_confidence() -> None:
    # A calibration saying "strong signals only hit 55%" caps confidence low.
    calibrated = HorizonModel(weights={"ret_5": 40.0}, calibration=((0.0, 0.5), (1.0, 0.55)))
    call = ensemble.evaluate(_fv({"ret_5": 0.05}), Horizon.INTRADAY, calibrated)
    assert call.confidence <= 56  # ~0.55 hit-rate, not a false 90%


def test_artifact_round_trips_through_dict() -> None:
    art = ensemble.default_artifact()
    back = ModelArtifact.from_dict(art.to_dict())
    assert set(back.models) == set(art.models)
    assert back.models[Horizon.INTRADAY].weights == art.models[Horizon.INTRADAY].weights


def test_default_artifact_reads_a_rising_tape_bullish() -> None:
    closes = tuple(100.0 + i for i in range(60))
    snap = MarketSnapshot(
        symbol="NIFTY",
        spot=closes[-1],
        closes=closes,
        highs=tuple(c + 2 for c in closes),
        lows=tuple(c - 2 for c in closes),
        volumes=tuple(1000.0 for _ in closes),
        daily_closes=tuple(100.0 + i for i in range(30)),
    )
    mhg = guider.build_multi_horizon(snap, ensemble.default_artifact())
    assert len(mhg.calls) == 3  # one per horizon
    intraday = mhg.call_for(Horizon.INTRADAY)
    assert intraday is not None and intraday.decision is Decision.BUY
    assert intraday.drivers  # surfaced the features that moved it
    assert mhg.regime == Regime.TRENDING_UP.value
    assert "intraday" in mhg.rationale.lower()
