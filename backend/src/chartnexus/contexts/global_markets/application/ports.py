"""Ports the global-markets use cases depend on."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable

from chartnexus.contexts.global_markets.domain.handoff import GapPrediction
from chartnexus.contexts.global_markets.domain.quotes import GlobalQuote, QuoteSet


@runtime_checkable
class GlobalQuoteSource(Protocol):
    """A source of world index and macro quotes.

    Implementations raise nothing on a partial answer: a provider that could
    not price three of fourteen symbols returns the eleven it has, and the
    caller renders dashes for the rest. A page showing eleven real rows is
    useful; one that 500s because Shanghai was unreachable is not.
    """

    @property
    def name(self) -> str: ...

    async def get_quotes(self, symbols: Sequence[str]) -> QuoteSet: ...


@runtime_checkable
class GiftNiftySource(Protocol):
    """GIFT NIFTY, which no general quote provider carries.

    Its own port precisely because it is the odd one out: NSE IX publishes no
    documented API, so this ships simulated and badged. Keeping it behind a
    separate seam means a live adapter lands here and nowhere else.
    """

    @property
    def name(self) -> str: ...

    async def get_quote(self, nifty_spot: GlobalQuote | None) -> GlobalQuote | None: ...


@runtime_checkable
class GapJournal(Protocol):
    """Where each session's prediction is recorded before the open settles it.

    Nothing reads this yet. It is written from the first day anyway because a
    prediction is only cheap to record *before* the outcome is known - after
    the fact it cannot be reconstructed at all, and a scorecard added later
    would have no history to grade.

    **``record`` must not raise.** Nothing on the page depends on the write
    landing, so an implementation swallows and logs its own failures rather
    than letting a journal hiccup take down a read the user is waiting on.
    """

    async def record(self, prediction: GapPrediction) -> None: ...

    async def history(self, sessions: int) -> Sequence[GapPrediction]: ...


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...
