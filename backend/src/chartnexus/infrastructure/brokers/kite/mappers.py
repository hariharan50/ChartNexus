"""Kite payloads → canonical market-data objects.

No Kite vocabulary escapes this module. Two Kite conventions to know:

* ``ohlc.close`` in a quote is the **previous session's** close, so day change
  is ``last_price - ohlc.close``. Kite's own ``net_change`` is not relied on:
  it reads zero for several instrument types.
* Kite publishes **no previous-day open interest**. ``previous_oi`` comes from
  the pre-open capture (:mod:`.prev_oi`); when that has not run, OI change is
  reported as unknown — ``previous_oi=None`` and a change of zero — rather than
  guessed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from chartnexus.contexts.market_data.domain.instruments import InstrumentSymbol
from chartnexus.contexts.market_data.domain.market_data import (
    Candle,
    CandleInterval,
    CandleSeries,
    DataSource,
    FuturesQuote,
    OpenInterestReading,
    OptionChain,
    OptionQuote,
    Provenance,
    Quote,
    StrikeRow,
)
from chartnexus.infrastructure.brokers.kite.instruments import KiteInstrument

IST = ZoneInfo("Asia/Kolkata")
_HUNDRED = Decimal(100)


def live(fetched_at: datetime) -> Provenance:
    return Provenance(source=DataSource.LIVE, fetched_at=fetched_at)


def to_quote(
    payload: Mapping[str, Any], *, instrument: InstrumentSymbol, fetched_at: datetime
) -> Quote:
    price = _decimal(payload.get("last_price"))
    if price is None:
        msg = f"no last price for {instrument.value}"
        raise ValueError(msg)
    ohlc = _ohlc(payload)
    change, change_percent = _change(price, ohlc.get("close"))
    return Quote(
        instrument=instrument,
        price=price,
        change=change,
        change_percent=change_percent,
        provenance=live(fetched_at),
        day_open=ohlc.get("open"),
        previous_close=ohlc.get("close"),
    )


def to_futures_quote(
    payload: Mapping[str, Any],
    *,
    instrument: InstrumentSymbol,
    contract: KiteInstrument,
    fetched_at: datetime,
    previous_oi: int | None = None,
) -> FuturesQuote:
    price = _decimal(payload.get("last_price"))
    if price is None:
        msg = f"no last price for {contract.tradingsymbol}"
        raise ValueError(msg)
    ohlc = _ohlc(payload)
    change, change_percent = _change(price, ohlc.get("close"))
    return FuturesQuote(
        instrument=instrument,
        contract=contract.tradingsymbol,
        expiry=contract.expiry.isoformat() if contract.expiry else "",
        price=price,
        change=change,
        change_percent=change_percent,
        volume=_int(payload.get("volume")),
        day_high=ohlc.get("high"),
        day_low=ohlc.get("low"),
        provenance=live(fetched_at),
        open_interest=_optional_int(payload.get("oi")),
        previous_open_interest=previous_oi,
        previous_close=ohlc.get("close"),
        day_open=ohlc.get("open"),
    )


def to_open_interest(
    payload: Mapping[str, Any],
    *,
    instrument: InstrumentSymbol,
    observed_at: datetime,
    previous_oi: int | None = None,
) -> OpenInterestReading | None:
    oi = _optional_int(payload.get("oi"))
    if oi is None:
        return None
    return OpenInterestReading(
        instrument=instrument,
        open_interest=oi,
        previous_open_interest=previous_oi,
        observed_at=observed_at,
    )


def to_option_quote(payload: Mapping[str, Any], *, previous_oi: int | None) -> OptionQuote | None:
    price = _decimal(payload.get("last_price"))
    if price is None:
        return None
    oi = _int(payload.get("oi"))
    ohlc = _ohlc(payload)
    change, change_percent = _change(price, ohlc.get("close"))
    raw_depth = payload.get("depth")
    depth: Mapping[str, Any] = raw_depth if isinstance(raw_depth, Mapping) else {}
    best_bid = _best(depth.get("buy"))
    best_ask = _best(depth.get("sell"))
    return OptionQuote(
        last_price=price,
        open_interest=oi,
        open_interest_change=(oi - previous_oi) if previous_oi is not None else 0,
        volume=_int(payload.get("volume")),
        # Kite quotes no IV or greeks; the market-data layer backfills IV.
        implied_volatility=None,
        bid=best_bid[0],
        ask=best_ask[0],
        change=change,
        change_percent=change_percent,
        previous_oi=previous_oi,
        bid_qty=best_bid[1],
        ask_qty=best_ask[1],
    )


def to_option_chain(
    *,
    instrument: InstrumentSymbol,
    expiry: date,
    expiries: Sequence[date],
    spot: Mapping[str, Any],
    contracts: Sequence[KiteInstrument],
    quotes: Mapping[str, Mapping[str, Any]],
    previous_oi: Mapping[int, int],
    fetched_at: datetime,
    future: Mapping[str, Any] | None = None,
    vix: Mapping[str, Any] | None = None,
) -> OptionChain:
    spot_price = _decimal(spot.get("last_price"))
    if spot_price is None:
        msg = f"no spot price for {instrument.value}"
        raise ValueError(msg)
    _, spot_change_percent = _change(spot_price, _ohlc(spot).get("close"))

    rows: dict[Decimal, dict[str, OptionQuote | None]] = {}
    lot_size: int | None = None
    for contract in contracts:
        if contract.strike is None:
            continue
        payload = quotes.get(contract.quote_key)
        if payload is None:
            continue
        lot_size = lot_size or contract.lot_size
        leg = to_option_quote(payload, previous_oi=previous_oi.get(contract.instrument_token))
        row = rows.setdefault(contract.strike, {"call": None, "put": None})
        row["call" if contract.instrument_type == "CE" else "put"] = leg

    vix_price, vix_change = (None, None)
    if vix is not None:
        vix_price = _decimal(vix.get("last_price"))
        if vix_price is not None:
            _, vix_change = _change(vix_price, _ohlc(vix).get("close"))

    return OptionChain(
        instrument=instrument,
        expiry=expiry.isoformat(),
        spot_price=spot_price,
        strikes=tuple(
            StrikeRow(strike=strike, call=legs["call"], put=legs["put"])
            for strike, legs in sorted(rows.items())
        ),
        provenance=live(fetched_at),
        expiries=tuple(item.isoformat() for item in expiries),
        lot_size=lot_size,
        change_percent=spot_change_percent,
        future_price=_decimal(future.get("last_price")) if future else None,
        india_vix=vix_price,
        india_vix_change_percent=vix_change,
    )


def to_candle_series(
    rows: Sequence[Sequence[Any]],
    *,
    instrument: InstrumentSymbol,
    interval: CandleInterval,
    fetched_at: datetime,
) -> CandleSeries:
    candles: list[Candle] = []
    seen: set[datetime] = set()
    for row in rows:
        candle = _candle(row)
        # Chunked requests can overlap at their seams; keep the first copy.
        if candle is not None and candle.opened_at not in seen:
            seen.add(candle.opened_at)
            candles.append(candle)
    candles.sort(key=lambda candle: candle.opened_at)
    return CandleSeries(
        instrument=instrument,
        interval=interval,
        candles=tuple(candles),
        provenance=live(fetched_at),
    )


# -- helpers --------------------------------------------------------------------


def _candle(row: Sequence[Any]) -> Candle | None:
    if len(row) < 6:  # noqa: PLR2004 — [ts, open, high, low, close, volume, (oi)]
        return None
    opened_at = _timestamp(row[0])
    values = [_decimal(value) for value in row[1:5]]
    if opened_at is None or any(value is None for value in values):
        return None
    open_, high, low, close = (value for value in values if value is not None)
    return Candle(
        opened_at=opened_at, open=open_, high=high, low=low, close=close, volume=_int(row[5])
    )


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        moment = value
    else:
        try:
            moment = datetime.fromisoformat(str(value))
        except ValueError:
            return None
    return moment if moment.tzinfo else moment.replace(tzinfo=IST)


def _ohlc(payload: Mapping[str, Any]) -> dict[str, Decimal | None]:
    raw = payload.get("ohlc")
    raw = raw if isinstance(raw, Mapping) else {}
    return {name: _decimal(raw.get(name)) for name in ("open", "high", "low", "close")}


def _change(
    price: Decimal, previous_close: Decimal | None
) -> tuple[Decimal | None, Decimal | None]:
    if previous_close is None or previous_close == 0:
        return None, None
    change = price - previous_close
    return change, (change / previous_close * _HUNDRED).quantize(Decimal("0.01"))


def _best(levels: Any) -> tuple[Decimal | None, int | None]:
    if not isinstance(levels, Sequence) or not levels:
        return None, None
    first = levels[0]
    if not isinstance(first, Mapping):
        return None, None
    price = _decimal(first.get("price"))
    # An empty book level is reported as price 0 by Kite, not as a missing one.
    if price is None or price == 0:
        return None, None
    return price, _optional_int(first.get("quantity"))


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    return _optional_int(value) or 0
