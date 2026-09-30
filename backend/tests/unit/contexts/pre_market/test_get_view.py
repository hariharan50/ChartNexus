"""The aggregate read, and what it does when upstreams misbehave.

These are the cases the page's reliability actually rests on. A screener that
blanks because one of four upstream contexts is down is worse than useless at
09:10, so "one leg fails" is tested as a first-class behaviour rather than
left to an exception handler nobody exercises.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from marketcompass.contexts.pre_market.application.get_pre_market_view import (
    GetPreMarketView,
    PreMarketQuery,
)
from marketcompass.contexts.pre_market.domain.readings import (
    BreadthReading,
    CandleSeries,
    FlowReading,
    GiftReading,
    GlobalReading,
    MarketPhase,
    NarrativeReading,
    OptionsReading,
    SpotReading,
)
from marketcompass.contexts.pre_market.domain.view import Availability
from marketcompass.shared_kernel.domain.levels import Bar

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 28, 8, 45, tzinfo=UTC)


class UpstreamError(Exception):
    """A stand-in for any upstream fault."""


def bars(count: int = 260) -> tuple[Bar, ...]:
    return tuple(
        Bar(open=25_000 + n * 10 - 5, high=25_000 + n * 10 + 40,
            low=25_000 + n * 10 - 40, close=25_000 + n * 10)
        for n in range(count)
    )


def spot(symbol: str, price: str, previous: str, open_: str | None = None) -> SpotReading:
    return SpotReading(
        symbol=symbol,
        label=symbol,
        price=Decimal(price),
        previous_close=Decimal(previous),
        day_open=Decimal(open_) if open_ else None,
        change=None,
        change_percent=None,
        source="live",
    )


class StubSpots:
    def __init__(self, readings: dict[str, SpotReading] | None = None, fail: bool = False):
        self._readings = readings or {
            "NIFTY": spot("NIFTY", "25482", "25386", "25420"),
            "BANKNIFTY": spot("BANKNIFTY", "57000", "56900", "56950"),
            "SENSEX": spot("SENSEX", "82000", "81900", "81950"),
        }
        self._fail = fail

    async def get_spots(self, symbols: Sequence[str]) -> dict[str, SpotReading]:
        if self._fail:
            raise UpstreamError
        return {k: v for k, v in self._readings.items() if k in symbols}


class StubCandles:
    def __init__(self, fail: bool = False, series: CandleSeries | None = None):
        self._fail = fail
        self._series = series

    async def get_daily(self, symbol: str, *, days: int) -> CandleSeries | None:
        if self._fail:
            raise UpstreamError
        return self._series or CandleSeries(symbol=symbol, bars=bars())


class StubOptions:
    def __init__(self, fail: bool = False, reading: OptionsReading | None = None):
        self._fail = fail
        self._reading = reading

    async def get_options(self, symbol: str) -> OptionsReading | None:
        if self._fail:
            raise UpstreamError
        return self._reading or OptionsReading(
            expiry=None, days_to_expiry=3, spot=Decimal("25482"),
            atm_strike=Decimal("25500"), pcr_oi=Decimal("1.18"), pcr_change=None,
            total_call_oi=1, total_put_oi=2, max_pain=Decimal("25500"),
            call_wall=Decimal("25700"), put_wall=Decimal("25300"),
            gamma_flip=None, atm_iv=Decimal("13.8"), iv_percentile=Decimal("38"),
            atm_straddle=Decimal("185"), india_vix=Decimal("13.82"),
            india_vix_change_percent=Decimal("-4.21"),
        )


class StubGlobal:
    def __init__(self, fail: bool = False):
        self._fail = fail

    async def get_global(self) -> GlobalReading | None:
        if self._fail:
            raise UpstreamError
        return GlobalReading(
            pressure_score=Decimal("32.5"),
            pressure_band="up",
            gift=GiftReading(
                level=Decimal("25575"), change=Decimal("-85"),
                change_percent=Decimal("-0.37"), overnight_high=Decimal("25640"),
                overnight_low=Decimal("25420"), gap_points=Decimal("189"),
                gap_percent=Decimal("0.74"), signal="gap_up",
            ),
        )


class StubBreadth:
    def __init__(self, fail: bool = False):
        self._fail = fail
        self.calls: list[str] = []

    async def get_breadth(self, index: str) -> BreadthReading | None:
        self.calls.append(index)
        if self._fail:
            raise UpstreamError
        return BreadthReading(advances=1420, declines=812, unchanged=105, priced=50, universe=50)


class StubFlows:
    async def get_flows(self) -> FlowReading | None:
        return FlowReading(session_date=None, fii_net=Decimal("-710"), dii_net=Decimal("1280"))


class StubVix:
    def __init__(self, history: tuple[float, ...] = ()):
        self._history = history

    async def get_vix_history(self, *, days: int) -> tuple[float, ...]:
        return self._history


class StubPhase:
    async def get_phase(self) -> MarketPhase | None:
        return MarketPhase(
            is_open=False, session_date="2026-09-28", time_ist="08:45",
            opens_ist="09:15", closes_ist="15:30",
        )


class StubNarrative:
    def __init__(self, reading: NarrativeReading | None = None):
        self._reading = reading

    async def get_narrative(self) -> NarrativeReading | None:
        return self._reading


class StubClock:
    def now(self) -> datetime:
        return NOW


def build(**overrides: object) -> GetPreMarketView:
    parts: dict[str, object] = {
        "spots": StubSpots(),
        "candles": StubCandles(),
        "options": StubOptions(),
        "global_cues": StubGlobal(),
        "breadth": StubBreadth(),
        "flows": StubFlows(),
        "vix_history": StubVix(),
        "phase": StubPhase(),
        "narrative": StubNarrative(),
        "clock": StubClock(),
    }
    parts.update(overrides)
    return GetPreMarketView(**parts)  # type: ignore[arg-type]


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_it_returns_all_three_headline_indices(self) -> None:
        view = await build()(PreMarketQuery())

        assert [card.symbol for card in view.headline] == ["NIFTY", "BANKNIFTY", "SENSEX"]

    @pytest.mark.asyncio
    async def test_every_panel_shares_one_as_of(self) -> None:
        """The reason this is one endpoint: panels computed from different
        instants disagree on screen for reasons nobody can diagnose."""
        view = await build()(PreMarketQuery())

        assert view.as_of == NOW

    @pytest.mark.asyncio
    async def test_the_deep_panels_resolve_for_the_focused_index(self) -> None:
        view = await build()(PreMarketQuery(focus="NIFTY"))

        assert view.levels is not None
        assert view.technicals is not None
        assert view.expected_move is not None
        assert view.regime is not None
        assert view.status.levels.availability is Availability.OK

    @pytest.mark.asyncio
    async def test_only_nifty_gets_the_gift_implied_gap(self) -> None:
        view = await build()(PreMarketQuery())
        by_symbol = {card.symbol: card for card in view.headline}

        assert by_symbol["NIFTY"].implied_gap is not None
        assert by_symbol["BANKNIFTY"].implied_gap is None
        assert by_symbol["SENSEX"].implied_gap is None

    @pytest.mark.asyncio
    async def test_an_unknown_focus_falls_back_to_nifty(self) -> None:
        view = await build()(PreMarketQuery(focus="NOTANINDEX"))

        assert view.focus == "NIFTY"


class TestPartialFailure:
    @pytest.mark.asyncio
    async def test_a_dead_option_chain_costs_one_panel_not_the_page(self) -> None:
        """The whole reason SectionStatus is a domain concept."""
        view = await build(options=StubOptions(fail=True))(PreMarketQuery())

        assert view.status.options.availability is Availability.UNAVAILABLE
        assert view.status.options.reason is not None
        # The ladder needs only candles, and still renders.
        assert view.levels is not None
        assert view.status.levels.availability is Availability.OK
        assert view.headline

    @pytest.mark.asyncio
    async def test_dead_candles_cost_levels_but_not_the_chain(self) -> None:
        view = await build(candles=StubCandles(fail=True))(PreMarketQuery())

        assert view.levels is None
        assert view.status.levels.availability is Availability.UNAVAILABLE
        assert view.status.options.availability is Availability.OK

    @pytest.mark.asyncio
    async def test_the_reason_names_the_fault_so_it_can_be_acted_on(self) -> None:
        view = await build(global_cues=StubGlobal(fail=True))(PreMarketQuery())

        reason = view.status.global_cues.reason
        assert reason is not None
        assert "UpstreamError" in reason

    @pytest.mark.asyncio
    async def test_every_upstream_failing_still_produces_a_view(self) -> None:
        view = await build(
            spots=StubSpots(fail=True),
            candles=StubCandles(fail=True),
            options=StubOptions(fail=True),
            global_cues=StubGlobal(fail=True),
            breadth=StubBreadth(fail=True),
        )(PreMarketQuery())

        assert view.as_of == NOW
        assert len(view.headline) == 3
        assert view.status.headline.availability is Availability.UNAVAILABLE
        assert view.regime is not None


class TestSensex:
    @pytest.mark.asyncio
    async def test_breadth_is_not_even_asked_for_and_says_why(self) -> None:
        """SENSEX has no constituent weight table. Rendering an empty chart
        would read as a bug; naming the gap reads as a fact."""
        breadth = StubBreadth()

        view = await build(breadth=breadth)(PreMarketQuery(focus="SENSEX"))

        assert breadth.calls == []
        assert view.status.breadth.availability is Availability.UNAVAILABLE
        assert "weight table" in (view.status.breadth.reason or "")

    @pytest.mark.asyncio
    async def test_its_levels_and_technicals_still_resolve(self) -> None:
        view = await build()(PreMarketQuery(focus="SENSEX"))

        assert view.levels is not None
        assert view.technicals is not None


class TestProvenance:
    @pytest.mark.asyncio
    async def test_the_badge_reports_the_weakest_leg(self) -> None:
        """A page is only as live as its least live input."""
        mocked = OptionsReading(
            expiry=None, days_to_expiry=1, spot=None, atm_strike=None, pcr_oi=None,
            pcr_change=None, total_call_oi=None, total_put_oi=None, max_pain=None,
            call_wall=None, put_wall=None, gamma_flip=None, atm_iv=None,
            iv_percentile=None, atm_straddle=None, india_vix=None,
            india_vix_change_percent=None, source="mock",
        )

        view = await build(options=StubOptions(reading=mocked))(PreMarketQuery())

        assert view.source == "mock"

    @pytest.mark.asyncio
    async def test_a_thin_vix_history_reports_its_count_not_a_rank(self) -> None:
        view = await build(vix_history=StubVix(history=(12.0, 13.0)))(PreMarketQuery())

        assert view.volatility is not None
        assert view.volatility.vix_percentile is None
        assert view.volatility.vix_sample_sessions == 2


class TestNarrative:
    @pytest.mark.asyncio
    async def test_no_briefing_yet_is_a_named_state_not_a_blank(self) -> None:
        view = await build()(PreMarketQuery())

        assert view.narrative is None
        assert view.status.narrative.availability is Availability.UNAVAILABLE
        assert "briefing" in (view.status.narrative.reason or "")
