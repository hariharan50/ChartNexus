"""Price history: the degrade ladder, the mock generator, and the FYERS mapper.

`GET /market/history` is the first read on this context that returns a series
rather than a single figure, so the things worth pinning are that a partial day
is not extended into a forecast, that a broker outage degrades to real cached
bars rather than silently to synthetic ones, and that an unrecognised payload
shape is an error instead of an empty chart.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from marketcompass.contexts.market_data.application.queries import GetHistory, HistoryQuery
from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.contexts.market_data.domain.market_data import (
    Candle,
    CandleInterval,
    CandleSeries,
    DataSource,
    Provenance,
)
from marketcompass.infrastructure.brokers.fyers.history_mapper import (
    to_candle_series,
    to_resolution,
)
from marketcompass.infrastructure.brokers.mock.history_factory import build_history
from marketcompass.shared_kernel.domain.errors import UpstreamError
from marketcompass.shared_kernel.types.identifiers import TenantId

pytestmark = pytest.mark.unit

TENANT = TenantId("00000000-0000-4000-8000-000000000001")
NIFTY = InstrumentSymbol.NIFTY

# A Wednesday, mid-session: 12:00 IST.
MIDDAY = datetime(2026, 8, 5, 6, 30, tzinfo=UTC)


# -- the mock generator -----------------------------------------------------


class TestMockHistory:
    def test_a_bar_summarises_the_walk_it_covers(self) -> None:
        series = build_history(NIFTY, CandleInterval.M5, days=1, now=MIDDAY)

        for candle in series.candles:
            assert candle.low <= candle.open <= candle.high
            assert candle.low <= candle.close <= candle.high

    def test_it_is_stamped_mock_and_never_anything_else(self) -> None:
        series = build_history(NIFTY, CandleInterval.M5, days=1, now=MIDDAY)
        assert series.provenance.source is DataSource.MOCK

    def test_the_same_request_always_returns_the_same_bars(self) -> None:
        first = build_history(NIFTY, CandleInterval.M15, days=3, now=MIDDAY)
        second = build_history(NIFTY, CandleInterval.M15, days=3, now=MIDDAY)
        assert first.candles == second.candles

    def test_a_longer_range_leaves_the_shared_bars_untouched(self) -> None:
        # Volume is seeded on a bar's own identity, so asking for more days must
        # not renumber or reprice the days already there.
        short = build_history(NIFTY, CandleInterval.H1, days=2, now=MIDDAY)
        long = build_history(NIFTY, CandleInterval.H1, days=5, now=MIDDAY)
        assert long.candles[-len(short.candles) :] == short.candles

    def test_today_stops_at_now_rather_than_running_to_the_close(self) -> None:
        series = build_history(NIFTY, CandleInterval.M5, days=1, now=MIDDAY)
        assert series.candles
        # Bars open on or before the moment asked for. Anything later would be a
        # forecast wearing a candle's clothes.
        assert all(candle.opened_at <= MIDDAY for candle in series.candles)

    def test_it_skips_the_weekend(self) -> None:
        # Monday 10 Aug 2026. Three sessions back is Thu/Fri/Mon, not Sat/Sun.
        monday = datetime(2026, 8, 10, 6, 30, tzinfo=UTC)
        series = build_history(NIFTY, CandleInterval.D1, days=3, now=monday)

        days = [candle.opened_at.date() for candle in series.candles]
        assert [day.weekday() for day in days] == [3, 4, 0]

    def test_daily_bars_are_one_per_session(self) -> None:
        series = build_history(NIFTY, CandleInterval.D1, days=4, now=MIDDAY)
        assert len(series.candles) == 4
        assert len({candle.opened_at.date() for candle in series.candles}) == 4

    def test_a_coarser_interval_yields_fewer_bars(self) -> None:
        fine = build_history(NIFTY, CandleInterval.M1, days=1, now=MIDDAY)
        coarse = build_history(NIFTY, CandleInterval.M15, days=1, now=MIDDAY)
        assert len(coarse.candles) < len(fine.candles)


# -- the FYERS mapper -------------------------------------------------------


class TestHistoryMapper:
    def test_it_reads_a_candle_row(self) -> None:
        payload = {"s": "ok", "candles": [[1_754_457_300, 24601.2, 24640.0, 24590.1, 24633.4, 0]]}

        series = to_candle_series(
            payload, instrument=NIFTY, interval=CandleInterval.M5, fetched_at=MIDDAY
        )

        assert len(series.candles) == 1
        candle = series.candles[0]
        assert candle.open == Decimal("24601.2")
        assert candle.high == Decimal("24640.0")
        assert candle.low == Decimal("24590.1")
        assert candle.close == Decimal("24633.4")
        assert candle.opened_at == datetime.fromtimestamp(1_754_457_300, tz=UTC)
        assert series.provenance.source is DataSource.LIVE

    def test_an_index_zero_volume_passes_through(self) -> None:
        # Indices have no turnover of their own. A synthesised figure beside live
        # prices would be a lie; an empty volume pane is merely quiet.
        payload = {"candles": [[1_754_457_300, 1.0, 2.0, 0.5, 1.5, 0]]}
        series = to_candle_series(
            payload, instrument=NIFTY, interval=CandleInterval.D1, fetched_at=MIDDAY
        )
        assert series.candles[0].volume == 0

    def test_an_empty_range_is_not_an_error(self) -> None:
        series = to_candle_series(
            {"candles": []}, instrument=NIFTY, interval=CandleInterval.D1, fetched_at=MIDDAY
        )
        assert series.candles == ()

    def test_a_missing_candles_key_raises(self) -> None:
        with pytest.raises(UpstreamError):
            to_candle_series(
                {"s": "error"}, instrument=NIFTY, interval=CandleInterval.D1, fetched_at=MIDDAY
            )

    def test_rows_that_all_fail_to_parse_raise_rather_than_read_as_quiet(self) -> None:
        # A shape change must not be indistinguishable from a market holiday.
        with pytest.raises(UpstreamError):
            to_candle_series(
                {"candles": [{"o": 1}, {"o": 2}]},
                instrument=NIFTY,
                interval=CandleInterval.M5,
                fetched_at=MIDDAY,
            )

    def test_resolutions_match_the_broker_vocabulary(self) -> None:
        assert to_resolution(CandleInterval.M1) == "1"
        assert to_resolution(CandleInterval.H1) == "60"
        assert to_resolution(CandleInterval.D1) == "D"


# -- the degrade ladder -----------------------------------------------------


def _series(fetched_at: datetime, source: DataSource, close: str) -> CandleSeries:
    return CandleSeries(
        instrument=NIFTY,
        interval=CandleInterval.M5,
        candles=(
            Candle(
                opened_at=fetched_at,
                open=Decimal(close),
                high=Decimal(close),
                low=Decimal(close),
                close=Decimal(close),
                volume=1,
            ),
        ),
        provenance=Provenance(source=source, fetched_at=fetched_at),
    )


class _Provider:
    def __init__(self, name: str, *, fails: bool = False, close: str = "100") -> None:
        self.name = name
        self._fails = fails
        self._close = close
        self.calls = 0

    async def get_history(
        self, instrument: InstrumentSymbol, interval: CandleInterval, days: int
    ) -> CandleSeries:
        self.calls += 1
        self.days = days
        if self._fails:
            raise UpstreamError("fyers", "down")
        source = DataSource.MOCK if self.name == "mock" else DataSource.LIVE
        return _series(MIDDAY, source, self._close)


class _Resolver:
    def __init__(self, provider: _Provider) -> None:
        self._provider = provider

    async def resolve(self, tenant_id: TenantId) -> _Provider:
        return self._provider

    async def is_live(self, tenant_id: TenantId) -> bool:
        return self._provider.name != "mock"


class _Clock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _query(interval: CandleInterval = CandleInterval.M5, days: int = 5) -> HistoryQuery:
    return HistoryQuery(tenant_id=TENANT, instrument=NIFTY, interval=interval, days=days)


class TestGetHistory:
    @pytest.mark.asyncio
    async def test_it_serves_the_broker_when_the_broker_answers(self) -> None:
        live = _Provider("fyers", close="24600")
        query = GetHistory(
            resolver=_Resolver(live), fallback=_Provider("mock"), clock=_Clock(MIDDAY)
        )

        series = await query(_query())

        assert series.provenance.source is DataSource.LIVE
        assert series.candles[0].close == Decimal("24600")

    @pytest.mark.asyncio
    async def test_an_outage_re_serves_the_last_real_bars_marked_cached(self) -> None:
        live = _Provider("fyers", close="24600")
        fallback = _Provider("mock")
        clock = _Clock(MIDDAY)
        get = GetHistory(resolver=_Resolver(live), fallback=fallback, clock=clock)

        await get(_query())

        # The broker goes down after one good answer.
        live._fails = True
        clock._now = MIDDAY + timedelta(seconds=90)
        series = await get(_query())

        assert series.provenance.source is DataSource.CACHED
        assert series.provenance.age_seconds == pytest.approx(90.0)
        # Real bars, re-labelled — not the mock's.
        assert series.candles[0].close == Decimal("24600")
        assert fallback.calls == 0

    @pytest.mark.asyncio
    async def test_it_falls_to_mock_only_when_nothing_real_was_ever_seen(self) -> None:
        fallback = _Provider("mock")
        get = GetHistory(
            resolver=_Resolver(_Provider("fyers", fails=True)),
            fallback=fallback,
            clock=_Clock(MIDDAY),
        )

        series = await get(_query())

        assert series.provenance.source is DataSource.MOCK
        assert fallback.calls == 1

    @pytest.mark.asyncio
    async def test_the_range_is_clamped_to_what_the_interval_supports(self) -> None:
        # A year of one-minute bars is not a slow request; it is one the broker
        # rejects. Clamping here keeps both providers behaving the same way.
        live = _Provider("fyers")
        get = GetHistory(resolver=_Resolver(live), fallback=_Provider("mock"), clock=_Clock(MIDDAY))

        await get(_query(CandleInterval.M1, days=365))

        assert live.days == CandleInterval.M1.max_days

    @pytest.mark.asyncio
    async def test_a_shorter_range_is_left_alone(self) -> None:
        live = _Provider("fyers")
        get = GetHistory(resolver=_Resolver(live), fallback=_Provider("mock"), clock=_Clock(MIDDAY))

        await get(_query(CandleInterval.D1, days=30))

        assert live.days == 30

    @pytest.mark.asyncio
    async def test_intervals_cache_separately(self) -> None:
        # Two intervals share an instrument but not a series. A single cache key
        # would serve 5-minute bars to a request for daily ones.
        live = _Provider("fyers")
        get = GetHistory(resolver=_Resolver(live), fallback=_Provider("mock"), clock=_Clock(MIDDAY))

        await get(_query(CandleInterval.M5))
        await get(_query(CandleInterval.D1))

        assert live.calls == 2
