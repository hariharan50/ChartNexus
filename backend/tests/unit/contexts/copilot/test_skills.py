"""The skill registry: selection, tool scoping, and prompt composition.

Pure logic, no model — these are the guarantees the planner and executor rely on:
selection stays within known skills, tool scoping is the union of the chosen
skills, and the composed prompt only carries the chosen skills' instructions.
"""

from __future__ import annotations

from marketcompass.contexts.copilot.domain import persona, skills


def test_default_ids_are_all_known() -> None:
    assert set(skills.DEFAULT_IDS) <= set(skills.skill_ids())


def test_valid_ids_filters_unknown_and_dedupes_in_registry_order() -> None:
    got = skills.valid_ids(
        ["nonsense", "price_action_technical", "oi_options_flow", "oi_options_flow"]
    )
    # Registry order (oi before price_action), unknown dropped, no duplicates.
    assert got == ["oi_options_flow", "price_action_technical"]


def test_tools_for_is_the_union_of_selected_skills() -> None:
    tools = skills.tools_for(["oi_options_flow"])
    assert skills.GET_OPTION_CHAIN_SUMMARY in tools
    assert skills.GET_MAX_PAIN_AND_PCR in tools
    # A price-action-only tool is not pulled in by an OI skill.
    assert skills.GET_PREVIOUS_DAY_OHLC not in tools


def test_conversational_skill_has_no_tools() -> None:
    assert skills.tools_for([skills.CONVERSATIONAL_ID]) == set()


def test_instructions_block_only_covers_selected_skills() -> None:
    block = skills.instructions_block(["price_action_technical"])
    assert "Price Action" in block
    assert "max pain" not in block.lower()


def test_compose_system_folds_in_selected_skills() -> None:
    system = persona.compose_system(
        skills.titles_for(["oi_options_flow"]),
        skills.instructions_block(["oi_options_flow"]),
    )
    assert "Hella" in system  # base persona present
    assert "OI & Options Flow" in system  # the selected skill named
    assert "not investment advice" in system.lower()  # compliance retained


def test_compose_system_with_no_skills_is_just_the_base() -> None:
    assert persona.compose_system([], "") == persona.compose_system([], "")
    assert "Hella" in persona.compose_system([], "")
