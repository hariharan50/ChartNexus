"""Pure option-chain header math for the ingest path.

Deliberately self-contained: a bounded context may not import another, so the
same PCR / ATM / max-pain definitions that ``options_analytics`` computes on read
are restated here for the writer. They are small and stable enough that the
duplication is cheaper than a shared dependency, and both sides are covered by
their own tests.

No I/O, no framework — just arithmetic over already-parsed rows.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal

_CALL = "CE"
_PUT = "PE"


@dataclass(frozen=True, slots=True)
class MetricRow:
    """The minimum a header metric needs from one leg."""

    strike: Decimal
    option_type: str
    oi: int


def total_call_oi(rows: Iterable[MetricRow]) -> int:
    return sum(row.oi for row in rows if row.option_type == _CALL)


def total_put_oi(rows: Iterable[MetricRow]) -> int:
    return sum(row.oi for row in rows if row.option_type == _PUT)


def pcr_oi(rows: Iterable[MetricRow]) -> Decimal | None:
    """ΣPE.oi / ΣCE.oi. ``None`` (not 0) when there is no call interest."""
    materialised = list(rows)
    calls = total_call_oi(materialised)
    if calls <= 0:
        return None
    puts = total_put_oi(materialised)
    return (Decimal(puts) / Decimal(calls)).quantize(Decimal("0.0001"))


def atm_strike(spot: Decimal, strikes: Sequence[Decimal]) -> Decimal | None:
    """The listed strike nearest spot, or ``None`` when nothing is listed."""
    if not strikes:
        return None
    return min(strikes, key=lambda strike: abs(strike - spot))


def max_pain_strike(rows: Iterable[MetricRow], strikes: Sequence[Decimal]) -> Decimal | None:
    """The settlement level minimising total intrinsic value owed to holders."""
    materialised = list(rows)
    if not strikes or not materialised:
        return None

    best: Decimal | None = None
    least = Decimal("Infinity")
    for candidate in strikes:
        pain = Decimal(0)
        for row in materialised:
            if row.option_type == _CALL:
                pain += row.oi * max(Decimal(0), candidate - row.strike)
            elif row.option_type == _PUT:
                pain += row.oi * max(Decimal(0), row.strike - candidate)
        if pain < least:
            least = pain
            best = candidate
    return best
