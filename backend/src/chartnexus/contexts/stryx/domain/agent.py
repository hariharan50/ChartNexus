"""Pure value objects for STRYX's agentic conversation.

The vocabulary of the tool-calling loop — remembered turns and the events the
loop streams. Structurally the same shape as copilot's, but STRYX keeps its own
copy so the two contexts stay isolated (neither imports the other). ``StryxCall``,
the parsed structured call, lives in :mod:`call_template` alongside its parser.

``application.ports`` re-exports these so callers import the whole vocabulary
from one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True, slots=True)
class Turn:
    """One prior message in the session, as plain text.

    Only user/assistant *text* is remembered across requests — a single answer's
    internal tool-call blocks are ephemeral, because each new question re-reads
    the live market rather than replaying a stale snapshot.
    """

    role: Literal["user", "assistant"]
    text: str


@dataclass(frozen=True, slots=True)
class StylesConsidered:
    """The entry styles STRYX weighs this turn, surfaced so the UI can show them."""

    titles: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TextDelta:
    """A chunk of STRYX's user-facing answer, as it streams."""

    text: str


@dataclass(frozen=True, slots=True)
class ToolStarted:
    """STRYX called a tool; surfaced so the UI can show what it is reading."""

    name: str
    title: str


@dataclass(frozen=True, slots=True)
class ToolFinished:
    name: str


@dataclass(frozen=True, slots=True)
class AgentDone:
    """The loop finished. ``text`` is the complete answer (the STRYX call)."""

    text: str


# What STRYX's ``run`` streams — a small tagged union the transport renders to SSE.
AgentEvent = StylesConsidered | TextDelta | ToolStarted | ToolFinished | AgentDone


@dataclass(frozen=True, slots=True)
class Session:
    """A conversation's short-lived memory."""

    id: str
    turns: tuple[Turn, ...] = field(default_factory=tuple)
