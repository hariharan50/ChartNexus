"""PMS's ports, implemented against the contexts that own the data.

This is the sanctioned place to reach across bounded contexts, and the same
shape ``infrastructure/report/data_gatherer.py`` uses. ``contexts/pre_market/``
imports none of these upstream contexts — ``tests/architecture`` forbids it with
no exemption list — so every translation from their vocabulary into PMS's
happens here, once.

**Each adapter swallows its own faults into ``None``.** The query layer already
guards every leg, but a port that raises on "no chain published for SENSEX"
would make a normal absence indistinguishable from an outage. Genuine
transport faults still propagate, because the page should say so.

**The tenant is bound at construction, not threaded through every port.**
Nothing on this page varies by tenant — an index level is a fact about the
market — but the upstream services want a tenant on their queries, and passing
it through nine port signatures would put it in the domain's vocabulary for no
reason.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from chartnexus.contexts.market_breadth.application.get_fii_dii import FlowQuery
from chartnexus.contexts.market_breadth.application.get_index_analysis import (
    IndexQuery,
)
from chartnexus.contexts.market_data.application.queries import (
    HistoryQuery,
    OptionChainQuery,
    QuoteQuery,
)
from chartnexus.contexts.market_data.domain.instruments import InstrumentSymbol
from chartnexus.contexts.market_data.domain.market_data import CandleInterval
from chartnexus.contexts.pre_market.domain.readings import (
    BreadthReading,
    CandleSeries,
    FlowReading,
    GiftReading,
    GlobalContribution,
    GlobalReading,
    MarketPhase,
    OptionsReading,
    SpotReading,
)
from chartnexus.infrastructure.observability.structured_logging import get_logger
from chartnexus.shared_kernel.domain.levels import Bar
from chartnexus.shared_kernel.types.identifiers import TenantId

log = get_logger(__name__)

#: India observes no DST, so a fixed offset is exact. Expiry distance has to be
#: counted in the exchange's own day, not the server's: a box running UTC would
#: otherwise report yesterday's expiry as today's for five and a half hours
#: every evening.
_IST = timezone(timedelta(hours=5, minutes=30), "IST")

#: Index keys this context uses, mapped to the market catalog's spellings.
_LABELS: dict[str, str] = {
    "NIFTY": "NIFTY 50",
    "BANKNIFTY": "BANK NIFTY",
    "SENSEX": "SENSEX",
}

#: The breadth context keys NIFTY by its index name, not its instrument symbol.
_BREADTH_INDEX: dict[str, str] = {"NIFTY": "NIFTY50", "BANKNIFTY": "BANKNIFTY"}


def _f(value: Decimal | float | int | None) -> float | None:
    return None if value is None else float(value)


def _d(value: Decimal | float | int | str | None) -> Decimal | None:
    if value is None:
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _source_of(provenance: Any) -> str:
    """Normalise a provider's provenance to the badge's three tiers."""
    try:
        raw = str(provenance.source.value).lower()
    except AttributeError:
        return "live"
    if "mock" in raw or "sim" in raw:
        return "mock"
    return "cached" if "cach" in raw else "live"


class MarketSpotAdapter:
    """Implements ``SpotSource`` over ``market_data``."""

    def __init__(self, market: Any, tenant_id: TenantId) -> None:
        self._market = market
        self._tenant_id = tenant_id

    async def get_spots(self, symbols: Any) -> dict[str, SpotReading]:
        """One quote per index. A partial board is a good board.

        Fetched in sequence rather than gathered: these share one broker quota
        and one database session, and three quick reads are not worth the
        contention of running them concurrently against both.
        """
        readings: dict[str, SpotReading] = {}
        for symbol in symbols:
            try:
                quote = await self._market.spot(
                    QuoteQuery(
                        tenant_id=self._tenant_id,
                        instrument=InstrumentSymbol.parse(symbol),
                    )
                )
            except Exception as exc:
                log.warning("pre_market_spot_failed", symbol=symbol, error=repr(exc))
                continue
            readings[symbol] = SpotReading(
                symbol=symbol,
                label=_LABELS.get(symbol, symbol),
                price=quote.price,
                previous_close=_d(getattr(quote, "previous_close", None)),
                day_open=_d(getattr(quote, "day_open", None)),
                change=_d(getattr(quote, "change", None)),
                change_percent=_d(getattr(quote, "change_percent", None)),
                source=_source_of(quote.provenance),
            )
        return readings


class MarketCandleAdapter:
    """Implements ``DailyCandleSource`` over ``market_data``.

    One call per index for the whole year — the broker's own cap for daily bars
    is 365 days, so pivots, the EMA stack, ATR and the 52-week range all come
    out of a single request rather than four.
    """

    def __init__(self, market: Any, tenant_id: TenantId) -> None:
        self._market = market
        self._tenant_id = tenant_id

    async def get_daily(self, symbol: str, *, days: int) -> CandleSeries | None:
        series = await self._market.history(
            HistoryQuery(
                tenant_id=self._tenant_id,
                instrument=InstrumentSymbol.parse(symbol),
                interval=CandleInterval.D1,
                days=days,
            )
        )
        bars = tuple(
            Bar(
                open=float(candle.open),
                high=float(candle.high),
                low=float(candle.low),
                close=float(candle.close),
            )
            for candle in series.candles
        )
        if not bars:
            return None
        return CandleSeries(
            symbol=symbol,
            bars=bars,
            live=_source_of(series.provenance) != "mock",
        )


class OptionsAdapter:
    """Implements ``OptionSnapshotSource`` over ``market_data`` + ``options_analytics``.

    Two upstreams because they answer different halves: the chain carries India
    VIX, ATM IV and the straddle legs, while the OI view carries max pain and
    the heavy strikes. Either may be absent without the other.
    """

    def __init__(self, market: Any, options: Any, tenant_id: TenantId) -> None:
        self._market = market
        self._options = options
        self._tenant_id = tenant_id

    async def get_options(self, symbol: str) -> OptionsReading | None:
        chain = await self._chain(symbol)
        oi = await self._oi(symbol)
        if chain is None and oi is None:
            return None

        expiry = self._expiry(chain)
        return OptionsReading(
            expiry=expiry,
            days_to_expiry=self._days_to(expiry),
            spot=_d(getattr(chain, "spot", None)) if chain else None,
            atm_strike=_d(getattr(oi, "atm_strike", None) if oi else None)
            or _d(getattr(chain, "atm_strike", None) if chain else None),
            pcr_oi=_d(getattr(oi, "pcr_oi", None) if oi else None)
            or _d(getattr(chain, "pcr", None) if chain else None),
            pcr_change=_d(getattr(oi, "pcr_change", None)) if oi else None,
            total_call_oi=getattr(oi, "total_call_oi", None) if oi else None,
            total_put_oi=getattr(oi, "total_put_oi", None) if oi else None,
            max_pain=_d(getattr(oi, "max_pain", None)) if oi else None,
            call_wall=self._wall(oi, "call"),
            put_wall=self._wall(oi, "put"),
            gamma_flip=None,
            atm_iv=_d(getattr(chain, "atm_iv", None)) if chain else None,
            iv_percentile=_d(getattr(chain, "iv_percentile", None)) if chain else None,
            atm_straddle=self._straddle(chain),
            india_vix=_d(getattr(chain, "india_vix", None)) if chain else None,
            india_vix_change_percent=_d(getattr(chain, "india_vix_change_percent", None))
            if chain
            else None,
            source=_source_of(chain.provenance) if chain is not None else "live",
        )

    async def _chain(self, symbol: str) -> Any | None:
        try:
            return await self._market.option_chain(
                OptionChainQuery(
                    tenant_id=self._tenant_id,
                    instrument=InstrumentSymbol.parse(symbol),
                )
            )
        except Exception as exc:
            log.warning("pre_market_chain_failed", symbol=symbol, error=repr(exc))
            return None

    async def _oi(self, symbol: str) -> Any | None:
        try:
            return await self._options.oi(symbol)
        except Exception as exc:
            log.warning("pre_market_oi_failed", symbol=symbol, error=repr(exc))
            return None

    @staticmethod
    def _expiry(chain: Any | None) -> date | None:
        raw = getattr(chain, "expiry", None) if chain else None
        if isinstance(raw, date):
            return raw
        if isinstance(raw, str):
            try:
                return date.fromisoformat(raw)
            except ValueError:
                return None
        return None

    @staticmethod
    def _days_to(expiry: date | None) -> int | None:
        """Calendar days, floored at one.

        Zero would make every volatility scaling collapse to nothing on expiry
        day, which is the one session where the range matters most.
        """
        if expiry is None:
            return None
        return max(1, (expiry - datetime.now(tz=_IST).date()).days)

    @staticmethod
    def _wall(oi: Any | None, side: str) -> Decimal | None:
        """The heaviest strike on one side.

        Named "wall" by convention only. It is where positioning sits, not a
        level that will hold, and the UI is required to say so.
        """
        strikes = getattr(oi, "strikes", None) if oi else None
        if not strikes:
            return None
        field = "call_oi" if side == "call" else "put_oi"
        best = max(strikes, key=lambda row: getattr(row, field, 0) or 0, default=None)
        if best is None or not getattr(best, field, 0):
            return None
        return _d(getattr(best, "strike", None))

    @staticmethod
    def _straddle(chain: Any | None) -> Decimal | None:
        """CE + PE at the money — the market's own price for a move."""
        if chain is None:
            return None
        call = _d(getattr(chain, "atm_call_ltp", None))
        put = _d(getattr(chain, "atm_put_ltp", None))
        if call is None or put is None:
            return None
        total = call + put
        return total if total > 0 else None


