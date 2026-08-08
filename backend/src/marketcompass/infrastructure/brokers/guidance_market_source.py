"""Feeds the signals context one assembled snapshot from data it may not import.

``signals`` may not reach ``market_data`` or ``options_analytics`` directly, so
this adapter — living in ``infrastructure``, which may — does the fetching and
hands back a plain ``MarketSnapshot``. It pulls the option chain and candle
history from ``market_data`` (which carry real provenance), reuses
``options_analytics``' pure OI math for PCR / max-pain / ATM, and reads the
dealer-gamma levels from the GEX view.

Provenance is merged as the *worst* of the market-data legs: the chain and the
history each report live / cached / mock, and a snapshot is only as trustworthy
as its shakiest input. The GEX view derives from stored snapshots and carries no
separate provenance, so it never improves the reported source — only the live
legs can.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.market_data.api.dependencies import build_market_services
from marketcompass.contexts.market_data.application.queries import (
    GetHistory,
    GetOptionChain,
    HistoryQuery,
    OptionChainQuery,
)
from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.contexts.market_data.domain.market_data import (
    CandleInterval,
    OptionChain,
)
from marketcompass.contexts.options_analytics.api.dependencies import (
    build_options_analytics_services,
)
from marketcompass.contexts.options_analytics.application.gex_service import GetGex
from marketcompass.contexts.options_analytics.domain.oi_math import (
    ChainRow,
    atm_strike,
    max_pain,
    pcr_oi,
)
from marketcompass.contexts.signals.domain.inputs import MarketSnapshot
from marketcompass.contexts.signals.domain.models import Provenance
from marketcompass.shared_kernel.domain.errors import UpstreamError
from marketcompass.shared_kernel.types.identifiers import TenantId

# Five days of 5-minute bars: enough for a 21-bar EMA and a 14-bar ATR with room
# to spare, without asking the broker for a range it caps.
_HISTORY_INTERVAL = CandleInterval.M5
_HISTORY_DAYS = 5


class GuidanceMarketSource:
    """Implements the signals ``MarketReadPort`` over market-data + analytics."""

    def __init__(
        self,
        *,
        option_chain: GetOptionChain,
        history: GetHistory,
        gex: GetGex,
    ) -> None:
        self._option_chain = option_chain
        self._history = history
        self._gex = gex

    async def read(self, tenant_id: TenantId, symbol: str) -> MarketSnapshot:
        instrument = InstrumentSymbol.parse(symbol)

        chain = await self._option_chain(
            OptionChainQuery(tenant_id=tenant_id, instrument=instrument)
        )
        candles = await self._history(
            HistoryQuery(
                tenant_id=tenant_id,
                instrument=instrument,
                interval=_HISTORY_INTERVAL,
                days=_HISTORY_DAYS,
            )
        )
        gex = await self._safe_gex(tenant_id, symbol)

        return _assemble(symbol, chain, candles, gex)

    async def _safe_gex(self, tenant_id: TenantId, symbol: str) -> dict[str, Any]:
        # GEX needs stored intraday snapshots; on a fresh day or a mock session it
        # legitimately has nothing. That must degrade the dealer-positioning leg,
        # not fail the whole guidance.
        try:
            return await self._gex(tenant_id, symbol)
        except (UpstreamError, ValueError, KeyError):
            return {}


def _assemble(
    symbol: str, chain: OptionChain, candles: Any, gex: dict[str, Any]
) -> MarketSnapshot:
    rows = _chain_rows(chain)
    strikes = sorted({row.strike for row in rows})
    spot = float(chain.spot_price)
    atm = atm_strike(spot, strikes) if strikes else None

    pcr = pcr_oi(rows) if rows else None
    pain = max_pain(rows, strikes) if rows and strikes else None
    call_chg = sum(row.oi_change for row in rows if row.is_call)
    put_chg = sum(row.oi_change for row in rows if row.is_put)

    frame = _latest_gex_frame(gex)
    ce_iv, pe_iv = _atm_skew(chain, atm)

    closes, highs, lows = _candle_arrays(candles)

    sources = [
        _to_provenance(chain),
        _to_provenance(candles),
    ]

    return MarketSnapshot(
        symbol=symbol,
        spot=spot,
        atm_strike=atm,
        lot_size=chain.lot_size,
        expiry_date=chain.expiry or None,
        pcr=(pcr if pcr and pcr > 0.0 else None),
        pcr_change=None,
        total_call_oi_chg=call_chg,
        total_put_oi_chg=put_chg,
        max_pain=(pain if pain and pain > 0.0 else None),
        bullish_pct=None,
        gex_net=_opt_float(frame.get("net_total")),
        call_wall=_opt_float(frame.get("call_wall")),
        put_wall=_opt_float(frame.get("put_wall")),
        gamma_flip=_opt_float(frame.get("gamma_flip")),
        net_cross=_opt_float(frame.get("net_cross")),
        iv_coverage=_opt_float(gex.get("iv_coverage")),
        iv_percentile=_opt_float(chain.iv_percentile),
        atm_call_iv=ce_iv,
        atm_put_iv=pe_iv,
        closes=closes,
        highs=highs,
        lows=lows,
        strikes=tuple(strikes),
        sources=tuple(sources),
    )


def _chain_rows(chain: OptionChain) -> list[ChainRow]:
    rows: list[ChainRow] = []
    for strike_row in chain.strikes:
        strike = float(strike_row.strike)
        if strike_row.call is not None:
            rows.append(_row(strike, "CE", strike_row.call))
        if strike_row.put is not None:
            rows.append(_row(strike, "PE", strike_row.put))
    return rows


def _row(strike: float, option_type: str, leg: Any) -> ChainRow:
    return ChainRow(
        strike=strike,
        option_type=option_type,
        oi=int(leg.open_interest),
        oi_change=int(leg.open_interest_change),
        ltp=float(leg.last_price),
        volume=int(leg.volume),
        iv=None if leg.implied_volatility is None else float(leg.implied_volatility),
    )


def _atm_skew(chain: OptionChain, atm: float | None) -> tuple[float | None, float | None]:
    if atm is None:
        return None, None
    nearest = min(chain.strikes, key=lambda row: abs(float(row.strike) - atm), default=None)
    if nearest is None:
        return None, None
    ce = nearest.call.implied_volatility if nearest.call else None
    pe = nearest.put.implied_volatility if nearest.put else None
    return (None if ce is None else float(ce), None if pe is None else float(pe))


def _latest_gex_frame(gex: dict[str, Any]) -> dict[str, Any]:
    frames = gex.get("frames") or []
    return frames[-1] if frames else {}


def _candle_arrays(candles: Any) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    bars = getattr(candles, "candles", ())
    closes = tuple(float(bar.close) for bar in bars)
    highs = tuple(float(bar.high) for bar in bars)
    lows = tuple(float(bar.low) for bar in bars)
    return closes, highs, lows


def _to_provenance(payload: Any) -> Provenance:
    source = payload.provenance.source
    return Provenance(source.value)


def _opt_float(value: Any) -> float | None:
    return None if value is None else float(value)


def build_guidance_market_source(request: Request, session: AsyncSession) -> GuidanceMarketSource:
    """Wire the market source from the two contexts' own service builders.

    Reusing ``build_market_services`` and ``build_options_analytics_services``
    keeps the broker/resolver wiring defined once. This factory lives in
    ``infrastructure`` — not in the signals API layer — because only
    infrastructure may reach across into another context's assembly.
    """
    market = build_market_services(request, session)
    analytics = build_options_analytics_services(request, session)
    return GuidanceMarketSource(
        option_chain=market.option_chain,
        history=market.history,
        gex=analytics.gex,
    )
