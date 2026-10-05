"""The Observation aggregate — one hourly read, later graded.

An ``Observation`` is what HUGIN records at a tick: the raw market ``readings``,
its directional ``bias``, an explicit *falsifiable* next-hour ``expectation``, and
the structural levels it hangs that read on (call wall / put wall / key level).

The grade fields (``grade``, ``score``, ``grade_evidence``) start empty. The
*next* tick loads this row, judges the expectation against what the market
actually did, and fills them in — so a graded observation carries both what HUGIN
predicted and how that prediction turned out, with the cited numbers behind the
verdict kept for audit.

Frozen dataclasses, no shared aggregate base: the repo's ``shared_kernel`` bases
are empty stubs, so — like STRYX — this context defines its own vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from chartnexus.shared_kernel.types.identifiers import TenantId


class Bias(StrEnum):
    """The read's directional lean. Values mirror the DB check constraint."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class Grade(StrEnum):
    """How last hour's expectation held up. Values mirror the DB check constraint."""

    HIT = "HIT"
    PARTIAL = "PARTIAL"
    MISS = "MISS"


@dataclass(frozen=True, slots=True)
class Observation:
    """One tenant x instrument x tick read, optionally graded by the next tick."""

    tenant_id: TenantId
    instrument: str
    tick_at: datetime
    trading_day: date
    readings: dict[str, Any]
    bias: Bias
    expectation: str
    call_wall: Decimal | None = None
    put_wall: Decimal | None = None
    key_level: Decimal | None = None
    # Filled by the following tick when it grades this observation.
    grade: Grade | None = None
    score: Decimal | None = None
    grade_evidence: dict[str, Any] | None = None
    # Present once persisted/read back; absent on a freshly reflected observation.
    id: Any | None = None
    created_at: datetime | None = None

    @property
    def graded(self) -> bool:
        return self.grade is not None
