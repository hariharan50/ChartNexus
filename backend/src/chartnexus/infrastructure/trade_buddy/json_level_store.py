"""Marks and live states on disk, one JSON file per instrument.

The original single-operator store. Trade Buddy is now per-user and keeps its
state in Postgres (``PostgresLevelStore``); this one remains for two jobs:
reading the files a single-operator install left behind, for the one-off
``import-legacy`` command, and as the cheapest real store for unit tests of the
document logic both share (:mod:`.document_store`).

Writes go through a temporary file and an atomic replace. The engine saves after
every tick, so a crash mid-write is not a hypothetical, and a truncated JSON
file would lose the session's state entirely.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from chartnexus.contexts.trade_buddy.domain.level import LevelBands
from chartnexus.infrastructure.observability.structured_logging import get_logger
from chartnexus.infrastructure.trade_buddy.document_store import (
    VERSION,
    Document,
    DocumentLevelStore,
    Mutation,
    is_readable,
)

log = get_logger(__name__)


@dataclass(slots=True)
class JsonLevelStore(DocumentLevelStore):
    """Implements the ``LevelStore`` port against one JSON file per instrument."""

    directory: Path
    bands: LevelBands
    #: Guards the read-modify-write cycle within this process.
    _lock: asyncio.Lock = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def symbols(self) -> tuple[str, ...]:
        """Every instrument with a file here, for the legacy import."""
        return tuple(sorted(path.stem for path in self.directory.glob("*.json")))

    # -- paths --------------------------------------------------------------

    def _path(self, symbol: str) -> Path:
        # Symbols carry colons and hyphens ("NSE:NIFTY50-INDEX"), and a colon is
        # not a legal Windows filename character.
        safe = symbol.replace(":", "_").replace("/", "_")
        return self.directory / f"{safe}.json"

    # -- the primitives -----------------------------------------------------

    async def _load(self, symbol: str) -> Document:
        path = self._path(symbol)
        if not path.exists():
            return {}
        try:
            raw = await asyncio.to_thread(path.read_text, encoding="utf-8")
            parsed: Document = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("trade_buddy_state_unreadable", symbol=symbol, error=repr(exc))
            return {}
        if not is_readable(parsed):
            log.warning("trade_buddy_state_version_mismatch", symbol=symbol)
            return {}
        return parsed

    async def _update(self, symbol: str, mutate: Mutation) -> None:
        async with self._lock:
            data = await self._load(symbol)
            mutate(data)
            data["version"] = VERSION
            path = self._path(symbol)
            body = json.dumps(data, indent=2, sort_keys=True)

            def _atomic() -> None:
                temp = path.with_suffix(".json.tmp")
                temp.write_text(body, encoding="utf-8")
                temp.replace(path)

            await asyncio.to_thread(_atomic)

    async def _remove(self, symbol: str) -> None:
        async with self._lock:
            path = self._path(symbol)
            if path.exists():
                await asyncio.to_thread(path.unlink)
