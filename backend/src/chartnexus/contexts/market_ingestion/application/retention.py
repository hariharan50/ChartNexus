"""Retention policy for the option-chain archive.

Ingest writes ~126 snapshots per symbol per trading day, each with ~90 legs.
Left alone that is roughly 8 million rows a year for three instruments, for data
whose only consumer — the Open Interest tool — never looks past *today*. This
use case decides what may be deleted; the adapter decides how.

Deliberately separate from :class:`CaptureChainSnapshots`, which returns early
when the market is closed. That is exactly when pruning should happen.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta, timezone

from chartnexus.contexts.market_ingestion.application.ports import Clock, SnapshotPruner

_IST = timezone(timedelta(hours=5, minutes=30))


@dataclass(frozen=True, slots=True)
class PruneResult:
    """What one prune pass did."""

    cutoff: date
    deleted: int


class RetentionError(RuntimeError):
    """Raised when the computed cutoff is not safe to act on."""


class PruneSnapshots:
    """Deletes archived snapshots older than the retention window."""

    def __init__(self, *, pruner: SnapshotPruner, clock: Clock, retention_days: int) -> None:
        if retention_days < 1:
            raise RetentionError("retention_days must be at least 1")
        self._pruner = pruner
        self._clock = clock
        self._retention_days = retention_days

    async def __call__(self) -> PruneResult:
        cutoff = self.cutoff()
        deleted = await self._pruner.delete_sessions_before(cutoff)
        return PruneResult(cutoff=cutoff, deleted=deleted)

    def cutoff(self) -> date:
        """The first session date that is kept; everything before it goes.

        Computed on the IST trading date, because ``session_date`` is an IST
        date — deriving it from a UTC date would move the boundary by a day for
        five and a half hours of every evening.
        """
        today = self._clock.now().astimezone(_IST).date()
        cutoff = today - timedelta(days=self._retention_days)
        if cutoff >= today:
            # Unreachable with a validated window, and catastrophic if it ever
            # were reached: a cutoff of today or later erases the whole archive,
            # including the session currently being captured.
            raise RetentionError(f"refusing a cutoff that is not in the past: {cutoff}")
        return cutoff
