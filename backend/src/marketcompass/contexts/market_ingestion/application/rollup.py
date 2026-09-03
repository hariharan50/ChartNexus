"""Rolls the intraday archive up into one implied-volatility reading per session.

Implied volatility is only ever quoted *now*. The intraday archive that holds it
is pruned after 30 days, and the broker will not sell the missing history back —
FYERS never quoted IV in the first place, so it exists only because this system
back-solved it at capture time. Once a session falls out of the retention window
its volatility is gone permanently.

So IV Rank and IV Percentile over any real lookback are impossible unless
something writes a durable row per session as the sessions happen. That is this
use case. It walks every session still in the archive, takes the last capture's
at-the-money IV, and upserts it — which means it both **backfills** whatever the
window currently holds and **keeps today current** as the session fills out.

Ordering matters: run it before :class:`PruneSnapshots`. The prune is what
deletes the oldest day, and the rollup has to see that day first or the reading
is lost for good.

Deliberately separate from :class:`CaptureChainSnapshots`, which returns early
when the market is closed — the same reasoning that put pruning in its own use
case.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta, timezone
from decimal import Decimal
from typing import Protocol, runtime_checkable

from marketcompass.contexts.market_ingestion.application.ports import Clock

_IST = timezone(timedelta(hours=5, minutes=30))


@dataclass(frozen=True, slots=True)
class SessionIv:
    """One session's closing volatility, ready to store."""

    symbol: str
    session_date: date
    atm_iv: Decimal
    future_close: Decimal | None
    captures: int
    source: str


@dataclass(frozen=True, slots=True)
class RollupResult:
    """What one rollup pass did."""

    written: int
    skipped: int


@runtime_checkable
class SessionIvSource(Protocol):
    """Reads closing IV per session out of the intraday archive."""

    async def session_ivs(self, symbol: str, *, since: date) -> list[SessionIv]:
        """One entry per session on or after ``since`` that has a usable ATM IV.

        Sessions whose last capture quoted no volatility at the money are simply
        absent — a day with no reading must not become a row claiming one.
        """
        ...


@runtime_checkable
class DailyIvWriter(Protocol):
    async def upsert_daily_iv(self, rows: list[SessionIv]) -> int: ...


class RollupDailyIv:
    """Persists one IV reading per session, for every session still archived."""

    def __init__(self, *, source: SessionIvSource, writer: DailyIvWriter, clock: Clock) -> None:
        self._source = source
        self._writer = writer
        self._clock = clock

    async def __call__(self, symbols: list[str], *, lookback_days: int) -> RollupResult:
        since = self._since(lookback_days)
        written = 0
        skipped = 0
        for symbol in symbols:
            rows = await self._source.session_ivs(symbol, since=since)
            if not rows:
                skipped += 1
                continue
            written += await self._writer.upsert_daily_iv(rows)
        return RollupResult(written=written, skipped=skipped)

    def _since(self, lookback_days: int) -> date:
        """The oldest session worth asking for.

        The IST trading date, not the UTC one: ``session_date`` is an IST date,
        and deriving the bound from UTC would shift it by a day for five and a
        half hours of every evening.
        """
        today = self._clock.now().astimezone(_IST).date()
        return today - timedelta(days=max(1, lookback_days))