class GlobalCueAdapter:
    """Implements ``GlobalCueSource`` over ``global_markets``."""

    def __init__(self, global_services: Any) -> None:
        self._global = global_services

    async def get_global(self) -> GlobalReading | None:
        view = await self._global.view()
        gift = view.implied
        quote = view.gift

        return GlobalReading(
            pressure_score=view.pressure.score,
            pressure_band=view.pressure.band.value,
            contributions=tuple(
                GlobalContribution(
                    key=item.key,
                    label=item.label,
                    region=item.region,
                    change_percent=item.change_percent,
                    points=item.points,
                )
                for item in view.pressure.contributions
            ),
            missing=tuple(view.pressure.missing),
            macro=tuple(
                GlobalContribution(
                    key=market.key,
                    label=market.label,
                    region=market.region.value,
                    change_percent=row.change_percent or Decimal(0),
                    points=Decimal(0),
                )
                for market in view.markets
                if market.macro and (row := view.quotes.get(market.key)) is not None
            ),
            gift=GiftReading(
                level=gift.gift_level if gift else (quote.price if quote else None),
                change=quote.change if quote else None,
                change_percent=quote.change_percent if quote else None,
                overnight_high=quote.day_high if quote else None,
                overnight_low=quote.day_low if quote else None,
                gap_points=gift.gap_points if gift else None,
                gap_percent=gift.gap_percent if gift else None,
                signal=gift.signal.value if gift else None,
            )
            if (gift is not None or quote is not None)
            else None,
        )


