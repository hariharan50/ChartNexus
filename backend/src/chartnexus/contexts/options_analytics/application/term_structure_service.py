"""At-the-money implied volatility across expiries — the volatility term structure.

The one Options Lab service that reads **only** live chains and no archive at
all, and it has to: a term structure is several expiries priced at the *same
instant*, and the snapshot archive holds exactly one expiry per session. The
ingest worker fetches the chain with no expiry argument, so what it stores is
always the nearest contract, rolling forward as each one dies. There is no
historical term structure to be had, and this service does not pretend
otherwise — it takes no ``trade_date``.

What it does instead is ask the broker for each requested expiry's chain and
read the money off each one. That is a real curve, as of now, and it refreshes
with the page's poll.

The at-the-money reading is the mean of the call and put implied volatility at
the strike nearest spot, ignoring an unquoted side — the same rule
``market_data``'s ``atm_implied_volatility`` applies to a live chain and the
same one the daily IV rollup stores, so the number means one thing across the
whole system.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

from chartnexus.contexts.options_analytics.application.ports import (
    ChainProvider,
    ProviderChain,
)
from chartnexus.contexts.options_analytics.application.session import iso
from chartnexus.contexts.options_analytics.domain.oi_math import ChainRow
from chartnexus.shared_kernel.types.identifiers import TenantId

# India observes no DST; a fixed +05:30 offset, as everywhere else.
_IST = timezone(timedelta(hours=5, minutes=30))
#: How many expiries one request may ask for. A term structure is read point by
#: point, and past a handful the curve says less rather than more — the same
#: reasoning behind the contract picker's cap.
MAX_EXPIRIES = 5
_IV_PLACES = 3


class GetTermStructure:
    """Assembles the live volatility term structure for one instrument."""

    def __init__(self, *, provider: ChainProvider, now_utc: Any = None) -> None:
        self._provider = provider
        self._now = now_utc or (lambda: datetime.now(UTC))

    async def __call__(
        self, tenant_id: TenantId, symbol: str, *, expiries: list[str]
    ) -> dict[str, Any]:
        now = self._now()
        wanted = _dedupe(expiries)[:MAX_EXPIRIES]

        points: list[dict[str, Any]] = []
        spot: float | None = None

        for expiry in wanted:
            chain = await self._provider.fetch(tenant_id, symbol, expiry=expiry)
            if spot is None:
                spot = chain.spot
            points.append(
                {
                    # What the broker actually answered with, not what was asked
                    # for: a provider handed an expiry it does not list falls
                    # back to the nearest, and a curve labelled with the request
                    # would quietly plot the same chain twice.
                    "expiry": chain.expiry or expiry,
                    "atm_iv": _atm_iv(chain),
                    "days_to_expiry": _days_away(chain.expiry or expiry, now),
                }
            )

        # Sorted by the date, not by the order asked for: a curve is read left
        # to right along the calendar.
        points.sort(key=lambda point: point["expiry"])

        return {
            "instrument_id": symbol,
            "symbol": symbol,
            "spot": round(spot, 2) if spot is not None else 0.0,
            "as_of": iso(now),
            "points": points,
        }


def _atm_iv(chain: ProviderChain) -> float | None:
    """The chain's at-the-money volatility, or ``None`` if it was not quoted.

    ``None`` rather than a substitute: an expiry the broker priced no volatility
    on has no point on the curve, and interpolating one from its neighbours
    would invent the very number the reader came for.
    """
    if chain.spot is None or chain.spot <= 0 or not chain.rows:
        return None

    atm = _nearest_strike(chain.rows, chain.spot)
    if atm is None:
        return None

    quoted = [
        row.iv for row in chain.rows if row.strike == atm and row.iv is not None and row.iv > 0
    ]
    if not quoted:
        return None
    return round(sum(quoted) / len(quoted), _IV_PLACES)


def _nearest_strike(rows: tuple[ChainRow, ...], spot: float) -> float | None:
    best: float | None = None
    best_gap = float("inf")
    for row in rows:
        gap = abs(row.strike - spot)
        if gap < best_gap:
            best_gap = gap
            best = row.strike
    return best


def _days_away(expiry: str, now: datetime) -> int | None:
    """Calendar days to expiry, on the IST trading date. Never negative."""
    try:
        target = date.fromisoformat(expiry[:10])
    except ValueError:
        return None
    return max(0, (target - now.astimezone(_IST).date()).days)


def _dedupe(expiries: list[str]) -> list[str]:
    """Preserve order, drop repeats and blanks.

    A repeated expiry would cost a broker call to draw the same point twice.
    """
    seen: set[str] = set()
    out: list[str] = []
    for expiry in expiries:
        cleaned = expiry.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
    return out
