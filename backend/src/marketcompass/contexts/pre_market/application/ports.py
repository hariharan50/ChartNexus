"""What this context needs from the outside, stated as protocols.

Every one of these is implemented in ``infrastructure/pre_market/`` against a
*different* bounded context's application services. That indirection is not
ceremony: ``tests/architecture/test_context_boundaries.py`` walks every file
under ``contexts/`` and fails on any import of another context, with no
exemption list. So these protocols are the only vocabulary PMS has for the rest
of the system, and they deliberately speak in this context's own DTOs.

**Every method returns ``None`` rather than raising for a missing reading.**
Raising is reserved for a genuine fault, which the query layer catches and
turns into a named ``SectionStatus``. The distinction matters: "the broker has
no SENSEX chain" is a fact the page should state, while "Redis refused the
connection" is a fault the page should survive.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable

from marketcompass.contexts.pre_market.domain.readings import (
    BreadthReading,
    CandleSeries,
    FlowReading,
    GlobalReading,
    MarketPhase,
    NarrativeReading,
    OptionsReading,
    SpotReading,
)


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...


class SpotSource(Protocol):
    """Live quotes for the headline indices."""

    async def get_spots(self, symbols: Sequence[str]) -> dict[str, SpotReading]:
        """Whatever answered, keyed by symbol. A partial result is a good one."""
        ...


class DailyCandleSource(Protocol):
    """Daily bars, for levels and indicators."""

    async def get_daily(self, symbol: str, *, days: int) -> CandleSeries | None: ...


class OptionSnapshotSource(Protocol):
    """The option book, reduced to a pre-market read."""

    async def get_options(self, symbol: str) -> OptionsReading | None: ...


class GlobalCueSource(Protocol):
    """The overnight handoff — world indices, macro, GIFT NIFTY."""

    async def get_global(self) -> GlobalReading | None: ...


class BreadthSource(Protocol):
    """Participation across an index's members."""

    async def get_breadth(self, index: str) -> BreadthReading | None: ...


class FlowSource(Protocol):
    """Yesterday's institutional net."""

    async def get_flows(self) -> FlowReading | None: ...


class VixHistorySource(Protocol):
    """Past India VIX closes, for the percentile.

    Returns an empty tuple rather than ``None`` when no history has accrued:
    the count is itself the answer the page prints beside an empty rank.
    """

    async def get_vix_history(self, *, days: int) -> tuple[float, ...]: ...


class MarketPhasePort(Protocol):
    """Where the clock is, relative to the Indian session."""

    async def get_phase(self) -> MarketPhase | None: ...


class NarrativeSource(Protocol):
    """Today's stored morning prose, if one has been written."""

    async def get_narrative(self) -> NarrativeReading | None: ...


class ViewCache(Protocol):
    """Whole-view caching, so one fan-out serves many simultaneous loads."""

    async def get(self, key: str) -> bytes | None: ...

    async def set(self, key: str, payload: bytes, *, ttl_seconds: int) -> None: ...
