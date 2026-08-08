"""The pure decision pipeline: a snapshot in, a Guidance out.

One function ties the skills, the fusion and the risk gate together with no I/O,
so the entire judgement — call, confidence, scaffold, provenance handling — is
exercised by a single unit test against a hand-built ``MarketSnapshot``. The
application layer only adds fetching the snapshot and persisting the result.
"""

from __future__ import annotations

from marketcompass.contexts.signals.domain import fusion, rationale, trade_scaffold
from marketcompass.contexts.signals.domain.indicators import atr
from marketcompass.contexts.signals.domain.inputs import MarketSnapshot
from marketcompass.contexts.signals.domain.models import Guidance
from marketcompass.contexts.signals.domain.skills import (
    level_based,
    oi_analysis,
    price_action,
    risk_management,
)


def build_guidance(snap: MarketSnapshot) -> Guidance:
    levels = level_based.build_levels(snap)

    oi_read = oi_analysis.analyse(snap)
    price_read = price_action.analyse(snap)
    level_read = level_based.analyse(snap, levels)

    fused = fusion.fuse([oi_read, price_read, level_read])

    atr_value = atr(snap.highs, snap.lows, snap.closes)
    scaffold = trade_scaffold.build_scaffold(fused.decision, snap, levels, atr_value)

    risk = risk_management.assess(
        fused.decision, scaffold, snap.provenance, fused.confidence
    )

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
