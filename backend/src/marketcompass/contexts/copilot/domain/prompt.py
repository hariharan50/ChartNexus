"""Pure prompt construction for the guider agent.

Builds the system persona and a structured market-state context block from a
``GuidanceSnapshot``. No I/O, no LLM — just string assembly, so the exact grounding
handed to the model is unit-testable and identical across providers.
"""

from __future__ import annotations

from marketcompass.contexts.copilot.domain.models import GuidanceSnapshot

_SYSTEM = (
    "You are Hella, MarketCompass's trading guider — a calm, soft-spoken, and articulate "
    "companion who specialises in Indian index options. You speak gently and warmly, like a "
    "thoughtful mentor: patient, encouraging, and reassuring, never brash or pushy. You "
    "reason from four skills: OI Analysis, Price Action, Level-Based Trading, and Risk "
    "Management. Answer the user's question about the current setup in 2-4 short, graceful "
    "sentences, grounded ONLY in the structured state provided — never invent numbers. Be "
    "clear and kind, and keep the person's composure in mind. This is an algorithmic signal, "
    "not investment advice, and you must never present it as a personalised recommendation. "
    "If the data is simulated (mock provenance), gently note that and treat the call as "
    "illustrative. You may refer to yourself as Hella when it feels natural."
)


def system_prompt() -> str:
    return _SYSTEM


def context_block(snapshot: GuidanceSnapshot) -> str:
    """The structured state the model must ground its answer in."""
    lines = [
        f"Instrument: {snapshot.symbol}",
        f"Call: {snapshot.decision} at {snapshot.confidence}% confidence",
        f"Data provenance: {snapshot.provenance} "
        f"({'tradeable' if snapshot.is_actionable else 'illustrative only'})",
        f"Engine rationale: {snapshot.rationale}",
    ]
    for skill in snapshot.skills:
        score = "n/a" if skill.score is None else f"{skill.score:+.2f}"
        lines.append(f"- {skill.label} [{score}]: {skill.headline}")
    if snapshot.support is not None or snapshot.resistance is not None:
        lines.append(
            f"Levels: support {_fmt(snapshot.support)}, resistance {_fmt(snapshot.resistance)}"
        )
    if snapshot.entry is not None:
        lines.append(
            "Scaffold (illustrative): "
            f"entry {_fmt(snapshot.entry)}, stop {_fmt(snapshot.stop)}, "
            f"target {_fmt(snapshot.target)}"
        )
    if snapshot.suggested_contract:
        lines.append(f"Suggested contract: {snapshot.suggested_contract}")
    for warning in snapshot.warnings:
        lines.append(f"Warning: {warning}")
    return "\n".join(lines)


def _fmt(value: float | None) -> str:
    return "unknown" if value is None else f"{value:,.0f}"
