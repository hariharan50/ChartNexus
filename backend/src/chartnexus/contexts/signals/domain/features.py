"""The feature vector the calibrated engine reasons over.

Where the legacy engine read three hand-scored skills off one instant, the new
engine reads a **named feature vector** derived from the same inputs plus the
intraday archive time-series and a longer candle history. The vector is computed
once; each horizon's model applies its own learned weights to it.

Pure: raw numbers in (`FeatureInputs`), a `FeatureVector` out, using only the
shared indicator maths. The infrastructure feature-builder fetches the raw data
(chain, archive series, OHLC) and calls :func:`compute`. Every feature is
optional at source — a missing input simply omits that feature, and the ensemble
treats an absent feature as neutral, scaled down by `coverage`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from chartnexus.shared_kernel.domain import indicators as ind

# Canonical feature order — the model artifact's weights are keyed by these names,
# so adding a feature is append-only and never renumbers an existing weight.
FEATURE_NAMES: tuple[str, ...] = (
    # price / technical (intraday)
    "ret_5",
    "ret_20",
    "rsi_norm",
    "ema_gap",
    "vwap_gap",
    "adx",
    "bb_width",
    "realized_vol",
    "range_pos",
    # swing (daily)
    "daily_ret_3",
    "daily_rsi_norm",
    # oi / flow
    "pcr_level",
    "pcr_velocity",
    "buildup_bias",
    "gex_sign",
    # levels (signed distance, spot above = positive)
    "dist_max_pain",
    "dist_call_wall",
    "dist_put_wall",
    "dist_gamma_flip",
    # volatility
    "iv_pct",
    "atm_skew",
)

# ADX above this reads as a trending market; below the lower bound, rangebound.
_ADX_TREND = 25.0


class Regime(StrEnum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGEBOUND = "rangebound"


@dataclass(frozen=True, slots=True)
class FeatureInputs:
    """Raw, adapter-free inputs the feature builder assembles for one instant."""

    spot: float
    # Intraday OHLCV, oldest bar first.
    closes: tuple[float, ...] = ()
    highs: tuple[float, ...] = ()
    lows: tuple[float, ...] = ()
    volumes: tuple[float, ...] = ()
    # Daily closes/highs/lows for the swing view, oldest first.
    daily_closes: tuple[float, ...] = ()
    daily_highs: tuple[float, ...] = ()
    daily_lows: tuple[float, ...] = ()
    # Recent PCR readings from the intraday archive, oldest first (for velocity).
    pcr_series: tuple[float, ...] = ()
    call_oi_chg: int | None = None
    put_oi_chg: int | None = None
    gex_net: float | None = None
    # Levels.
    max_pain: float | None = None
    call_wall: float | None = None
    put_wall: float | None = None
    gamma_flip: float | None = None
    # Volatility.
    iv_percentile: float | None = None
    atm_call_iv: float | None = None
    atm_put_iv: float | None = None


@dataclass(frozen=True, slots=True)
class FeatureVector:
    """The computed features (only those with data) plus the regime read."""

    values: dict[str, float]
    regime: Regime
    #: Fraction of ``FEATURE_NAMES`` that had data — scales the ensemble's confidence.
    coverage: float
    details: tuple[str, ...] = field(default_factory=tuple)

    def get(self, name: str) -> float | None:
        return self.values.get(name)


def compute(inp: FeatureInputs) -> FeatureVector:
    v: dict[str, float] = {}

    _price_features(inp, v)
    _swing_features(inp, v)
    _flow_features(inp, v)
    _level_features(inp, v)
    _vol_features(inp, v)

    coverage = len(v) / len(FEATURE_NAMES)
    return FeatureVector(values=v, regime=_regime(v), coverage=round(coverage, 3))


# -- feature groups ---------------------------------------------------------


def _price_features(inp: FeatureInputs, v: dict[str, float]) -> None:
    closes, highs, lows = inp.closes, inp.highs, inp.lows
    _put(v, "ret_5", ind.slope_pct(closes, 5))
    _put(v, "ret_20", ind.slope_pct(closes, 20))

    rsi = ind.rsi(closes, 14)
    if rsi is not None:
        v["rsi_norm"] = (rsi - 50.0) / 50.0

    ema20, ema50 = ind.ema(closes, 20), ind.ema(closes, 50)
    if ema20 is not None and ema50 is not None and inp.spot > 0:
        v["ema_gap"] = (ema20 - ema50) / inp.spot

    vwap = ind.vwap(highs, lows, closes, inp.volumes)
    if vwap is not None and inp.spot > 0:
        v["vwap_gap"] = (inp.spot - vwap) / inp.spot

    _put(v, "adx", _scaled(ind.adx(highs, lows, closes, 14), 100.0))
    _put(v, "bb_width", ind.bollinger_width(closes, 20))
    _put(v, "realized_vol", ind.realized_vol(closes, 20))

    hi = ind.recent_max(highs, 20)
    lo = ind.recent_min(lows, 20)
    if hi is not None and lo is not None and hi > lo:
        v["range_pos"] = ((inp.spot - lo) / (hi - lo)) * 2.0 - 1.0


def _swing_features(inp: FeatureInputs, v: dict[str, float]) -> None:
    _put(v, "daily_ret_3", ind.slope_pct(inp.daily_closes, 3))
    rsi = ind.rsi(inp.daily_closes, 14)
    if rsi is not None:
        v["daily_rsi_norm"] = (rsi - 50.0) / 50.0


def _flow_features(inp: FeatureInputs, v: dict[str, float]) -> None:
    if inp.pcr_series:
        pcr = inp.pcr_series[-1]
        if pcr > 0:
            # Centred on 1.0 (balanced), clamped so extremes don't dominate.
            v["pcr_level"] = ind.clamp(pcr - 1.0)
        vel = ind.slope_pct(inp.pcr_series, min(6, len(inp.pcr_series) - 1))
        _put(v, "pcr_velocity", None if vel is None else ind.clamp(vel * 5.0))

    if inp.call_oi_chg is not None and inp.put_oi_chg is not None:
        total = abs(inp.call_oi_chg) + abs(inp.put_oi_chg)
        if total > 0:
            # Puts building (positive) is supportive/bullish; calls building bearish.
            v["buildup_bias"] = (inp.put_oi_chg - inp.call_oi_chg) / total

    if inp.gex_net is not None:
        v["gex_sign"] = 1.0 if inp.gex_net > 0 else -1.0 if inp.gex_net < 0 else 0.0


def _level_features(inp: FeatureInputs, v: dict[str, float]) -> None:
    if inp.spot <= 0:
        return
    _put(v, "dist_max_pain", _dist(inp.spot, inp.max_pain))
    _put(v, "dist_call_wall", _dist(inp.spot, inp.call_wall))
    _put(v, "dist_put_wall", _dist(inp.spot, inp.put_wall))
    _put(v, "dist_gamma_flip", _dist(inp.spot, inp.gamma_flip))


def _vol_features(inp: FeatureInputs, v: dict[str, float]) -> None:
    if inp.iv_percentile is not None:
        v["iv_pct"] = (inp.iv_percentile / 100.0) * 2.0 - 1.0
    ce, pe = inp.atm_call_iv, inp.atm_put_iv
    if ce is not None and pe is not None and (ce + pe) > 0:
        v["atm_skew"] = ind.clamp((pe - ce) / ((ce + pe) / 2.0))


def _regime(v: dict[str, float]) -> Regime:
    adx = v.get("adx")  # already 0-1
    direction = v.get("ema_gap") or v.get("ret_20") or v.get("ret_5") or 0.0
    trending = adx is not None and adx * 100.0 >= _ADX_TREND
    if not trending:
        return Regime.RANGEBOUND
    return Regime.TRENDING_UP if direction >= 0 else Regime.TRENDING_DOWN


# -- helpers ----------------------------------------------------------------


def _put(v: dict[str, float], name: str, value: float | None) -> None:
    if value is not None:
        v[name] = value


def _scaled(value: float | None, by: float) -> float | None:
    return None if value is None else value / by


def _dist(spot: float, level: float | None) -> float | None:
    return None if level is None or level <= 0 else (spot - level) / spot
