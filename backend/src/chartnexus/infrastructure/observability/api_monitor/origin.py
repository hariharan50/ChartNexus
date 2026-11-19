"""Who asked for an outbound call.

The transport cannot see its caller, so the caller's label rides along in a
``ContextVar``. Tasks copy the context they were created in, which means a
label set where a background loop is started covers every call that loop and
its children make.

Fallback order: an explicit label, else the process name (``chartnexus-ingest``
becomes ``ingest``), else ``other``.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from pathlib import Path

_MAX_ORIGIN_LENGTH = 80

_origin: ContextVar[str | None] = ContextVar("cn_api_call_origin", default=None)


def _process_origin() -> str:
    name = Path(sys.argv[0]).name if sys.argv and sys.argv[0] else ""
    name = name.removesuffix(".exe").removesuffix("-script.py").removesuffix(".py")
    if name.startswith("chartnexus-"):
        return clean_origin(name.removeprefix("chartnexus-"))
    return "other"


def clean_origin(label: str) -> str:
    """A label safe to store: no field separator, bounded length."""
    cleaned = label.strip().replace("|", "/").removesuffix("-loop") or "other"
    return cleaned[:_MAX_ORIGIN_LENGTH]


_PROCESS_ORIGIN = _process_origin()


def current_origin() -> str:
    return _origin.get() or _PROCESS_ORIGIN


def set_origin(label: str) -> Token[str | None]:
    return _origin.set(clean_origin(label))


def reset_origin(token: Token[str | None]) -> None:
    _origin.reset(token)


@contextmanager
def api_call_origin(label: str) -> Iterator[None]:
    """Label every outbound call made inside the block (and tasks it starts)."""
    token = set_origin(label)
    try:
        yield
    finally:
        _origin.reset(token)
