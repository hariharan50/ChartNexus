"""Per-session implied-volatility history, for the IV/HV/IVP Chart.

The thinnest service in the Options Lab, and the only one that spans days rather
than captures. It reads the durable per-session archive that ``market_ingestion``
rolls up and hands it over unchanged — no smoothing, no interpolation, no
percentile.

**IV Rank and IV Percentile are deliberately not computed here.** Both depend on
a lookback the reader chooses from the sidebar, and recomputing the whole payload
on the server every time someone changes "1 Year" to "3 Months" would be a round
trip for arithmetic over an array the client already holds. Same trade the rest
of the Lab makes.

``covered_sessions`` is the honest part of the payload. The archive only started
accruing when the rollup landed, so a request for a year may legitimately return
a fortnight, and a page that cannot tell a short history from a flat one will
draw a confident, wrong IV Percentile. The client labels the curve with this.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from marketcompass.contexts.options_analytics.application.ports import DailyIvReader
from marketcompass.shared_kernel.types.identifiers import TenantId

# India observes no DST; a fixed +05:30 offset, as everywhere else.
_IST = timezone(timedelta(hours=5, minutes=30))
_MAX_DAYS = 365
_MIN_DAYS = 1


class GetIvHistory:
    """Assembles the daily IV history for one instrument."""

    def __init__(self, *, readings: DailyIvReader, now_utc: Any = None) -> None:
        self._readings = readings
        self._now = now_utc or (lambda: datetime.now(UTC))

    async def __call__(self, tenant_id: TenantId, symbol: str, *, days: int) -> dict[str, Any]:
        window = max(_MIN_DAYS, min(_MAX_DAYS, days))
        # Calendar days back from the IST trading date: `session_date` is an IST
        # date, so bounding the range by a UTC one would move the edge by a day
        # for five and a half hours of every evening.
        end = self._now().astimezone(_IST).date()
        start = end - timedelta(days=window)

        readings = await self._readings.daily_iv(tenant_id, symbol, start=start, end=end)

        return {
            "instrument_id": symbol,
            "symbol": symbol,
            "requested_days": window,
            "covered_sessions": len(readings),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "sessions": [
                {
                    "d": reading.session_date.isoformat(),
                    "iv": round(reading.atm_iv, 3),
                    "future_close": reading.future_close,
                    "captures": reading.captures,
                }
                for reading in readings
            ],
        }
