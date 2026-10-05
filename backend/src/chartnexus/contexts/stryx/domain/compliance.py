"""STRYX's compliance floor — the non-bypassable 'not advice' framing.

A STRYX call is a decisive, actionable-looking thing, so the guardrail matters
more here than for a hedged analyst answer: the persona already frames calls as
educational / paper-trade, but a prompt is guidance, not a guarantee. Every call
runs through :func:`needs_disclaimer` and gets :data:`DISCLAIMER` appended when
it is missing. Pure and deterministic so it is testable without a model.
"""

from __future__ import annotations

DISCLAIMER = (
    "Reminder: STRYX calls are educational / paper-trade only — not investment advice or a "
    "personalised recommendation. Trade your own plan and risk."
)

_ALREADY_PRESENT = (
    "not investment advice",
    "not financial advice",
    "paper-trade only",
    "not a personalised recommendation",
    "not a personalized recommendation",
    "educational",
)


def needs_disclaimer(answer: str) -> bool:
    """True when a non-empty answer doesn't already carry the compliance framing."""
    text = answer.strip().lower()
    if not text:
        return False
    return not any(marker in text for marker in _ALREADY_PRESENT)
