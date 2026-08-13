"""The compliance guardrail — the non-bypassable floor on what Hella ships.

Pure and deterministic: the persona already tells the model to frame everything
as educational, but a system prompt is guidance, not a guarantee. On a market
turn the agent runs the answer through :func:`needs_disclaimer` and appends
:data:`DISCLAIMER` when the model didn't already carry it — so no analytical
answer ever leaves without the "not investment advice" framing, regardless of
what the model wrote.

Kept in the domain so it is unit-testable without a model, and so the exact
wording lives in one place.
"""

from __future__ import annotations

DISCLAIMER = (
    "A gentle reminder: this is educational market analysis, not investment advice or a "
    "personalised recommendation."
)

# Phrases that mean the answer already carries the compliance framing, so a
# second line would just be noise.
_ALREADY_PRESENT = (
    "not investment advice",
    "not financial advice",
    "educational market analysis",
    "not a personalised recommendation",
    "not a personalized recommendation",
)


def needs_disclaimer(answer: str) -> bool:
    """True when a non-empty answer doesn't already carry the compliance framing."""
    text = answer.strip().lower()
    if not text:
        return False
    return not any(marker in text for marker in _ALREADY_PRESENT)
