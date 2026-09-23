"""Ports the market-breadth use cases depend on.

Two sources, because the pages draw on two genuinely different kinds of data:
a priced index, which the broker can answer, and the exchange's daily
participant file, which it cannot.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from marketcompass.contexts.market_breadth.domain.constituents import IndexSnapshot
from marketcompass.contexts.market_breadth.domain.flows import FlowDay
from marketcompass.contexts.market_breadth.domain.open_interest import OiRow
from marketcompass.shared_kernel.types.identifiers import TenantId


@runtime_checkable
class IndexConstituentSource(Protocol):
    async def read(self, tenant_id: TenantId, index: str) -> IndexSnapshot:
        """Every member of ``index``, priced against its previous close.

        One call for the whole index, not one per member: a fifty-name index
        refreshed on a fifteen-second poll would exhaust the shared daily
        broker quota before lunch.

        Members the source could not price are returned with a ``None``
        previous close rather than omitted, so the page can show the index's
        real membership and say which rows are missing prints.
        """
        ...

    def universe(self) -> tuple[str, ...]:
        """Which indices this source can answer for, in display order.

        Synchronous because it reads a static membership table, not the
        market. The API layer uses it to validate the ``index`` query
        parameter instead of hardcoding a list of its own.
        """
        ...


@runtime_checkable
class InstitutionalFlowSource(Protocol):
    async def read(
        self, tenant_id: TenantId, *, sessions: int, until: date | None = None
    ) -> list[FlowDay]:
        """The last ``sessions`` published participant days, oldest first.

        ``until`` caps the window at an archived session for replay; ``None``
        means up to the most recent published day. Trading holidays simply do
        not appear — the list is sessions, not calendar days, and a consumer
        that assumes otherwise will mis-date its own axis.
        """
        ...

    async def read_open_interest(self, tenant_id: TenantId, session: date) -> list[OiRow]:
        """Participant-wise open interest for one session.

        A separate call from ``read`` because these are separate publications:
        the value tables and the participant-wise OI file are two documents,
        and a source may well have one and not the other. An empty list means
        "nothing published for that session", which the page renders as an
        empty board rather than as zeros.
        """
        ...

    async def neighbours(
        self, tenant_id: TenantId, session: date
    ) -> tuple[date | None, date | None]:
        """The published sessions immediately before and after ``session``.

        ``(None, None)`` at the two ends of the archive. The date stepper on
        the page is built from this rather than from calendar arithmetic of
        its own: only the source knows which days the exchange published, and
        a client guessing "yesterday" walks into every holiday.
        """
        ...

    async def read_index(
        self, tenant_id: TenantId, session: date, index: str
    ) -> IndexSnapshot | None:
        """Where ``index`` closed on ``session``, if this source can say.

        Separate from ``IndexConstituentSource.read`` because it answers a
        different question. The broker answers "where is the index *now*";
        this answers "where did it finish on that day". For the latest
        session the two agree, and for every archived one only this can be
        right — a broker asked about a session three weeks back returns
        today's level, and printing that under that day's date is a lie the
        reader has no way to catch.

        ``None`` when the source has no archived close, which is the ordinary
        answer for a source that only generates figures.
        """
        ...

    @property
    def source(self) -> str:
        """``"live"`` or ``"mock"``.

        Declared on the port rather than inferred by the caller. The daily
        participant file has no real adapter yet, and a generated flow board
        is indistinguishable from a true one by inspection — this property is
        the only thing that separates them.
        """
        ...
