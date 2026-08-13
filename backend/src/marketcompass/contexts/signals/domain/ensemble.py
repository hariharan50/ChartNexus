"""The calibrated logistic ensemble — a feature vector to a per-horizon call.

Each horizon has a :class:`HorizonModel`: a weight per feature, a bias, a decision
band, and a calibration table. The score is a plain logistic —
``p = sigmoid(bias + Σ wᵢ·featureᵢ)`` — banded into BUY / SELL / HOLD, with a
**confidence that is calibrated**: the raw signal strength is mapped through the
fitted calibration table to the *measured* hit-rate, then scaled by how much of
the feature vector actually had data.

The weights ship as a hand-set default (`default_artifact`) so the engine is
sensible before any fit; the backtest CLI fits and overwrites them from real
history. `to_dict`/`from_dict` keep the artifact JSON-round-trippable so a fitted
model is just a file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

from marketcompass.contexts.signals.domain.features import FeatureVector
from marketcompass.contexts.signals.domain.models import Decision, Horizon, HorizonCall
from marketcompass.shared_kernel.domain import indicators as ind

_ARTIFACT_VERSION = 1
# How many strongest features to surface as the call's drivers.
_N_DRIVERS = 4


@dataclass(frozen=True, slots=True)
class HorizonModel:
    weights: dict[str, float]
    bias: float = 0.0
    #: p must clear 0.5 ± band to be a BUY/SELL rather than HOLD.
    band: float = 0.06
    #: Ascending (strength, hit_rate) points; empty means "uncalibrated" — use the
    #: raw strength as the confidence. Filled by the fit step.
    calibration: tuple[tuple[float, float], ...] = ()


@dataclass(frozen=True, slots=True)
class ModelArtifact:
    models: dict[Horizon, HorizonModel]
    version: int = _ARTIFACT_VERSION
    trained_at: str | None = None
    data_range: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "trained_at": self.trained_at,
            "data_range": self.data_range,
            "metrics": self.metrics,
            "models": {
                h.value: {
                    "weights": m.weights,
                    "bias": m.bias,
                    "band": m.band,
                    "calibration": [list(p) for p in m.calibration],
                }
                for h, m in self.models.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelArtifact:
        models = {
            Horizon(name): HorizonModel(
                weights={k: float(v) for k, v in spec["weights"].items()},
                bias=float(spec.get("bias", 0.0)),
                band=float(spec.get("band", 0.06)),
                calibration=tuple((float(a), float(b)) for a, b in spec.get("calibration", [])),
            )
            for name, spec in data["models"].items()
        }
        return cls(
            models=models,
            version=int(data.get("version", _ARTIFACT_VERSION)),
            trained_at=data.get("trained_at"),
            data_range=data.get("data_range"),
            metrics=data.get("metrics", {}),
        )


def evaluate(fv: FeatureVector, horizon: Horizon, model: HorizonModel) -> HorizonCall:
    """Score one horizon: probability, banded decision, calibrated confidence."""
    z = model.bias
    contributions: list[tuple[str, float]] = []
    for name, weight in model.weights.items():
        value = fv.get(name)
        if value is None:
            continue
        term = weight * value
        z += term
        contributions.append((name, term))

    p = ind.sigmoid(z)
    decision = _band(p, model.band)
    strength = min(1.0, abs(p - 0.5) * 2.0)
    calibrated = _calibrate(strength, model.calibration)
    # A thin feature vector is a less trustworthy call — never full confidence.
    confidence = round(100.0 * calibrated * (0.4 + 0.6 * fv.coverage))

    drivers = tuple(
        name
        for name, _ in sorted(contributions, key=lambda kv: abs(kv[1]), reverse=True)[:_N_DRIVERS]
    )
    return HorizonCall(
        horizon=horizon,
        decision=decision,
        probability=round(p, 4),
        confidence=int(confidence),
        drivers=drivers,
    )


def _band(p: float, band: float) -> Decision:
    if p > 0.5 + band:
        return Decision.BUY
    if p < 0.5 - band:
        return Decision.SELL
    return Decision.HOLD


def _calibrate(strength: float, table: tuple[tuple[float, float], ...]) -> float:
    """Map raw signal strength to a calibrated hit-rate via the fitted table.

    Empty table → identity (the pre-calibration behaviour). Otherwise piecewise-
    linear interpolation over the ascending points.
    """
    if not table:
        return strength
    if strength <= table[0][0]:
        return table[0][1]
    if strength >= table[-1][0]:
        return table[-1][1]
    for (x0, y0), (x1, y1) in pairwise(table):
        if x0 <= strength <= x1 and x1 > x0:
            return y0 + (y1 - y0) * (strength - x0) / (x1 - x0)
    return strength


# -- default (pre-fit) weights ----------------------------------------------
# Hand-set directional priors, magnitudes chosen for the feature scales. Positive
# weight = bullish contribution. The fit step replaces these from real history.

_INTRADAY = HorizonModel(
    weights={
        "ret_5": 30.0,
        "ret_20": 10.0,
        "rsi_norm": 0.3,
        "ema_gap": 20.0,
        "vwap_gap": 25.0,
        "range_pos": 0.2,
        "pcr_level": 0.3,
        "pcr_velocity": 0.7,
        "buildup_bias": 0.7,
        "gex_sign": 0.3,
        "dist_max_pain": -12.0,
        "dist_call_wall": -8.0,
        "dist_put_wall": 6.0,
        "dist_gamma_flip": 5.0,
        "iv_pct": -0.2,
        "atm_skew": -0.4,
    }
)

_END_OF_DAY = HorizonModel(
    weights={
        "ret_5": 12.0,
        "ret_20": 18.0,
        "rsi_norm": 0.4,
        "ema_gap": 25.0,
        "vwap_gap": 12.0,
        "range_pos": 0.3,
        "pcr_level": 0.5,
        "pcr_velocity": 0.5,
        "buildup_bias": 0.6,
        "gex_sign": 0.3,
        "daily_ret_3": 4.0,
        "dist_max_pain": -18.0,
        "dist_call_wall": -10.0,
        "dist_put_wall": 8.0,
        "dist_gamma_flip": 6.0,
        "iv_pct": -0.3,
        "atm_skew": -0.5,
    }
)

_SWING = HorizonModel(
    weights={
        "ret_20": 8.0,
        "rsi_norm": 0.2,
        "ema_gap": 30.0,
        "range_pos": 0.2,
        "pcr_level": 0.6,
        "buildup_bias": 0.4,
        "gex_sign": 0.2,
        "daily_ret_3": 10.0,
        "daily_rsi_norm": 0.6,
        "dist_max_pain": -8.0,
        "dist_call_wall": -6.0,
        "dist_put_wall": 6.0,
        "iv_pct": -0.4,
        "atm_skew": -0.5,
    }
)


def default_artifact() -> ModelArtifact:
    return ModelArtifact(
        models={
            Horizon.INTRADAY: _INTRADAY,
            Horizon.END_OF_DAY: _END_OF_DAY,
            Horizon.SWING: _SWING,
        },
        trained_at=None,
        data_range="hand-set defaults (unfitted)",
    )
