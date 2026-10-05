"""Read-only market-data tools Hella reasons over.

Each tool is a thin bridge from a LangChain ``StructuredTool`` to an existing
use case in ``market_data`` or ``options_analytics``. This is the sanctioned
cross-context bridge location — infrastructure may import any context; the
copilot context itself never does.

The tenant and the per-request services are captured in a closure, so the model
only ever supplies a symbol (and, for history, an interval) — never identity or
wiring. Every tool returns a compact human-readable string: the model reads it
as evidence, and keeping it terse controls token cost.

All tools are read-only. There is no tool that places or modifies an order.
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

from langchain_core.tools import StructuredTool

from chartnexus.contexts.copilot.domain import indicators, skills
from chartnexus.contexts.market_data.api.dependencies import MarketServices
from chartnexus.contexts.market_data.application.queries import (
    HistoryQuery,
    OptionChainQuery,
    QuoteQuery,
)
from chartnexus.contexts.market_data.domain.instruments import InstrumentSymbol
from chartnexus.contexts.market_data.domain.market_data import (
    CandleInterval,
    CandleSeries,
    OptionChain,
)
from chartnexus.contexts.options_analytics.api.dependencies import OptionsAnalyticsServices
from chartnexus.shared_kernel.types.identifiers import TenantId

_INTERVALS = {i.value: i for i in CandleInterval}
# Lookback per interval for indicators — enough bars for EMA50/RSI without
# pulling the broker's full range on every call. Capped by the interval's own max.
_INDICATOR_DAYS = {
    CandleInterval.M1: 5,
    CandleInterval.M5: 5,
    CandleInterval.M15: 10,
    CandleInterval.H1: 30,
    CandleInterval.D1: 150,
}
# Need today + yesterday to read the previous session's OHLC.
_MIN_DAILY_CANDLES = 2
# Above this magnitude a value is a price (render whole); below, a ratio/%.
_PRICE_MAGNITUDE = 100.0


def build_agent_tools(
    tenant_id: TenantId,
    market: MarketServices,
    options: OptionsAnalyticsServices,
) -> list[StructuredTool]:
    """The full toolset for one request, bound to this tenant's providers."""

    # All tools share the request's SQLAlchemy AsyncSession, which forbids
    # concurrent use. The model may call tools in parallel (Anthropic parallel
    # tool use), and LangGraph runs those concurrently — so serialise every tool
    # body on one lock. The reads are fast (mostly cached), so the cost of
    # running them one-at-a-time is negligible next to a DB-session collision.
    lock = asyncio.Lock()

    def _serialise(fn: Callable[..., Awaitable[str]]) -> Callable[..., Awaitable[str]]:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> str:
            async with lock:
                return await fn(*args, **kwargs)

        return wrapper

    def _instrument(symbol: str) -> InstrumentSymbol:
        return InstrumentSymbol.parse(symbol.strip().upper())

    async def get_spot(symbol: str) -> str:
        """Current index spot (last traded price) with day change. `symbol`: NIFTY, BANKNIFTY, SENSEX."""
        quote = await market.spot(QuoteQuery(tenant_id=tenant_id, instrument=_instrument(symbol)))
        return (
            f"{symbol} spot {_num(quote.price)} "
            f"({_signed(quote.change)}, {_pct(quote.change_percent)}) "
            f"[{quote.provenance.source.value}]"
        )

    async def get_futures(symbol: str) -> str:
        """Front-month futures: price, day change, day high/low, volume. `symbol`: NIFTY, BANKNIFTY, SENSEX."""
        fut = await market.futures(QuoteQuery(tenant_id=tenant_id, instrument=_instrument(symbol)))
        return (
            f"{symbol} {fut.contract} future {_num(fut.price)} "
            f"({_signed(fut.change)}, {_pct(fut.change_percent)}); "
            f"day high {_num(fut.day_high)}, day low {_num(fut.day_low)}, "
            f"volume {fut.volume:,} [{fut.provenance.source.value}]"
        )

    async def get_ohlc(symbol: str, interval: str = "15m", days: int = 5) -> str:
        """Recent OHLC candles for price-action / technical analysis.

        `symbol`: NIFTY, BANKNIFTY, SENSEX. `interval`: 1m, 5m, 15m, 1h, 1d.
        `days`: lookback window (capped per interval). Returns the session range
        plus the most recent bars.
        """
        bar = _INTERVALS.get(interval, CandleInterval.M15)
        series = await market.history(
            HistoryQuery(
                tenant_id=tenant_id, instrument=_instrument(symbol), interval=bar, days=days
            )
        )
        return _fmt_series(symbol, series)

    async def get_previous_day_ohlc(symbol: str) -> str:
        """Yesterday's (previous session's) open/high/low/close. `symbol`: NIFTY, BANKNIFTY, SENSEX."""
        series = await market.history(
            HistoryQuery(
                tenant_id=tenant_id,
                instrument=_instrument(symbol),
                interval=CandleInterval.D1,
                days=5,
            )
        )
        daily = series.candles
        if len(daily) < _MIN_DAILY_CANDLES:
            return f"No previous-day candle available for {symbol}."
        prev = daily[-2]
        return (
            f"{symbol} previous session — open {_num(prev.open)}, high {_num(prev.high)}, "
            f"low {_num(prev.low)}, close {_num(prev.close)} [{series.provenance.source.value}]"
        )

    async def get_option_chain_summary(symbol: str) -> str:
        """Options snapshot: spot, ATM, PCR, total CE/PE OI, India VIX, and the heaviest-OI strikes.

        `symbol`: NIFTY, BANKNIFTY, SENSEX. Use for open-interest and options-flow reads.
        """
        chain = await market.option_chain(
            OptionChainQuery(tenant_id=tenant_id, instrument=_instrument(symbol))
        )
        return _fmt_chain(symbol, chain)

    async def get_max_pain_and_pcr(symbol: str) -> str:
        """Max pain, PCR (and its change since open), and total CE/PE OI with day changes.

        `symbol`: NIFTY, BANKNIFTY, SENSEX. This is the derived open-interest read.
        """
        view = await options.oi_view(tenant_id, _instrument(symbol).value)
        return (
            f"{symbol}: max pain {_g(view, 'max_pain')}, ATM {_g(view, 'atm_strike')}, "
            f"PCR {_g(view, 'pcr_oi')} (chg {_g(view, 'pcr_change')}); "
            f"total CE OI {_g(view, 'total_call_oi')} (chg {_g(view, 'total_call_oi_chg')}), "
            f"total PE OI {_g(view, 'total_put_oi')} (chg {_g(view, 'total_put_oi_chg')})"
        )

    async def get_gamma_exposure(symbol: str) -> str:
        """Dealer gamma: the gamma-flip / zero-gamma level. `symbol`: NIFTY, BANKNIFTY, SENSEX."""
        gex = await options.gex(tenant_id, _instrument(symbol).value)
        return f"{symbol}: gamma flip {_g(gex, 'gamma_flip')}"

    async def get_indicators(symbol: str, interval: str = "15m") -> str:
        """Technical indicators computed from candles: RSI(14), EMA20, EMA50, VWAP, ATR(14),
        and nearest swing support/resistance.

        `symbol`: NIFTY, BANKNIFTY, SENSEX. `interval`: 1m, 5m, 15m, 1h, 1d.
        Use for the momentum/trend/volatility read behind a technical call.
        """
        bar = _INTERVALS.get(interval, CandleInterval.M15)
        days = min(_INDICATOR_DAYS.get(bar, 10), bar.max_days)
        series = await market.history(
            HistoryQuery(
                tenant_id=tenant_id, instrument=_instrument(symbol), interval=bar, days=days
            )
        )
        return _fmt_indicators(symbol, series)

    async def get_market_status() -> str:
        """Whether the exchange is open now, the session date, and the data source."""
        status = await market.status(tenant_id)
        state = "OPEN" if status.is_open else "CLOSED"
        return (
            f"Market {state} on {status.session_date} ({status.time_ist} IST); "
            f"source {status.source.value}, hours {status.market_open}-{status.market_close}"
        )

    # Names come from the domain skill registry so the two can't desync.
    specs: list[tuple[Any, str, str]] = [
        (get_spot, skills.GET_SPOT, "Current index spot price with day change."),
        (
            get_futures,
            skills.GET_FUTURES,
            "Front-month futures price, day change, day high/low, volume.",
        ),
        (get_ohlc, skills.GET_OHLC, "Recent OHLC candles for technical / price-action analysis."),
        (
            get_previous_day_ohlc,
            skills.GET_PREVIOUS_DAY_OHLC,
            "Previous session's open/high/low/close.",
        ),
        (
            get_option_chain_summary,
            skills.GET_OPTION_CHAIN_SUMMARY,
            "Options snapshot: spot, ATM, PCR, total OI, VIX, heaviest strikes.",
        ),
        (
            get_max_pain_and_pcr,
            skills.GET_MAX_PAIN_AND_PCR,
            "Max pain, PCR and change, total CE/PE OI with day changes.",
        ),
        (get_gamma_exposure, skills.GET_GAMMA_EXPOSURE, "Dealer gamma flip / zero-gamma level."),
        (
            get_indicators,
            skills.GET_INDICATORS,
            "Technical indicators (RSI, EMA20/50, VWAP, ATR, swing S/R) from candles.",
        ),
        (
            get_market_status,
            skills.GET_MARKET_STATUS,
            "Whether the market is open and the data source.",
        ),
    ]
    return [
        StructuredTool.from_function(
            coroutine=_serialise(fn), name=name, description=fn.__doc__ or desc
        )
        for fn, name, desc in specs
    ]


