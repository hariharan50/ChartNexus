"""The dashboard's opening-gap reading.

The bug these pin: the gap card recomputed ``open - previous_close`` from every
fifteen-second spot poll, so a poll that degraded to the mock provider - which
has its own seeded open and its own previous close - swapped the whole reading.
On NIFTY that showed as +125 for a couple of minutes, then -120 for a couple of
minutes, tracking nothing but the broker's circuit breaker.

So the assertions below are mostly about what must *not* change.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from marketcompass.contexts.market_data.application.queries import GetSessionGap
from marketcompass.contexts.market_data.domain.gap import (
    GapSignal,
    SessionGap,
    classify,
    measure,
    supersedes,
)
from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.contexts.market_data.domain.market_data import (
    DataSource,
    Provenance,
    Quote,
)
from marketcompass.infrastructure.time.market_calendar import ExchangeCalendar
from marketcompass.shared_kernel.types.identifiers import TenantId

NIFTY = InstrumentSymbol.parse("NIFTY")
TENANT = TenantId(UUID("019fbe6d-18a2-72f8-b106-12d2c0bb4b3b"))

# A Monday. 04:00Z is 09:30 IST - the auction has settled.
MIDMORNING = datetime(2026, 9, 28, 4, 0, tzinfo=UTC)
# 03:30Z is 09:00 IST, before the bell.
PRE_OPEN = datetime(2026, 9, 28, 3, 30, tzinfo=UTC)
# The Saturday after.
WEEKEND = datetime(2026, 10, 3, 6, 0, tzinfo=UTC)


class _Clock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def set(self, now: datetime) -> None:
        self._now = now


class _Store:
    """An in-memory stand-in for the Redis latch."""

    def __init__(self) -> None:
        self.entries: dict[tuple[str, str], SessionGap] = {}
        self.writes = 0

    async def read(
        self, *, tenant_id: TenantId, instrument: InstrumentSymbol, session_date: date
    ) -> SessionGap | None:
        return self.entries.get((instrument.value, session_date.isoformat()))

    async def write(
        self,
        *,
        tenant_id: TenantId,
        instrument: InstrumentSymbol,
        session_date: date,
        gap: SessionGap,
    ) -> None:
        self.writes += 1
        self.entries[(instrument.value, session_date.isoformat())] = gap


class _BrokenStore:
    async def read(self, **_: object) -> SessionGap | None:
        raise RuntimeError("redis is down")

    async def write(self, **_: object) -> None:
        raise RuntimeError("redis is down")


def _quote(
    *,
    price: str = "23100.00",
    day_open: str | None = "23064.90",
    previous_close: str | None = "22780.20",
    source: DataSource = DataSource.LIVE,
    at: datetime = MIDMORNING,
) -> Quote:
    return Quote(
        instrument=NIFTY,
        price=Decimal(price),
        change=None,
        change_percent=None,
        day_open=Decimal(day_open) if day_open is not None else None,
        previous_close=Decimal(previous_close) if previous_close is not None else None,
        provenance=Provenance(source=source, fetched_at=at),
    )


def _use_case(store: object, clock: _Clock) -> GetSessionGap:
    return GetSessionGap(store=store, clock=clock, calendar=ExchangeCalendar())  # type: ignore[arg-type]


class TestMeasure:
    def test_it_reads_the_gap_off_the_pair(self) -> None:
        gap = measure(
            Decimal("23064.90"),
            Decimal("22780.20"),
            source=DataSource.LIVE,
            observed_at=MIDMORNING,
            settled=True,
        )

        assert gap is not None
        assert gap.points == Decimal("284.70")
        assert round(gap.percent, 2) == Decimal("1.25")
        assert gap.signal is GapSignal.UP

    @pytest.mark.parametrize(
        ("day_open", "previous_close"),
        [
            (None, "22780.20"),
            ("23064.90", None),
            ("0", "22780.20"),
            ("23064.90", "0"),
            ("-100", "22780.20"),
        ],
    )
    def test_an_unusable_pair_is_no_reading_rather_than_a_zero(
        self, day_open: str | None, previous_close: str | None
    ) -> None:
        # A zero gap renders as "opened flat", which is a claim. Absence is not.
        assert (
            measure(
                Decimal(day_open) if day_open else None,
                Decimal(previous_close) if previous_close else None,
                source=DataSource.LIVE,
                observed_at=MIDMORNING,
                settled=True,
            )
            is None
        )

    def test_it_rejects_a_gap_no_index_could_open_with(self) -> None:
        # Past the exchange's own 20% halt, so this is a bad field, not a gap.
        assert (
            measure(
                Decimal("30000"),
                Decimal("22780.20"),
                source=DataSource.LIVE,
                observed_at=MIDMORNING,
                settled=True,
            )
            is None
        )

    def test_it_rejects_an_open_that_cannot_belong_to_the_price_beside_it(self) -> None:
        # The pair is internally consistent - a 0.56% gap - and still refused,
        # because an index printing 23,100 right now did not open at 17,800.
        # This is the guard against a stale or foreign open reaching the card.
        assert (
            measure(
                Decimal("17800"),
                Decimal("17700"),
                source=DataSource.LIVE,
                observed_at=MIDMORNING,
                settled=True,
                reference_price=Decimal("23100"),
            )
            is None
        )

    def test_the_dead_zone_calls_overnight_noise_flat(self) -> None:
        assert classify(Decimal("0.14")) is GapSignal.FLAT
        assert classify(Decimal("-0.14")) is GapSignal.FLAT
        assert classify(Decimal("0.15")) is GapSignal.UP
        assert classify(Decimal("-0.15")) is GapSignal.DOWN


class TestSupersedes:
    def _gap(self, source: DataSource, *, settled: bool = True) -> SessionGap:
        gap = measure(
            Decimal("23064.90"),
            Decimal("22780.20"),
            source=source,
            observed_at=MIDMORNING,
            settled=settled,
        )
        assert gap is not None
        return gap

    def test_a_simulated_pair_never_displaces_a_live_one(self) -> None:
        assert not supersedes(self._gap(DataSource.MOCK), self._gap(DataSource.LIVE))

    def test_a_live_pair_displaces_the_mock_that_stood_in_for_it(self) -> None:
        assert supersedes(self._gap(DataSource.LIVE), self._gap(DataSource.MOCK))

    def test_the_same_source_observed_again_changes_nothing(self) -> None:
        assert not supersedes(self._gap(DataSource.LIVE), self._gap(DataSource.LIVE))

    def test_a_pre_open_placeholder_is_replaced_once_the_auction_has_run(self) -> None:
        provisional = self._gap(DataSource.LIVE, settled=False)
        assert supersedes(self._gap(DataSource.LIVE), provisional)


@pytest.mark.asyncio
class TestGetSessionGap:
    async def test_it_latches_the_first_believable_pair_of_the_session(self) -> None:
        store = _Store()
        gap = await _use_case(store, _Clock(MIDMORNING))(TENANT, _quote())

        assert gap is not None
        assert gap.points == Decimal("284.70")
        assert store.writes == 1

    async def test_a_mock_fallback_cannot_rewrite_a_live_opening_print(self) -> None:
        # The bug, exactly: the broker trips its circuit breaker, the next poll
        # comes back off the seeded walk, and the card used to flip sign.
        store = _Store()
        clock = _Clock(MIDMORNING)
        use_case = _use_case(store, clock)

        live = await use_case(TENANT, _quote())
        degraded = await use_case(
            TENANT,
            _quote(
                price="23976.50",
                day_open="23976.50",
                previous_close="24117.24",
                source=DataSource.MOCK,
            ),
        )

        assert degraded == live
        assert degraded is not None
        assert degraded.signal is GapSignal.UP
        assert store.writes == 1

    async def test_a_live_pair_replaces_the_mock_that_stood_in_before_it(self) -> None:
        store = _Store()
        use_case = _use_case(store, _Clock(MIDMORNING))

        await use_case(TENANT, _quote(source=DataSource.MOCK))
        gap = await use_case(TENANT, _quote(source=DataSource.LIVE))

        assert gap is not None
        assert gap.source is DataSource.LIVE
        assert store.writes == 2

    async def test_a_pre_open_reading_is_replaced_by_the_real_opening_print(self) -> None:
        # Brokers fill open_price with the previous session's figure until the
        # auction runs. Freezing that would be wrong all day.
        store = _Store()
        clock = _Clock(PRE_OPEN)
        use_case = _use_case(store, clock)

        stale = await use_case(TENANT, _quote(day_open="22800.00", at=PRE_OPEN))
        assert stale is not None
        assert not stale.settled

        clock.set(MIDMORNING)
        opened = await use_case(TENANT, _quote())

        assert opened is not None
        assert opened.opened_at == Decimal("23064.90")
        assert opened.settled

    async def test_it_keeps_the_latch_across_a_quote_that_lost_the_pair(self) -> None:
        store = _Store()
        use_case = _use_case(store, _Clock(MIDMORNING))

        latched = await use_case(TENANT, _quote())
        blank = await use_case(TENANT, _quote(day_open=None, previous_close=None))

        assert blank == latched

    async def test_no_pair_and_no_latch_is_no_reading(self) -> None:
        store = _Store()
        gap = await _use_case(store, _Clock(MIDMORNING))(
            TENANT, _quote(day_open=None, previous_close=None)
        )

        assert gap is None

    async def test_a_weekend_reads_the_session_that_actually_traded(self) -> None:
        store = _Store()
        clock = _Clock(WEEKEND)

        # Friday 2 October, not Saturday the 3rd.
        assert _use_case(store, clock)._anchor(WEEKEND) == (date(2026, 10, 2), True)

    async def test_a_store_outage_still_answers_from_the_poll_in_hand(self) -> None:
        # The latch buys steadiness, not correctness. Losing Redis must cost the
        # first and not the card.
        gap = await _use_case(_BrokenStore(), _Clock(MIDMORNING))(TENANT, _quote())

        assert gap is not None
        assert gap.points == Decimal("284.70")

    async def test_each_session_gets_its_own_latch(self) -> None:
        store = _Store()
        clock = _Clock(MIDMORNING)
        use_case = _use_case(store, clock)

        await use_case(TENANT, _quote())
        clock.set(MIDMORNING + timedelta(days=1))
        await use_case(TENANT, _quote(day_open="23200.00"))

        assert len(store.entries) == 2
