"""Fit and score the calibrated ensemble — pure Python, no numpy.

Three pieces, all operating on plain rows so they are trivially unit-testable and
carry no dependency the running app doesn't already have:

* :func:`fit_logistic` — batch gradient descent with L2, producing a
  :class:`HorizonModel`'s weights and bias. A missing feature is treated as the
  neutral ``0`` it is at inference (``evaluate`` skips absent features), so train
  and serve agree.
* :func:`build_calibration` — bins raw signal *strength* against the realised
  hit-rate to fill the calibration table, so confidence reflects measured
  accuracy rather than raw logit distance.
* :func:`backtest` — replays rows through a model and reports the numbers that say
  whether it is any good: directional accuracy on decisive calls, coverage, Brier
  score, and a calibration curve.

Data sizes here are small (an archive's worth of frames by 21 features), so plain
Python is fast enough and keeps the fit dependency-free.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from chartnexus.contexts.signals.domain.ensemble import HorizonModel, _band
from chartnexus.shared_kernel.domain import indicators as ind

# A separable dataset needs both classes; pooling compares adjacent pairs.
_BOTH_CLASSES = 2
_ADJACENT_PAIR = 2


@dataclass(frozen=True, slots=True)
class LabeledRow:
    """One training example: the feature values that were present, and what
    happened next (1 = up, 0 = down)."""

    features: dict[str, float]
    label: int


def fit_logistic(
    rows: Sequence[LabeledRow],
    feature_names: Sequence[str],
    *,
    learning_rate: float = 0.1,
    epochs: int = 400,
    l2: float = 1e-3,
) -> HorizonModel:
    """Fit logistic weights + bias by gradient descent over ``feature_names``.

    Returns an *uncalibrated* :class:`HorizonModel`; pair with
    :func:`build_calibration` to fill its table. Raises ``ValueError`` on an empty
    or single-class dataset — there is nothing to learn from either.
    """
    if not rows:
        raise ValueError("cannot fit on an empty dataset")
    labels = {row.label for row in rows}
    if labels - {0, 1}:
        raise ValueError(f"labels must be 0/1, got {sorted(labels)}")
    if len(labels) < _BOTH_CLASSES:
        raise ValueError("dataset has a single class — nothing to separate")

    names = list(feature_names)
    weights = dict.fromkeys(names, 0.0)
    bias = 0.0
    n = len(rows)

    for _ in range(epochs):
        grad_w = dict.fromkeys(names, 0.0)
        grad_b = 0.0
        for row in rows:
            z = bias + sum(weights[name] * row.features.get(name, 0.0) for name in names)
            error = ind.sigmoid(z) - row.label
            grad_b += error
            for name in names:
                grad_w[name] += error * row.features.get(name, 0.0)
        bias -= learning_rate * (grad_b / n)
        for name in names:
            step = grad_w[name] / n + l2 * weights[name]
            weights[name] -= learning_rate * step

    return HorizonModel(weights=weights, bias=round(bias, 6))


def build_calibration(
    scored: Sequence[tuple[float, int]],
    *,
    bins: int = 5,
) -> tuple[tuple[float, float], ...]:
    """Map signal strength → realised hit-rate.

    ``scored`` is ``(strength, hit)`` pairs where ``strength ∈ [0, 1]`` is the
    call's conviction and ``hit`` is 1 when the decisive call was right. Returns
    ascending ``(mean_strength, hit_rate)`` points for the non-empty bins, made
    non-decreasing (pool-adjacent) so confidence never falls as strength rises.
    """
    if not scored or bins < 1:
        return ()
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(bins)]
    for strength, hit in scored:
        s = min(1.0, max(0.0, strength))
        idx = min(bins - 1, int(s * bins))
        buckets[idx].append((s, hit))

    points: list[tuple[float, float]] = []
    for bucket in buckets:
        if not bucket:
            continue
        mean_s = sum(s for s, _ in bucket) / len(bucket)
        rate = sum(h for _, h in bucket) / len(bucket)
        points.append((round(mean_s, 4), round(rate, 4)))

    return _pool_monotone(points)


def _pool_monotone(points: list[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    """Pool-adjacent-violators lite: enforce a non-decreasing hit-rate."""
    pooled: list[list[float]] = []  # each: [x_sum, y_sum, count]
    for x, y in points:
        pooled.append([x, y, 1.0])
        while (
            len(pooled) >= _ADJACENT_PAIR
            and pooled[-2][1] / pooled[-2][2] > pooled[-1][1] / pooled[-1][2]
        ):
            x2, y2, c2 = pooled.pop()
            pooled[-1][0] += x2
            pooled[-1][1] += y2
            pooled[-1][2] += c2
    return tuple((round(x / c, 4), round(y / c, 4)) for x, y, c in pooled)


def backtest(
    rows: Sequence[LabeledRow],
    model: HorizonModel,
    feature_names: Sequence[str],
) -> dict[str, Any]:
    """Replay ``rows`` through ``model`` and report how well it did.

    ``directional_accuracy`` is over *decisive* calls only (those that cleared the
    band); ``coverage`` is the decisive fraction; ``brier`` is the mean squared
    error of the probability against the outcome; ``calibration`` bins predicted
    probability against the realised up-rate.
    """
    names = list(feature_names)
    n = len(rows)
    if n == 0:
        return {"n": 0}

    decisive = 0
    correct = 0
    brier_sum = 0.0
    prob_bins: list[list[tuple[float, int]]] = [[] for _ in range(10)]

    for row in rows:
        z = model.bias + sum(model.weights.get(nm, 0.0) * row.features.get(nm, 0.0) for nm in names)
        p = ind.sigmoid(z)
        brier_sum += (p - row.label) ** 2
        prob_bins[min(9, int(p * 10))].append((p, row.label))

        decision = _band(p, model.band)
        if decision.value == "HOLD":
            continue
        decisive += 1
        predicted_up = decision.value == "BUY"
        if predicted_up == (row.label == 1):
            correct += 1

    calibration = [
        {
            "p_mean": round(sum(p for p, _ in b) / len(b), 4),
            "up_rate": round(sum(y for _, y in b) / len(b), 4),
            "n": len(b),
        }
        for b in prob_bins
        if b
    ]

    return {
        "n": n,
        "base_rate": round(sum(r.label for r in rows) / n, 4),
        "decisive": decisive,
        "coverage": round(decisive / n, 4),
        "directional_accuracy": round(correct / decisive, 4) if decisive else None,
        "brier": round(brier_sum / n, 4),
        "calibration": calibration,
    }
