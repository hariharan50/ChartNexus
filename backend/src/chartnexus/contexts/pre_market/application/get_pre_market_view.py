"""The whole PMS page, assembled in one read.

**One query, not eleven.** The regime score, the level ladder and the gap card
all describe the same instant. Eleven independently polled endpoints would let
them drift apart on screen — a score computed from an 09:04 quote set sitting
beside a ladder drawn from an 09:06 one, disagreeing for reasons no user could
diagnose. That is the screenshot a trader posts as evidence the product is
broken, and it is entirely preventable.

**Partial failure is a good response.** This reads from four upstream contexts
and any of them can be down. Every leg is wrapped so a failure becomes a named
``SectionStatus`` rather than an exception that takes the page with it. A dead
option chain costs the derivatives panel; it must not cost the level ladder,
which needs only candles.

**The expensive work is not in the request.** The daily candle history is one
call per symbol and everything downstream of it — pivots, EMA stack, ATR, the
52-week range — is arithmetic over the result. The chain and the global board
are already cached by the contexts that own them. What is left is a handful of
reads, gathered in parallel, behind a whole-view cache.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import datetime
from typing import TypeVar

from chartnexus.contexts.pre_market.application.ports import (
    BreadthSource,
    Clock,
    DailyCandleSource,
    FlowSource,
    GlobalCueSource,
    MarketPhasePort,
    NarrativeSource,
    OptionSnapshotSource,
    SpotSource,
    VixHistorySource,
)
from chartnexus.contexts.pre_market.domain import compose
from chartnexus.contexts.pre_market.domain.readings import (
    BY_SYMBOL,
    HEADLINE_INDICES,
    BreadthReading,
    CandleSeries,
    FlowReading,
    GlobalReading,
    MarketPhase,
    NarrativeReading,
    OptionsReading,
    Sources,
    SpotReading,
)
from chartnexus.contexts.pre_market.domain.view import (
    PreMarketView,
    SectionStatus,
    SectionStatuses,
)
from chartnexus.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)

T = TypeVar("T")

#: A year of daily bars — the broker's own cap for this resolution, and enough
#: for a 200-EMA and a 52-week range in a single call.
_HISTORY_DAYS = 365

#: How far back the VIX percentile looks. Same window, so the two rank against
#: comparable samples.
_VIX_DAYS = 365


@dataclass(frozen=True, slots=True)
class PreMarketQuery:
    """Which index the deep panels describe.

    The three headline cards always render; only the panels below them are
    scoped to one instrument, because a level ladder for three indices at once
    is a table nobody reads.
    """

    focus: str = "NIFTY"


class GetPreMarketView:
    """Read the overnight world, weigh it, and say what it implies for today."""

    def __init__(
        self,
        *,
        spots: SpotSource,
        candles: DailyCandleSource,
        options: OptionSnapshotSource,
        global_cues: GlobalCueSource,
        breadth: BreadthSource,
        flows: FlowSource,
        vix_history: VixHistorySource,
        phase: MarketPhasePort,
        narrative: NarrativeSource,
        clock: Clock,
    ) -> None:
        self._spots = spots
        self._candles = candles
        self._options = options
        self._global = global_cues
        self._breadth = breadth
        self._flows = flows
        self._vix_history = vix_history
        self._phase = phase
        self._narrative = narrative
        self._clock = clock

    async def __call__(self, query: PreMarketQuery) -> PreMarketView:
        now = self._clock.now()
        focus = query.focus if query.focus in BY_SYMBOL else "NIFTY"
        index = BY_SYMBOL[focus]

        symbols = [item.symbol for item in HEADLINE_INDICES]
        failures: dict[str, str] = {}

        # Tasks rather than a bare ``gather`` of coroutines: ``gather``'s
        # return type collapses to a union of every leg, and the assembly below
        # is only checkable if each leg keeps its own type.
        spots = asyncio.create_task(
            self._guard("headline", failures, self._spots.get_spots(symbols), {})
        )
        series = asyncio.create_task(
            self._guard(
                "levels", failures, self._candles.get_daily(focus, days=_HISTORY_DAYS), None
            )
        )
        options = asyncio.create_task(
            self._guard("options", failures, self._options.get_options(focus), None)
        )
        global_cues = asyncio.create_task(
            self._guard("global_cues", failures, self._global.get_global(), None)
        )
        breadth = asyncio.create_task(
            self._guard(
                "breadth",
                failures,
                self._breadth.get_breadth(focus) if index.breadth_tracked else _none(),
                None,
            )
        )
        flows = asyncio.create_task(self._guard("flows", failures, self._flows.get_flows(), None))
        vix_history = asyncio.create_task(
            self._guard(
                "volatility", failures, self._vix_history.get_vix_history(days=_VIX_DAYS), ()
            )
        )
        phase = asyncio.create_task(self._guard("phase", failures, self._phase.get_phase(), None))
        narrative = asyncio.create_task(
            self._guard("narrative", failures, self._narrative.get_narrative(), None)
        )

        # No ``return_exceptions`` needed: ``_guard`` swallows its own, so a
        # failing leg has already become a recorded fault by this point.
        await asyncio.gather(
            spots, series, options, global_cues, breadth, flows, vix_history, phase, narrative
        )

        return self._assemble(
            now=now,
            index_symbol=focus,
            spots=spots.result(),
            series=series.result(),
            options=options.result(),
            global_cues=global_cues.result(),
            breadth=breadth.result(),
            flows=flows.result(),
            vix_history=vix_history.result(),
            phase=phase.result(),
            narrative=narrative.result(),
            failures=failures,
        )

    # -- gathering -----------------------------------------------------------

    async def _guard(
        self, section: str, failures: dict[str, str], awaitable: Awaitable[T], fallback: T
    ) -> T:
        """Await one leg, recording a fault instead of propagating it.

        The reason string is kept and surfaced on the section, because "the
        broker refused" and "there is no chain for this instrument" lead a
        reader to do different things, and a blank panel says neither.
        """
        try:
            return await awaitable
        except Exception as exc:
            log.warning("pre_market_section_failed", section=section, error=repr(exc))
            failures[section] = type(exc).__name__
            return fallback

    # -- assembly ------------------------------------------------------------

    def _assemble(
        self,
        *,
        now: datetime,
        index_symbol: str,
        spots: dict[str, SpotReading],
        series: CandleSeries | None,
        options: OptionsReading | None,
        global_cues: GlobalReading | None,
        breadth: BreadthReading | None,
        flows: FlowReading | None,
        vix_history: tuple[float, ...],
        phase: MarketPhase | None,
        narrative: NarrativeReading | None,
        failures: dict[str, str],
    ) -> PreMarketView:
        index = BY_SYMBOL[index_symbol]

        technicals = compose.technicals_of(series)
        atr = compose.atr_of(technicals)

        gift_level = global_cues.gift.level if global_cues and global_cues.gift else None
        headline = tuple(
            compose.headline_card(
                definition,
                spots.get(definition.symbol),
                atr=atr if definition.symbol == index_symbol else None,
                # Only NIFTY has an overnight contract of its own.
                gift_level=gift_level if definition.symbol == "NIFTY" else None,
            )
            for definition in HEADLINE_INDICES
        )

        focused = spots.get(index_symbol)
        spot_price = focused.price if focused else None

        levels = compose.level_map_of(spot_price, series, options, atr=atr)
        volatility = compose.volatility_of(options, vix_history)
        expected = compose.expected_move_of(spot_price, options, atr=atr)
        focus_gap = next((card.gap for card in headline if card.symbol == index_symbol), None)
        regime = compose.regime_of(technicals, options, global_cues, breadth, gap=focus_gap)

        sources = Sources(
            parts={
                **{f"spot:{symbol}": reading.source for symbol, reading in spots.items()},
                **({"options": options.source} if options else {}),
            }
        )

        return PreMarketView(
            as_of=now,
            phase=phase
            or MarketPhase(
                is_open=False,
                session_date=now.date().isoformat(),
                time_ist=now.strftime("%H:%M"),
                opens_ist="09:15",
                closes_ist="15:30",
            ),
            focus=index_symbol,
            focus_label=index.label,
            source=sources.weakest(),
            status=SectionStatuses(
                headline=_status("headline", failures, bool(spots)),
                levels=_status("levels", failures, levels is not None),
                technicals=_status("levels", failures, technicals is not None),
                volatility=_status("options", failures, volatility is not None),
                expected_move=_status("options", failures, expected is not None),
                options=_status("options", failures, options is not None),
                global_cues=_status("global_cues", failures, global_cues is not None),
                breadth=(
                    SectionStatus.unavailable(
                        f"{index.label} has no constituent weight table, so "
                        "participation cannot be counted for it."
                    )
                    if not index.breadth_tracked
                    else _status("breadth", failures, breadth is not None)
                ),
                flows=_status("flows", failures, flows is not None),
                regime=SectionStatus.ok()
                if regime.inputs_present
                else SectionStatus.unavailable("No inputs answered."),
                narrative=_status("narrative", failures, narrative is not None),
            ),
            headline=headline,
            levels=levels,
            technicals=technicals,
            volatility=volatility,
            expected_move=expected,
            options=options,
            global_cues=global_cues,
            breadth=breadth,
            flows=flows,
            regime=regime,
            narrative=narrative,
        )


async def _none() -> None:
    """An already-satisfied awaitable, for legs that are skipped by design."""
    return None


_REASONS: dict[str, str] = {
    "headline": "The quote provider did not answer.",
    "levels": "No daily history came back, so levels and indicators cannot be derived.",
    "options": "The option chain did not answer.",
    "global_cues": "The overnight board did not answer.",
    "breadth": "The constituent board did not answer.",
    "flows": "The exchange participant file did not answer.",
    "volatility": "No India VIX history has accrued yet.",
    "narrative": "No briefing has been written for today yet.",
}


def _status(section: str, failures: dict[str, str], resolved: bool) -> SectionStatus:
    """A section's flag, naming the fault when there was one.

    A fault and an empty answer are different states: the first is worth
    retrying, the second is the truth about this instrument today.
    """
    if section in failures:
        return SectionStatus.unavailable(
            f"{_REASONS.get(section, 'Upstream read failed.')} ({failures[section]})"
        )
    if not resolved:
        return SectionStatus.unavailable(_REASONS.get(section, "No data."))
    return SectionStatus.ok()
