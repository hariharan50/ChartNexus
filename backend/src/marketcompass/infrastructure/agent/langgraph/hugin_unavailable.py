"""HUGIN's reflector when no model is configured — import-safe without the extra.

``HuginReflector`` imports the LangChain/pydantic structured-output stack, so when
the optional ``agent`` extra isn't installed importing it raises ``ImportError``.
The reflector builder returns *this* instead when the tenant owner has no usable
key, so the worker (and the availability check) answer without pulling in that
stack. The cycle gates on ``available`` and skips before ``reflect`` is ever
called; the method raises only as a defensive guard.
"""

from __future__ import annotations

from marketcompass.contexts.hugin.domain.cycle import ReflectInput, ReflectOutput


class UnavailableReflector:
    """A ``ReflectorPort`` that is never available; HUGIN accrues no memory."""

    available = False

    async def reflect(self, request: ReflectInput) -> ReflectOutput:
        _ = request
        raise RuntimeError("HUGIN reflector is unavailable — no language model is configured.")
