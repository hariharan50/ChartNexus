"""Capture option-chain snapshots for a set of instruments.

Runs on a schedule from the ingest process. One tick:

* does nothing outside market hours (no point archiving a frozen tape);
* for each symbol, fetches the live chain and — unless it is mock data the
  operator has not opted into — derives the header metrics and writes one
  snapshot.

It never raises for a single symbol's failure: a broker hiccup on BANKNIFTY must
not cost the NIFTY snapshot. Outcomes are returned as a :class:`CaptureResult`
for the caller to log; the use case itself stays free of I/O and framework.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta, timezone

from marketcompass.contexts.market_ingestion.application.ports import (
    ChainObservation,
    ChainSource,
    Clock,
    MarketCalendar,
    SnapshotToWrite,
    SnapshotWriter,
)
from marketcompass.contexts.market_ingestion.domain.chain_metrics import (
    MetricRow,
    atm_strike,
    max_pain_strike,
    pcr_oi,
    total_call_oi,
    total_put_oi,
)

# India observes no DST, so a fixed +05:30 offset is correct and avoids a tzdata
# dependency (matching how options_analytics reasons about the session).
_IST = timezone(timedelta(hours=5, minutes=30))
_MOCK = "mock"
_LIVE = "live"


@dataclass(frozen=True, slots=True)
class CaptureResult:
    """What one tick did, for the caller to log."""

    written: tuple[str, ...] = ()
    skipped_closed: bool = False
    skipped_mock: tuple[str, ...] = ()
    skipped_empty: tuple[str, ...] = ()
    skipped_unchanged: tuple[str, ...] = ()
    failed: tuple[tuple[str, str], ...] = ()


@dataclass
class _Acc:
    written: list[str] = field(default_factory=list)
    skipped_mock: list[str] = field(default_factory=list)
    skipped_empty: list[str] = field(default_factory=list)
    skipped_unchanged: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


class CaptureChainSnapshots:
    """Captures one snapshot per configured symbol when the market is open."""

    def __init__(
        self,
        *,
        source: ChainSource,
        writer: SnapshotWriter,
        calendar: MarketCalendar,
        clock: Clock,
        symbols: tuple[str, ...],
        allow_mock: bool = False,
        expiries: int = 1,
    ) -> None:
        self._source = source
        self._writer = writer
        self._calendar = calendar
        self._clock = clock
        self._symbols = symbols
        self._allow_mock = allow_mock
        self._expiries = max(1, expiries)

    async def __call__(self) -> CaptureResult:
        now = self._clock.now()
        if not self._calendar.is_open(now):
            return CaptureResult(skipped_closed=True)

        acc = _Acc()
        for symbol in self._symbols:
            await self._capture_one(symbol, acc)

        return CaptureResult(
            written=tuple(acc.written),
            skipped_mock=tuple(acc.skipped_mock),
            skipped_empty=tuple(acc.skipped_empty),
            skipped_unchanged=tuple(acc.skipped_unchanged),
            failed=tuple(acc.failed),
        )

    async def _capture_one(self, symbol: str, acc: _Acc) -> None:
        """Archive this symbol's configured expiries.

        Each expiry is captured independently: one contract's broker hiccup must
        not cost the others, exactly as one symbol's failure must not cost the
        rest of the universe.
        """
        for expiry in await self._expiries_for(symbol):
            await self._capture_expiry(symbol, expiry, acc)

    async def _expiries_for(self, symbol: str) -> tuple[str | None, ...]:
        """The expiries to capture, or ``(None,)`` to take whatever resolves.

        ``None`` is not the same as "the nearest": it lets the provider pick,
        which is the behaviour this loop had before it could archive more than
        one contract, and the one it keeps when configured for a single expiry.
        """
        if self._expiries <= 1:
            return (None,)
        try:
            listed = await self._source.expiries(symbol)
        except Exception:
            # A source that cannot list them still has a default chain to give.
            return (None,)
        if not listed:
            return (None,)
        return tuple(listed[: self._expiries])

    async def _capture_expiry(self, symbol: str, expiry: str | None, acc: _Acc) -> None:
        # Failures are labelled with the contract, not just the symbol: "NIFTY
        # failed" is useless when five of its six expiries wrote fine.
        label = symbol if expiry is None else f"{symbol}@{expiry}"
        try:
            observation = await self._source.fetch(symbol, expiry=expiry)
        except Exception as exc:
            acc.failed.append((label, repr(exc)))
            return
        if observation is None:
            return

        try:
            stored = await self._store(label, observation, acc)
        except Exception as exc:
            acc.failed.append((label, repr(exc)))
            return
        if stored:
            acc.written.append(label)

    async def _store(self, symbol: str, observation: ChainObservation, acc: _Acc) -> bool:
        """Decide whether this observation belongs in the archive, and write it.

        Every ``False`` here records *why* on ``acc``, because "the timeline has
        a gap" and "the timeline is wrong" look identical on the chart and only
        the log can tell them apart.
        """
        if observation.source == _MOCK and not self._allow_mock:
            # A mock-fallback day writes nothing: the honest gap in the archive
            # that later reads render as "no history for this session".
            acc.skipped_mock.append(symbol)
            return False
        if not observation.rows:
            acc.skipped_empty.append(symbol)
            return False

        snapshot = self._to_snapshot(observation)

        if observation.source == _MOCK and await self._writer.has_source(
            snapshot.symbol, snapshot.session_date, _LIVE
        ):
            # The broker answered earlier today and has since dropped out.
            # Filling the gap with simulated interest would splice a fabricated
            # afternoon onto a real morning — the chart draws one continuous
            # line, so nothing on screen says where the real data stopped. An
            # honest gap is recoverable; a seam is not.
            acc.skipped_mock.append(symbol)
            return False

        if await self._is_unchanged(snapshot):
            # The tape is frozen — a holiday the calendar does not know about,
            # or a provider repeating its last answer. Storing it would fill the
            # archive with identical frames, leaving the OI tool's timeline
            # fully populated and completely inert, which is a far more
            # confusing failure than an honest gap.
            acc.skipped_unchanged.append(symbol)
            return False

        await self._writer.save(snapshot)
        return True

    async def _is_unchanged(self, snapshot: SnapshotToWrite) -> bool:
        # Scoped to this contract. Compared across expiries the check is
        # meaningless: two different contracts never have identical books, so
        # it would pass every time and the frozen-tape guard would be dead code.
        previous = await self._writer.latest_rows(
            snapshot.symbol, snapshot.session_date, snapshot.expiry
        )
        return previous is not None and previous == snapshot.rows

    def _to_snapshot(self, observation: ChainObservation) -> SnapshotToWrite:
        metric_rows = [
            MetricRow(strike=row.strike, option_type=row.option_type, oi=row.oi)
            for row in observation.rows
        ]
        strikes = sorted({row.strike for row in metric_rows})
        session_date = observation.captured_at.astimezone(_IST).date()

        return SnapshotToWrite(
            symbol=observation.symbol,
            session_date=session_date,
            captured_at=observation.captured_at,
            spot=observation.spot,
            source=observation.source,
            rows=observation.rows,
            expiry=observation.expiry,
            future_price=observation.future_price,
            lot_size=observation.lot_size,
            atm_strike=atm_strike(observation.spot, strikes),
            total_call_oi=total_call_oi(metric_rows),
            total_put_oi=total_put_oi(metric_rows),
            pcr_oi=pcr_oi(metric_rows),
            max_pain_strike=max_pain_strike(metric_rows, strikes),
        )