# -- formatting -------------------------------------------------------------


def _fmt_series(symbol: str, series: CandleSeries) -> str:
    candles = series.candles
    if not candles:
        return f"No candles available for {symbol}."
    highs = max(c.high for c in candles)
    lows = min(c.low for c in candles)
    recent = candles[-8:]
    bars = "; ".join(
        f"{c.opened_at:%d-%b %H:%M} O{_num(c.open)} H{_num(c.high)} L{_num(c.low)} C{_num(c.close)}"
        for c in recent
    )
    return (
        f"{symbol} {series.interval.value} — range high {_num(highs)}, low {_num(lows)}, "
        f"last close {_num(candles[-1].close)} [{series.provenance.source.value}]. "
        f"Recent bars: {bars}"
    )


def _fmt_indicators(symbol: str, series: CandleSeries) -> str:
    candles = series.candles
    if not candles:
        return f"No candles available for {symbol} — indicators unavailable."
    highs = [float(c.high) for c in candles]
    lows = [float(c.low) for c in candles]
    closes = [float(c.close) for c in candles]
    volumes = [float(c.volume) for c in candles]
    r = indicators.compute(highs, lows, closes, volumes)
    return (
        f"{symbol} {series.interval.value} indicators ({len(candles)} bars, "
        f"{series.provenance.source.value}) — RSI14 {_num(r.rsi14)}, "
        f"EMA20 {_num(r.ema20)}, EMA50 {_num(r.ema50)}, VWAP {_num(r.vwap)}, "
        f"ATR14 {_num(r.atr14)}, swing support {_num(r.swing_support)}, "
        f"swing resistance {_num(r.swing_resistance)}, last close {_num(closes[-1])}"
    )


