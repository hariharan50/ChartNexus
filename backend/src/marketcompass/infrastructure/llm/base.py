"""Shared LLM-adapter helpers.

The port these providers implement (``LLMPort``, ``LLMMessage``, ``LLMResponse``)
is declared by the ``copilot`` context; infrastructure only supplies concrete
providers and the factory that picks one from settings.
"""

from __future__ import annotations


class LLMError(RuntimeError):
    """A provider could not produce a completion (network, auth, quota)."""
