"""HUGIN's chat vocabulary — its own, so the context imports no other agent.

A minimal conversation model: a ``Session`` of ``Turn``s, and the two streamed
events the transport speaks (``TextDelta`` while answering, ``ChatDone`` at the
end). HUGIN's chat has no tools and no playbook — it reasons purely over the memory
digest it is handed — so the event set is smaller than STRYX's.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Turn:
    role: str  # "user" | "assistant"
    text: str


@dataclass(frozen=True, slots=True)
class Session:
    id: str
    turns: tuple[Turn, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class TextDelta:
    text: str


@dataclass(frozen=True, slots=True)
class ChatDone:
    text: str


ChatEvent = TextDelta | ChatDone
