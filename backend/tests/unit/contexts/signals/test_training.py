"""The pure fit/calibrate/backtest core, pinned on deterministic synthetic data."""

from __future__ import annotations

import pytest

from chartnexus.contexts.signals.domain.training import (
    LabeledRow,
    backtest,
    build_calibration,
    fit_logistic,
)

pytestmark = pytest.mark.unit

_NAMES = ("x",)


def _separable_rows() -> list[LabeledRow]:
    """A clean linear rule: label = 1 when x > 0. The dead zone is left out."""
    rows: list[LabeledRow] = []
    for k in range(-50, 51):
        if k == 0:
            continue
        x = k / 50.0
        rows.append(LabeledRow(features={"x": x}, label=1 if x > 0 else 0))
    return rows


def test_fit_recovers_the_direction() -> None:
    model = fit_logistic(_separable_rows(), _NAMES, epochs=600)
    assert model.weights["x"] > 0.0
    assert abs(model.bias) < 0.5  # symmetric data → near-zero intercept


def test_fit_then_backtest_is_accurate_on_separable_data() -> None:
    model = fit_logistic(_separable_rows(), _NAMES, epochs=600)
    report = backtest(_separable_rows(), model, _NAMES)
    assert report["directional_accuracy"] == 1.0
    assert report["coverage"] > 0.5
    assert report["brier"] < 0.2


def test_fit_rejects_degenerate_datasets() -> None:
    with pytest.raises(ValueError, match="empty"):
        fit_logistic([], _NAMES)
    single = [LabeledRow(features={"x": 0.5}, label=1) for _ in range(4)]
    with pytest.raises(ValueError, match="single class"):
        fit_logistic(single, _NAMES)


def test_calibration_is_non_decreasing() -> None:
    # Strength rises with hit-rate, but with a local violation the pooling fixes.
    scored = [(0.1, 0), (0.3, 1), (0.2, 0), (0.5, 1), (0.9, 1)]
    table = build_calibration(scored, bins=5)
    ys = [y for _, y in table]
    assert ys == sorted(ys)
    xs = [x for x, _ in table]
    assert xs == sorted(xs)


def test_missing_feature_is_treated_as_neutral() -> None:
    # A row with no "x" must not crash the fit or the backtest — it contributes 0.
    rows = [*_separable_rows(), LabeledRow(features={}, label=1)]
    model = fit_logistic(rows, _NAMES, epochs=200)
    report = backtest(rows, model, _NAMES)
    assert report["n"] == len(rows)
