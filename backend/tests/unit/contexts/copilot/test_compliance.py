"""The compliance guardrail — when the disclaimer must be appended."""

from __future__ import annotations

from marketcompass.contexts.copilot.domain import compliance, skills


def test_empty_answer_needs_nothing() -> None:
    assert compliance.needs_disclaimer("") is False
    assert compliance.needs_disclaimer("   ") is False


def test_plain_answer_needs_the_disclaimer() -> None:
    assert compliance.needs_disclaimer("NIFTY leans balanced with support at 24,300.") is True


def test_answer_that_already_frames_it_is_left_alone() -> None:
    assert compliance.needs_disclaimer("... and remember, this is not investment advice.") is False
    assert compliance.needs_disclaimer("This is educational market analysis only.") is False


def test_the_disclaimer_itself_satisfies_the_check() -> None:
    # Appending it once must make a second pass a no-op (no double-append).
    assert compliance.needs_disclaimer(compliance.DISCLAIMER) is False


def test_analytical_turns_are_guarded_but_conversation_is_not() -> None:
    assert skills.is_analytical(["oi_options_flow"]) is True
    assert skills.is_analytical(["price_action_technical", skills.CONVERSATIONAL_ID]) is True
    assert skills.is_analytical([skills.CONVERSATIONAL_ID]) is False
    assert skills.is_analytical([]) is False
