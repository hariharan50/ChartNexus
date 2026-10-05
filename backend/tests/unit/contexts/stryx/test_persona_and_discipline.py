"""STRYX's system prompt and discipline rules are assembled from the domain.

Pins that the composed prompt carries the whole frame — the five-style playbook,
the output contract, the discipline rules — and that the hard daily-cap notice is
injected only when the cap is actually reached.
"""

from __future__ import annotations

from chartnexus.contexts.stryx.domain import discipline, entry_styles, persona
from chartnexus.contexts.stryx.domain.call_template import CONTRACT


def test_prompt_carries_playbook_contract_and_discipline() -> None:
    system = persona.compose_system(cap_reached=False)
    for title in entry_styles.titles():
        assert title in system
    assert "[STRYX CALL]" in CONTRACT
    assert CONTRACT.split("\n", 1)[0] in system
    assert "No stop = no call" in system
    assert f"{discipline.MAX_LIVE_CALLS_PER_DAY} LIVE calls" in system


def test_cap_notice_only_when_reached() -> None:
    assert "ALREADY REACHED" not in persona.compose_system(cap_reached=False)
    assert "ALREADY REACHED" in persona.compose_system(cap_reached=True)


def test_daily_cap_is_two() -> None:
    assert discipline.MAX_LIVE_CALLS_PER_DAY == 2


def test_five_entry_styles() -> None:
    assert len(entry_styles.ENTRY_STYLES) == 5
    assert len(entry_styles.titles()) == 5
