"""Pure value objects for the agentic conversation.

These are the vocabulary of the tool-calling loop — tool specs, remembered
turns, and the events the loop streams. They live in the domain because they are
pure data with no I/O and are shared by the application ports *and* the domain's
tool rendering; keeping them here avoids a domain→application dependency.

``application.ports`` re-exports them, so callers can keep importing the whole
agent vocabulary from one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True, slots=True)
class Turn:
    """One prior message in the session, as plain text.

    Only user and assistant *text* is remembered across requests — the internal
    tool-call/tool-result blocks of a single answer are ephemeral, because each
    new question re-runs the tools against fresh live market data rather than
    replaying a stale reading.
    """

    role: Literal["user", "assistant"]
    text: str


@dataclass(frozen=True, slots=True)
class SkillsSelected:
    """The skills the planner chose for this turn, surfaced so the UI can show them."""

    titles: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TextDelta:
    """A chunk of the model's user-facing answer, as it streams."""

    text: str


@dataclass(frozen=True, slots=True)
class ToolStarted:
    """The model called a tool; surfaced so the UI can show what Hella is doing."""

    name: str
    title: str


@dataclass(frozen=True, slots=True)
class ToolFinished:
    name: str


@dataclass(frozen=True, slots=True)
class AgentDone:
    """The loop finished. ``text`` is the complete assistant answer."""

    text: str


# What ``run_agent`` streams. A small tagged union the transport renders to SSE.
AgentEvent = SkillsSelected | TextDelta | ToolStarted | ToolFinished | AgentDone


@dataclass(frozen=True, slots=True)
class Session:
    """A conversation's short-lived memory."""

    id: str
    turns: tuple[Turn, ...] = field(default_factory=tuple)
