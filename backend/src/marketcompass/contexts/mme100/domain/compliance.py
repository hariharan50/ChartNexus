"""MME100's compliance floor — the non-bypassable 'not advice' framing.

A pre-market analysis names specific stocks and levels, so the guardrail matters:
the persona already frames the read as educational, but a prompt is guidance, not
a guarantee. Every analytical answer runs through :func:`needs_disclaimer` and
gets :data:`DISCLAIMER` appended when it is missing. Pure and deterministic so it
is testable without a model.
"""

from __future__ import annotations

DISCLAIMER = (
    "Disclaimer: This analysis is for educational and informational purposes only — "
    "not investment advice or a personalised recommendation. Consult a "
    "SEBI-registered adviser before investing. Markets can move sharply; use strict "
    "stop losses and never overleverage."
)

_ALREADY_PRESENT = (
    "not investment advice",
    "not financial advice",
    "educational",
    "sebi-registered",
    "not a personalised recommendation",
    "not a personalized recommendation",
)


def needs_disclaimer(answer: str) -> bool:
    """True when a non-empty answer doesn't already carry the compliance framing."""
    text = answer.strip().lower()
    if not text:
        return False
    return not any(marker in text for marker in _ALREADY_PRESENT)
