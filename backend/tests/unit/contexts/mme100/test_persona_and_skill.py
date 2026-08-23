"""MME100's persona/skill assembly and compliance floor — pure, model-free."""

from __future__ import annotations

from marketcompass.contexts.mme100.domain import compliance, persona, skill


def test_analysis_prompt_folds_in_the_six_section_framework() -> None:
    prompt = persona.compose_analysis()
    assert "Market Made Easy 100%" in prompt
    assert "GLOBAL CUES" in prompt
    assert "RISK FACTORS" in prompt
    # Global cues must be sourced from the web, not invented.
    assert "web search" in prompt.lower()


def test_conversational_prompt_drops_the_framework_and_tools() -> None:
    prompt = persona.compose_conversational()
    assert "NOT asking for an analysis" in prompt
    assert "do NOT call any tools" in prompt


def test_briefing_prompt_names_the_instrument() -> None:
    assert "NIFTY" in persona.briefing_prompt("NIFTY")


def test_section_titles_are_the_six_sections() -> None:
    titles = skill.titles()
    assert len(titles) == 6
    assert titles[0] == "Global Cues"


def test_core_tools_are_the_nine_india_tools_and_exclude_web_search() -> None:
    assert len(skill.CORE_TOOLS) == 9
    assert skill.WEB_SEARCH not in skill.CORE_TOOLS
    assert skill.GET_GAMMA_EXPOSURE in skill.CORE_TOOLS


def test_disclaimer_needed_only_when_absent() -> None:
    assert compliance.needs_disclaimer("Nifty likely opens flat.") is True
    assert compliance.needs_disclaimer("") is False
    assert compliance.needs_disclaimer(f"Read. {compliance.DISCLAIMER}") is False
