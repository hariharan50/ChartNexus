"""The pure decision pipeline: a snapshot in, a Guidance out.

One function ties the skills, the fusion and the risk gate together with no I/O,
so the entire judgement — call, confidence, scaffold, provenance handling — is
exercised by a single unit test against a hand-built ``MarketSnapshot``. The
application layer only adds fetching the snapshot and persisting the result.
"""

from __future__ import annotations

from chartnexus.contexts.signals.domain import (
    ensemble,
    features,
    fusion,
    rationale,
    trade_scaffold,
)
from chartnexus.contexts.signals.domain.ensemble import ModelArtifact
from chartnexus.contexts.signals.domain.features import FeatureInputs, FeatureVector
from chartnexus.contexts.signals.domain.indicators import atr
from chartnexus.contexts.signals.domain.inputs import MarketSnapshot
from chartnexus.contexts.signals.domain.models import (
    Decision,
    Guidance,
    Horizon,
    HorizonCall,
    MarketContext,
    MultiHorizonGuidance,
)
from chartnexus.contexts.signals.domain.skills import (
    level_based,
    oi_analysis,
    price_action,
    risk_management,
)

# The horizons the engine reports, in display order.
_HORIZONS = (Horizon.INTRADAY, Horizon.END_OF_DAY, Horizon.SWING)


def build_guidance(snap: MarketSnapshot) -> Guidance:
    levels = level_based.build_levels(snap)

    oi_read = oi_analysis.analyse(snap)
    price_read = price_action.analyse(snap)
    level_read = level_based.analyse(snap, levels)

    fused = fusion.fuse([oi_read, price_read, level_read])

    atr_value = atr(snap.highs, snap.lows, snap.closes)
    scaffold = trade_scaffold.build_scaffold(fused.decision, snap, levels, atr_value)

    risk = risk_management.assess(fused.decision, scaffold, snap.provenance, fused.confidence)

    # Card order matches the console layout: the three voters, then the gate.
    skills = (oi_read, price_read, level_read, risk.read)
    rule_based = rationale.summarise(fused.decision, risk.confidence, snap.symbol, skills)

    return Guidance(
        symbol=snap.symbol,
        decision=fused.decision,
        confidence=risk.confidence,
        score=fused.score,
        provenance=snap.provenance,
        skills=skills,
        levels=levels,
        scaffold=scaffold,
        rationale=rule_based,
        expiry_ref=snap.expiry_date,
        is_actionable=risk.is_actionable,
        warnings=risk.warnings,
    )


def build_multi_horizon(snap: MarketSnapshot, artifact: ModelArtifact) -> MultiHorizonGuidance:
    """The calibrated engine: a feature vector, one call per horizon, shared context.

    Replaces the three-skill vote with a feature-and-model read, while reusing the
    still-good level, scaffold and risk-gate machinery. The intraday call is the
    headline; the risk gate (provenance, geometry) sets actionability and warnings.
    """
    fv = features.compute(_to_inputs(snap))
    calls = tuple(
        ensemble.evaluate(fv, horizon, artifact.models[horizon])
        for horizon in _HORIZONS
        if horizon in artifact.models
    )
    headline = next(
        (c for c in calls if c.horizon is Horizon.INTRADAY), calls[0] if calls else None
    )

    levels = level_based.build_levels(snap)
    atr_value = atr(snap.highs, snap.lows, snap.closes)
    decision = headline.decision if headline else _hold(fv).decision
    confidence = headline.confidence if headline else 0
    scaffold = trade_scaffold.build_scaffold(decision, snap, levels, atr_value)
    risk = risk_management.assess(decision, scaffold, snap.provenance, confidence)

    return MultiHorizonGuidance(
        symbol=snap.symbol,
        calls=calls,
        regime=fv.regime.value,
        provenance=snap.provenance,
        levels=levels,
        scaffold=scaffold,
        rationale=_rationale(snap.symbol, calls, fv),
        context=MarketContext(
            india_vix=snap.india_vix,
            india_vix_change_percent=snap.india_vix_change_percent,
            pcr=snap.pcr,
        ),
        expiry_ref=snap.expiry_date,
        is_actionable=risk.is_actionable,
        warnings=risk.warnings,
    )


def _to_inputs(snap: MarketSnapshot) -> FeatureInputs:
    # Fall back to the current PCR as a one-point series when the archive is cold.
    pcr_series = snap.pcr_series or ((snap.pcr,) if snap.pcr else ())
    return FeatureInputs(
        spot=snap.spot,
        closes=snap.closes,
        highs=snap.highs,
        lows=snap.lows,
        volumes=snap.volumes,
        daily_closes=snap.daily_closes,
        daily_highs=snap.daily_highs,
        daily_lows=snap.daily_lows,
        pcr_series=pcr_series,
        call_oi_chg=snap.total_call_oi_chg,
        put_oi_chg=snap.total_put_oi_chg,
        gex_net=snap.gex_net,
        max_pain=snap.max_pain,
        call_wall=snap.call_wall,
        put_wall=snap.put_wall,
        gamma_flip=snap.gamma_flip,
        iv_percentile=snap.iv_percentile,
        atm_call_iv=snap.atm_call_iv,
        atm_put_iv=snap.atm_put_iv,
    )


def _hold(fv: FeatureVector) -> HorizonCall:
    _ = fv
    return HorizonCall(
        horizon=Horizon.INTRADAY, decision=Decision.HOLD, probability=0.5, confidence=0
    )


def _rationale(symbol: str, calls: tuple[HorizonCall, ...], fv: FeatureVector) -> str:
    if not calls:
        return f"No read on {symbol} — not enough data this session."
    parts = [
        f"{c.horizon.value.replace('_', ' ')}: {c.decision.value} ({c.confidence}%)" for c in calls
    ]
    return f"{symbol} — {', '.join(parts)}. Regime: {fv.regime.value.replace('_', ' ')}."
