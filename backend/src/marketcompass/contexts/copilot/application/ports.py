"""What the copilot context needs from the outside world.

* ``GuidancePort`` — the current AI-guider call for an instrument, as a
  copilot-owned :class:`GuidanceSnapshot` (so copilot never imports ``signals``).
  Satisfied by an infrastructure bridge over the signals use case.
* ``LLMPort`` — a text-completion provider. ``is_generative`` is the switch the
  conversation layer reads: the rule-based provider is *not* generative, so
  copilot answers deterministically from the structured snapshot and never calls
  ``complete``; the Anthropic/OpenAI providers are, and get the grounded facts as
  a guardrail.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from marketcompass.contexts.copilot.domain.models import GuidanceSnapshot
from marketcompass.shared_kernel.types.identifiers import TenantId


class GuidancePort(Protocol):
    async def current(self, tenant_id: TenantId, symbol: str) -> GuidanceSnapshot: ...


@dataclass(frozen=True, slots=True)
class LLMMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    provider: str
    model: str | None = None


class LLMPort(Protocol):
    #: The provider's name, e.g. "anthropic" / "openai" / "rule_based".
    name: str
    #: True when ``complete`` calls a real language model. False for the
    #: rule-based provider, whose answers are produced deterministically instead.
    is_generative: bool

    async def complete(self, *, system: str, messages: list[LLMMessage]) -> LLMResponse: ...
