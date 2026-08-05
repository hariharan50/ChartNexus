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


@dataclass(frozen=True, slots=True)
class CaptureResult:
    """What one tick did, for the caller to log."""

    written: tuple[str, ...] = ()
    skipped_closed: bool = False
    skipped_mock: tuple[str, ...] = ()
    skipped_empty: tuple[str, ...] = ()
    failed: tuple[tuple[str, str], ...] = ()


@dataclass
class _Acc:
    written: list[str] = field(default_factory=list)
    skipped_mock: list[str] = field(default_factory=list)
    skipped_empty: list[str] = field(default_factory=list)
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
    ) -> None:
        self._source = source
        self._writer = writer
        self._calendar = calendar
        self._clock = clock
        self._symbols = symbols
        self._allow_mock = allow_mock

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
            failed=tuple(acc.failed),
        )

    async def _capture_one(self, symbol: str, acc: _Acc) -> None:
        try:
            observation = await self._source.fetch(symbol)
        except Exception as exc:
            acc.failed.append((symbol, repr(exc)))
            return

        if observation is None:
            return
        if observation.source == _MOCK and not self._allow_mock:
            # A mock-fallback day writes nothing: the honest gap in the archive
            # that later reads render as "no history for this session".
            acc.skipped_mock.append(symbol)
            return
        if not observation.rows:
            acc.skipped_empty.append(symbol)
            return

        try:
            await self._writer.save(self._to_snapshot(observation))
        except Exception as exc:
            acc.failed.append((symbol, repr(exc)))
            return
        acc.written.append(symbol)

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