class BreadthAdapter:
    """Implements ``BreadthSource`` over ``market_breadth``."""

    def __init__(self, breadth: Any, tenant_id: TenantId) -> None:
        self._breadth = breadth
        self._tenant_id = tenant_id

    async def get_breadth(self, index: str) -> BreadthReading | None:
        key = _BREADTH_INDEX.get(index)
        if key is None:
            # No weight table for this index — an absence, not a fault.
            return None

        view = await self._breadth.advance_decline(IndexQuery(tenant_id=self._tenant_id, index=key))
        return BreadthReading(
            advances=getattr(view, "advances", None),
            declines=getattr(view, "declines", None),
            unchanged=getattr(view, "unchanged", None),
            priced=getattr(view, "priced", None),
            universe=getattr(view, "universe", None),
        )


class FlowAdapter:
    """Implements ``FlowSource`` over ``market_breadth``."""

    def __init__(self, breadth: Any, tenant_id: TenantId) -> None:
        self._breadth = breadth
        self._tenant_id = tenant_id

    async def get_flows(self) -> FlowReading | None:
        summary = await self._breadth.fii_dii_summary(FlowQuery(tenant_id=self._tenant_id))
        cash = getattr(summary, "cash", None)
        if cash is None:
            return None
        return FlowReading(
            session_date=getattr(cash, "session_date", None),
            fii_net=_d(getattr(cash, "fii_net", None)),
            dii_net=_d(getattr(cash, "dii_net", None)),
        )


class MarketPhaseAdapter:
    """Implements ``MarketPhasePort`` over ``market_data``'s status read."""

    def __init__(self, market: Any) -> None:
        self._market = market

    async def get_phase(self) -> MarketPhase | None:
        status = await self._market.status()
        return MarketPhase(
            is_open=bool(getattr(status, "is_open", False)),
            session_date=str(getattr(status, "session_date", "")),
            time_ist=str(getattr(status, "time_ist", "")),
            opens_ist=str(getattr(status, "market_open", "09:15")),
            closes_ist=str(getattr(status, "market_close", "15:30")),
        )


class EmptyVixHistory:
    """No India VIX series exists yet.

    The broker publishes VIX only as a spot reading attached to every option
    chain — there is no candle series and nothing has ever stored one per
    session. Returning an empty tuple rather than ``None`` is deliberate: the
    count is what the page prints beside the missing percentile, and it is the
    honest answer to "why is this blank".
    """

    async def get_vix_history(self, *, days: int) -> tuple[float, ...]:  # noqa: ARG002
        return ()


class NoNarrative:
    """No morning prose until the narrative phase ships."""

    async def get_narrative(self) -> None:
        return None
