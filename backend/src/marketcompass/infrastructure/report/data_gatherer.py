"""Gathers every deterministic number/series the report needs.

Reuses the same read-only market_data + options_analytics services the agents use
(so no new data source), and the copilot indicators helper for the technical read.
Each section is wrapped so one failing tool degrades that field to ``None`` rather
than losing the whole report. Owns a committing session (write-through caches
persist), so it works request-less in the scheduled worker.

Lives in infrastructure — the sanctioned place to reach across contexts.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from marketcompass.contexts.copilot.domain import indicators
from marketcompass.contexts.market_data.api.dependencies import (
    build_market_services_from,
)
from marketcompass.contexts.market_data.application.queries import (
    HistoryQuery,
    OptionChainQuery,
    QuoteQuery,
)
from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.contexts.market_data.domain.market_data import CandleInterval
from marketcompass.contexts.options_analytics.api.dependencies import (
    build_options_analytics_services_from,
)
from marketcompass.contexts.report.application.ports import ReportDataPort, ReportInputs
from marketcompass.contexts.report.domain.report import (
    Candle,
    InstrumentSummary,
    Level,
    OptionsSummary,
    OptionStrikeBar,
    TechnicalRead,
)
from marketcompass.infrastructure.observability.structured_logging import get_logger
from marketcompass.shared_kernel.types.identifiers import TenantId

log = get_logger(__name__)

# How many intraday bars to show on the candlestick, and strikes around ATM on
# the OI bar chart.
_CANDLE_BARS = 30
_STRIKE_SPAN = 8
_MIN_DAILY = 2
_YEAR_SESSIONS = 252


def _f(value: Decimal | float | int | None) -> float | None:
    return None if value is None else float(value)


def _is_mock(source: str) -> bool:
    return "mock" in source.lower() or "sim" in source.lower()


class ReportDataGatherer:
    """Implements ``ReportDataPort`` over the shared market/options services."""

    def __init__(self, container: Any) -> None:
        self._container = container

    async def gather(self, tenant_id: TenantId, symbol: str) -> ReportInputs:
        instrument = InstrumentSymbol.parse(symbol.strip().upper())
        async with self._container.database.session() as session:
            market = build_market_services_from(self._container, session)
            options = build_options_analytics_services_from(self._container, session)

            summary, source = await self._summary(market, tenant_id, instrument, symbol)
            candles, technical_series = await self._candles(market, tenant_id, instrument)
            technical = _technical(technical_series)
            option_bars, opt_summary, walls = await self._options(
                market, options, tenant_id, instrument, symbol
            )
            technical = _with_levels(technical, summary, walls)

        return ReportInputs(
            summary=summary,
            technical=technical,
            candles=candles,
            option_bars=option_bars,
            options=opt_summary,
            source=source,
        )

    async def _summary(
        self, market: Any, tenant_id: TenantId, instrument: Any, symbol: str
    ) -> tuple[InstrumentSummary, str]:
        ltp = change = change_pct = None
        source = "live"
        try:
            q = await market.spot(QuoteQuery(tenant_id=tenant_id, instrument=instrument))
            ltp, change, change_pct = _f(q.price), _f(q.change), _f(q.change_percent)
            source = "mock" if _is_mock(q.provenance.source.value) else "live"
        except Exception as exc:
            log.warning("report_spot_failed", symbol=symbol, error=repr(exc))

        prev_close = day_open = day_high = day_low = w52_low = w52_high = None
        try:
            daily = await market.history(
                HistoryQuery(
                    tenant_id=tenant_id, instrument=instrument, interval=CandleInterval.D1, days=400
                )
            )
            candles = daily.candles
            if len(candles) >= _MIN_DAILY:
                prev_close = _f(candles[-2].close)
                day_open = _f(candles[-1].open)
                day_high = _f(candles[-1].high)
                day_low = _f(candles[-1].low)
            window = candles[-_YEAR_SESSIONS:] if len(candles) > _YEAR_SESSIONS else candles
            if window:
                w52_low = _f(min(c.low for c in window))
                w52_high = _f(max(c.high for c in window))
            if _is_mock(daily.provenance.source.value):
                source = "mock"
        except Exception as exc:
            log.warning("report_daily_failed", symbol=symbol, error=repr(exc))

        summary = InstrumentSummary(
            symbol=symbol,
            ltp=ltp,
            change=change,
            change_pct=change_pct,
            prev_close=prev_close,
            day_open=day_open,
            day_high=day_high,
            day_low=day_low,
            week52_low=w52_low,
            week52_high=w52_high,
            source=source,
        )
        return summary, source

    async def _candles(
        self, market: Any, tenant_id: TenantId, instrument: Any
    ) -> tuple[tuple[Candle, ...], Any]:
        try:
            series = await market.history(
                HistoryQuery(
                    tenant_id=tenant_id,
                    instrument=instrument,
                    interval=CandleInterval.M15,
                    days=5,
                )
            )
        except Exception as exc:
            log.warning("report_intraday_failed", error=repr(exc))
            return (), None

        recent = series.candles[-_CANDLE_BARS:]
        bars = tuple(
            Candle(
                label=f"{c.opened_at:%d %H:%M}",
                open=float(c.open),
                high=float(c.high),
                low=float(c.low),
                close=float(c.close),
            )
            for c in recent
        )
        return bars, series

    async def _options(
        self, market: Any, options: Any, tenant_id: TenantId, instrument: Any, symbol: str
    ) -> tuple[tuple[OptionStrikeBar, ...], OptionsSummary, dict[str, float | None]]:
        bars: tuple[OptionStrikeBar, ...] = ()
        pcr = vix = atm = total_ce = total_pe = None
        call_wall = put_wall = None
        try:
            chain = await market.option_chain(
                OptionChainQuery(tenant_id=tenant_id, instrument=instrument)
            )
            pcr = _f(chain.put_call_ratio)
            vix = _f(chain.india_vix)
            atm = _f(chain.atm_strike)
            total_ce = float(chain.total_call_open_interest)
            total_pe = float(chain.total_put_open_interest)
            rows = [r for r in chain.strikes if r.call or r.put]
            # Centre the bar chart on ATM.
            if atm is not None and rows:
                rows.sort(key=lambda r: abs(float(r.strike) - atm))
                rows = sorted(rows[: _STRIKE_SPAN * 2 + 1], key=lambda r: float(r.strike))
            bars = tuple(
                OptionStrikeBar(
                    strike=float(r.strike),
                    call_oi=float(r.call.open_interest) if r.call else 0.0,
                    put_oi=float(r.put.open_interest) if r.put else 0.0,
                )
                for r in rows
            )
            if bars:
                call_wall = max(bars, key=lambda b: b.call_oi).strike
                put_wall = max(bars, key=lambda b: b.put_oi).strike
        except Exception as exc:
            log.warning("report_chain_failed", symbol=symbol, error=repr(exc))

        max_pain = pcr_change = gamma_flip = None
        try:
            view = await options.oi_view(tenant_id, instrument.value)
            max_pain = _num(view, "max_pain")
            pcr_change = _num(view, "pcr_change")
        except Exception as exc:
            log.warning("report_oiview_failed", symbol=symbol, error=repr(exc))
        try:
            gex = await options.gex(tenant_id, instrument.value)
            gamma_flip = _num(gex, "gamma_flip")
        except Exception as exc:
            log.warning("report_gex_failed", symbol=symbol, error=repr(exc))

        summary = OptionsSummary(
            pcr=pcr,
            pcr_change=pcr_change,
            max_pain=max_pain,
            atm_strike=atm,
            total_call_oi=total_ce,
            total_put_oi=total_pe,
            gamma_flip=gamma_flip,
            india_vix=vix,
        )
        walls = {"call_wall": call_wall, "put_wall": put_wall, "max_pain": max_pain}
        return bars, summary, walls


def _num(data: dict[str, Any], key: str) -> float | None:
    value = data.get(key)
    return float(value) if isinstance(value, (int, float, Decimal)) else None


def _technical(series: Any) -> TechnicalRead:
    if series is None or not series.candles:
        return TechnicalRead(
            ema20=None, ema50=None, rsi14=None, vwap=None, atr14=None
        )
    candles = series.candles
    r = indicators.compute(
        [float(c.high) for c in candles],
        [float(c.low) for c in candles],
        [float(c.close) for c in candles],
        [float(c.volume) for c in candles],
    )
    supports: list[Level] = []
    resistances: list[Level] = []
    if r.swing_support is not None:
        supports.append(Level(price=float(r.swing_support), label="Swing"))
    if r.swing_resistance is not None:
        resistances.append(Level(price=float(r.swing_resistance), label="Swing"))
    return TechnicalRead(
        ema20=_f(r.ema20),
        ema50=_f(r.ema50),
        rsi14=_f(r.rsi14),
        vwap=_f(r.vwap),
        atr14=_f(r.atr14),
        resistances=tuple(resistances),
        supports=tuple(supports),
    )


def _with_levels(
    technical: TechnicalRead,
    summary: InstrumentSummary,
    walls: dict[str, float | None],
) -> TechnicalRead:
    """Fold option walls into the S/R lists (heaviest OI = wall), keeping 2 each."""
    resistances = list(technical.resistances)
    supports = list(technical.supports)
    call_wall = walls.get("call_wall")
    put_wall = walls.get("put_wall")
    if call_wall is not None:
        resistances.append(Level(price=call_wall, label="Call wall"))
    if put_wall is not None:
        supports.append(Level(price=put_wall, label="Put wall"))
    ltp = summary.ltp
    if ltp is not None:
        resistances = sorted(
            {round(r.price): r for r in resistances if r.price >= ltp}.values(),
            key=lambda x: x.price,
        )[:2]
        supports = sorted(
            {round(s.price): s for s in supports if s.price <= ltp}.values(),
            key=lambda x: -x.price,
        )[:2]
    return TechnicalRead(
        ema20=technical.ema20,
        ema50=technical.ema50,
        rsi14=technical.rsi14,
        vwap=technical.vwap,
        atr14=technical.atr14,
        resistances=tuple(resistances),
        supports=tuple(supports),
    )


# Structural check: the gatherer satisfies the port.
_: type[ReportDataPort] = ReportDataGatherer
