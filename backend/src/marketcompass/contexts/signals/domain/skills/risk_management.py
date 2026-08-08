"""Risk Management skill — the gate, not a vote.

The other three skills argue direction; this one decides whether the resulting
call is fit to show as actionable and shapes its confidence:

* **Provenance gate** — a call built on any mock data is never tradeable. It is
  still shown (the engine ran), but flagged illustrative and its confidence is
  floored, so a simulated session can never surface a confident BUY.
* **Reward-for-risk** — a sub-1 R:R trade is a bad trade however strong the
  bias; confidence is trimmed and the setup called out.

It renders a fourth card on the console but casts no directional vote (weight 0).
"""

from __future__ import annotations

from dataclasses import dataclass

from marketcompass.contexts.signals.domain.models import (
    Decision,
    Provenance,
    SkillRead,
    TradeScaffold,
)

WEIGHT = 0.0
_LABEL = "Risk Management"
_SKILL = "risk_management"

# A mock-tainted call cannot be trusted past this confidence, no matter how
# strong the underlying score looked.
_MOCK_CONFIDENCE_CEILING = 15
_MIN_RISK_REWARD = 1.0


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    read: SkillRead
    is_actionable: bool
    confidence: int
    warnings: tuple[str, ...]


def assess(
    decision: Decision,
    scaffold: TradeScaffold,
    provenance: Provenance,
    confidence: int,
) -> RiskAssessment:
    warnings: list[str] = []
    details: list[str] = []
    actionable = True
    adjusted = confidence

    if not provenance.is_real:
        actionable = False
        adjusted = min(adjusted, _MOCK_CONFIDENCE_CEILING)
        warnings.append("Built on simulated data — illustrative only, not tradeable.")
        details.append("Provenance is mock; call downgraded.")

    rr = scaffold.risk_reward
    if rr is not None and rr < _MIN_RISK_REWARD:
        adjusted = round(adjusted * 0.7)
        warnings.append(f"Reward-to-risk {rr:.2f} is below 1 — poor trade geometry.")
        details.append(f"R:R {rr:.2f} < 1.0.")
    elif rr is not None:
        details.append(f"R:R {rr:.2f}.")

    headline = _headline(decision, scaffold, actionable)
    read = SkillRead(
        skill=_SKILL,
        label=_LABEL,
        weight=WEIGHT,
        score=None,
        headline=headline,
        details=tuple(details),
    )
    return RiskAssessment(
        read=read,
        is_actionable=actionable,
        confidence=adjusted,
        warnings=tuple(warnings),
    )


def _headline(decision: Decision, scaffold: TradeScaffold, actionable: bool) -> str:
    if decision is Decision.HOLD:
        return "No position — waiting for a cleaner setup."
    if not actionable:
        return "Illustrative only — simulated data."
    bits: list[str] = []
    if scaffold.stop is not None:
        bits.append(f"stop {scaffold.stop:,.0f}")
    if scaffold.risk_reward is not None:
        bits.append(f"R:R {scaffold.risk_reward:.1f}")
    return " · ".join(bits) if bits else "Manage risk to the nearest level."
