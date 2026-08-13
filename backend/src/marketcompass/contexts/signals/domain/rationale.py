"""The always-available "why" — a deterministic, no-LLM explanation.

Every guidance ships with this string so the console reads sensibly with no API
key. The ``copilot`` context may later replace it with richer LLM prose, but the
engine never depends on that: the rule-based line is the floor, not a fallback.
"""

from __future__ import annotations

from marketcompass.contexts.signals.domain.models import Decision, Guidance, SkillRead


def summarise(
    decision: Decision,
    confidence: int,
    symbol: str,
    skills: tuple[SkillRead, ...],
) -> str:
    verb = {
        Decision.BUY: "leans bullish",
        Decision.SELL: "leans bearish",
        Decision.HOLD: "has no clear edge",
    }[decision]

    lead = f"{symbol} {verb} ({confidence}% confidence)."

    # Name the loudest voting skills, strongest first, so the sentence explains
    # itself rather than just asserting a label.
    voting = sorted(
        (skill for skill in skills if skill.votes),
        key=lambda skill: abs(skill.score or 0.0),
        reverse=True,
    )
    reasons = [skill.headline for skill in voting[:2] if skill.headline]
    if reasons:
        return lead + " " + " ".join(reasons)
    return lead + " No skill had enough data to take a side."


def enrich(guidance: Guidance) -> str:
    """A slightly longer rule-based paragraph for the guidance detail panel."""
    lines = [guidance.rationale]
    levels = guidance.levels
    if levels.support is not None and levels.resistance is not None:
        lines.append(
            f"Watching support at {levels.support:,.0f} and resistance at {levels.resistance:,.0f}."
        )
    if guidance.scaffold.entry is not None:
        parts = [f"Entry near {guidance.scaffold.entry:,.0f}"]
        if guidance.scaffold.stop is not None:
            parts.append(f"stop {guidance.scaffold.stop:,.0f}")
        if guidance.scaffold.target is not None:
            parts.append(f"target {guidance.scaffold.target:,.0f}")
        lines.append(", ".join(parts) + ".")
    return " ".join(lines)
