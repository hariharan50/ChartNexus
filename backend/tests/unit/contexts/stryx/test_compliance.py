"""STRYX's compliance floor flags an answer that lacks the 'not advice' framing."""

from __future__ import annotations

from chartnexus.contexts.stryx.domain import compliance


def test_needs_disclaimer_when_missing() -> None:
    assert compliance.needs_disclaimer("[STRYX CALL]\nStatus: LIVE\nEntry: 100") is True


def test_no_disclaimer_when_already_present() -> None:
    assert compliance.needs_disclaimer("This is educational, paper-trade only.") is False


def test_empty_answer_needs_nothing() -> None:
    assert compliance.needs_disclaimer("   ") is False
