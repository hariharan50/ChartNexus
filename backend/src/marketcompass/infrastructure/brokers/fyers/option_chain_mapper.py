"""FYERS option-chain payloads to canonical chains.

Two traps, both documented as having caused real bugs in the source system:

1. **The keys are snake_case.** ``strike_price``, ``option_type``, ``oi``,
   ``oich``, ``ltpchp``, ``fp``. A camelCase parser does not error — it silently
   reads ``None`` for every strike, collapses the whole chain onto strike 0, and
   produces output that looks like plausible mock data.

2. **The underlying is in the same list.** It appears as an entry with
   ``strike_price == -1`` and no ``option_type``. Treating it as an option
   inserts a phantom strike; ignoring it loses the spot price, index change,
   and futures reference price, which appear nowhere else in the response.

Expiries come from the broker's ``expiryData`` rather than being computed. Weekly
expiry days move for holidays and have changed by exchange circular more than
once; a locally computed Thursday is wrong exactly when it matters most.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.contexts.market_data.domain.market_data import (
    DataSource,
    OptionChain,
    OptionQuote,
    Provenance,
    StrikeRow,
)
from marketcompass.shared_kernel.domain.errors import UpstreamError

UNDERLYING_STRIKE = Decimal(-1)
"""Sentinel FYERS uses to mark the index leg inside the options list."""

_CALL = "CE"
_PUT = "PE"

_DATE_FORMATS = ("%d-%m-%Y", "%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y")
_MIN_EPOCH = 10**9  # ~2001; anything smaller is not a timestamp

# Expiry epochs are read in exchange time. An expiry timestamp late in the UTC
# day is already the next calendar day in India, and resolving it as UTC would
# name the wrong expiry.
_EXCHANGE_TZ = ZoneInfo("Asia/Kolkata")


def to_option_chain(
    payload: dict[str, Any],
    *,
    instrument: InstrumentSymbol,
    fetched_at: datetime,
    expiry: str | None = None,
) -> OptionChain:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise UpstreamError("fyers", "The broker returned no option chain data.")

    entries = data.get("optionsChain")
    if not isinstance(entries, list) or not entries:
        raise UpstreamError("fyers", "The broker returned an empty option chain.")

    underlying: dict[str, Any] = {}
    by_strike: dict[Decimal, dict[str, OptionQuote]] = {}

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        strike = _decimal(entry.get("strike_price"))
        option_type = str(entry.get("option_type") or "").strip().upper()

        # The index leg: no option type, strike -1.
        if strike is None or strike == UNDERLYING_STRIKE or not option_type:
            if not underlying:
                underlying = entry
            continue

        if option_type not in (_CALL, _PUT):
            continue

        by_strike.setdefault(strike, {})[option_type] = _to_option_quote(entry)

    if not by_strike:
        raise UpstreamError("fyers", "The option chain contained no tradeable strikes.")

    spot = _decimal(underlying.get("ltp"))
    if spot is None:
        raise UpstreamError("fyers", "The option chain did not include a spot price.")

    strikes = tuple(
        StrikeRow(strike=strike, call=legs.get(_CALL), put=legs.get(_PUT))
        for strike, legs in sorted(by_strike.items())
    )

    expiries = _parse_expiries(data.get("expiryData"))
    resolved_expiry = expiry or (expiries[0] if expiries else _fallback_expiry(fetched_at))

    # FYERS attaches India VIX to every options-chain response (not just NIFTY's) —
    # a free ride, since a dedicated VIX fetch would cost its own quota slot.
    vix = data.get("indiavixData")
    vix = vix if isinstance(vix, dict) else {}

    return OptionChain(
        instrument=instrument,
        expiry=resolved_expiry,
        spot_price=spot,
        strikes=strikes,
        provenance=Provenance(source=DataSource.LIVE, fetched_at=fetched_at),
        expiries=expiries,
        lot_size=_int(data.get("lotSize")) or None,
        change_percent=_decimal(underlying.get("ltpchp")),
        future_price=_decimal(underlying.get("fp")),
        india_vix=_decimal(vix.get("ltp")),
        india_vix_change_percent=_decimal(vix.get("ltpchp")),
    )


def _to_option_quote(entry: dict[str, Any]) -> OptionQuote:
    return OptionQuote(
        last_price=_decimal(entry.get("ltp")) or Decimal(0),
        open_interest=_int(entry.get("oi")),
        # `oich` — open interest change. Not `oiChange`.
        open_interest_change=_int(entry.get("oich")),
        volume=_int(entry.get("volume")),
        implied_volatility=_decimal(entry.get("iv")),
        bid=_decimal(entry.get("bid")),
        ask=_decimal(entry.get("ask")),
        delta=_decimal(entry.get("delta")),
    )


def parse_expiry_epochs(payload: dict[str, Any]) -> dict[str, str]:
    """ISO expiry date to the broker's own epoch for it.

    FYERS selects an expiry by ``timestamp`` - the epoch it publishes alongside
    each date in ``expiryData`` - and there is no documented rule for deriving
    that epoch from the date. It is read back rather than computed: a guessed
    timestamp does not error, it silently returns the default chain, which is
    indistinguishable from the request having worked.
    """
    data = payload.get("data")
    raw = data.get("expiryData") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return {}

    epochs: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        iso = _normalise_date(item.get("date")) or _normalise_date(item.get("expiry"))
        stamp = item.get("expiry")
        if iso and stamp is not None and iso not in epochs:
            epochs[iso] = str(stamp)
    return epochs


def _parse_expiries(raw: Any) -> tuple[str, ...]:
    """Normalise the broker's expiry list to ISO dates.

    Entries look like ``{"date": "30-07-2026", "expiry": "1785...")}``. Both
    forms are accepted; unparseable entries are dropped rather than guessed at.
    """
    if not isinstance(raw, list):
        return ()

    seen: list[str] = []
    for item in raw:
        candidate: str | None = None
        if isinstance(item, dict):
            candidate = _normalise_date(item.get("date")) or _normalise_date(item.get("expiry"))
        else:
            candidate = _normalise_date(item)

        if candidate and candidate not in seen:
            seen.append(candidate)

    return tuple(sorted(seen))


def _normalise_date(value: Any) -> str | None:
    """Accept the four representations FYERS has been observed to use."""
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    # Epoch seconds, sometimes delivered as a numeric string.
    if text.isdigit():
        epoch = int(text)
        if epoch >= _MIN_EPOCH:
            return datetime.fromtimestamp(epoch, tz=_EXCHANGE_TZ).date().isoformat()
        return None

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC).date().isoformat()
        except ValueError:
            continue

    # Unrecognised. Dropping it is correct: a wrong expiry silently prices the
    # wrong contract.
    return None


def _fallback_expiry(fetched_at: datetime) -> str:
    """Only reached when the broker omitted expiryData entirely."""
    return fetched_at.date().isoformat()


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return parsed


def _int(value: Any) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        return int(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError):
        return 0