def _fmt_chain(symbol: str, chain: OptionChain) -> str:
    pcr = chain.put_call_ratio
    top_calls = sorted(
        (row for row in chain.strikes if row.call),
        key=lambda r: r.call.open_interest if r.call else 0,
        reverse=True,
    )[:3]
    top_puts = sorted(
        (row for row in chain.strikes if row.put),
        key=lambda r: r.put.open_interest if r.put else 0,
        reverse=True,
    )[:3]
    calls = ", ".join(f"{_num(r.strike)} ({r.call.open_interest:,})" for r in top_calls if r.call)
    puts = ", ".join(f"{_num(r.strike)} ({r.put.open_interest:,})" for r in top_puts if r.put)
    return (
        f"{symbol} chain (expiry {chain.expiry}) — spot {_num(chain.spot_price)}, "
        f"ATM {_num(chain.atm_strike)}, PCR {_num(pcr)}, "
        f"total CE OI {chain.total_call_open_interest:,}, total PE OI {chain.total_put_open_interest:,}, "
        f"India VIX {_num(chain.india_vix)} [{chain.provenance.source.value}]. "
        f"Heaviest call OI (resistance): {calls or 'n/a'}. "
        f"Heaviest put OI (support): {puts or 'n/a'}."
    )


def _num(value: Decimal | float | int | None) -> str:
    if value is None:
        return "n/a"
    v = float(value)
    return f"{v:,.0f}" if abs(v) >= _PRICE_MAGNITUDE else f"{v:.2f}"


def _signed(value: Decimal | None) -> str:
    if value is None:
        return "n/a"
    return (
        f"{float(value):+,.0f}" if abs(float(value)) >= _PRICE_MAGNITUDE else f"{float(value):+.2f}"
    )


def _pct(value: Decimal | None) -> str:
    return "n/a" if value is None else f"{float(value):+.2f}%"


def _g(data: dict[str, Any], key: str) -> str:
    return (
        _num(data.get(key))
        if isinstance(data.get(key), (int, float))
        else str(data.get(key, "n/a"))
    )
