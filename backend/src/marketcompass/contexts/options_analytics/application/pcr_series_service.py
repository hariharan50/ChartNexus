"""Chain-wide totals through the session, for the Put-Call Ratio tool.

Three stacked charts read one payload: the put/call ratio, the two sides' OI
change, and the two sides' total OI — all against the tradable future.

Where ``GetOiSeries`` answers "what did these particular contracts do", this
collapses the whole chain to one number per side per capture. That makes the
payload small enough (six numbers a snapshot, ~20 KB a session) that the
timeframe can be applied on the client, which is why — unlike the Multi OI
endpoint — this one takes no interval parameter.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from marketcompass.contexts.options_analytics.application.ports import (
    ChainProvider,
    ChainSnapshot,
    ProviderChain,
    SnapshotReader,
)
from marketcompass.contexts.options_analytics.application.session import (
    drop_future,
    future_of,
    iso,
    session_open_frame,
    session_open_utc,
)
from marketcompass.shared_kernel.types.identifiers import TenantId

_MIN_INTRADAY_SNAPSHOTS = 2


class GetPcrSeries:
    """Assembles the Put-Call Ratio payload for one instrument."""

    def __init__(
        self,
        *,
        provider: ChainProvider,
        snapshots: SnapshotReader,
        now_utc: Any = None,
    ) -> None:
        self._provider = provider
        self._snapshots = snapshots
        self._now = now_utc or (lambda: datetime.now(UTC))

    async def __call__(self, tenant_id: TenantId, symbol: str) -> dict[str, Any]:
        now = self._now()
        chain = await self._provider.fetch(tenant_id, symbol)
        snaps = drop_future(
            await self._snapshots.day_snapshots(tenant_id, symbol, trade_date_utc=now), now
        )

        if len(snaps) < _MIN_INTRADAY_SNAPSHOTS:
            return _empty(symbol, chain, now)

        ordered = sorted(snaps, key=lambda snap: snap.captured_at)
        reconstructed = session_open_frame(ordered)
        if reconstructed is not None:
            ordered = [reconstructed, *ordered]

        totals = [_totals(snap) for snap in ordered]

        return {
            "instrument_id": symbol,
            "symbol": symbol,
            "expiry_date": chain.expiry,
            "lot_size": chain.lot_size,
            "open_ts": iso(ordered[0].captured_at),
            "now_ts": iso(ordered[-1].captured_at),
            "data_quality": "intraday",
            "open_is_estimated": reconstructed is not None,
            "t": [iso(snap.captured_at) for snap in ordered],
            "fut": [future_of(snap) for snap in ordered],
            "pcr": [total.pcr for total in totals],
            "call_oi": [total.call_oi for total in totals],
            "put_oi": [total.put_oi for total in totals],
            "call_oi_chg": [total.call_chg for total in totals],
            "put_oi_chg": [total.put_chg for total in totals],
        }


class _Totals:
    """One capture collapsed to a per-side summary."""

    __slots__ = ("call_chg", "call_oi", "pcr", "put_chg", "put_oi")

    def __init__(self, call_oi: int, put_oi: int, call_chg: int, put_chg: int) -> None:
        self.call_oi = call_oi
        self.put_oi = put_oi
        self.call_chg = call_chg
        self.put_chg = put_chg
        # `None`, never 0, when there is no call interest to divide by.
        #
        # `oi_math.pcr_oi` returns 0.0 for this case, which is right for the
        # Open Interest page — a headline figure has to render something. A
        # *line* is different: 0 draws a floor the market never printed and
        # anchors the axis to it, where `None` simply breaks. Same definition,
        # different honest answer at the undefined point.
        self.pcr = (put_oi / call_oi) if call_oi > 0 else None


def _totals(snapshot: ChainSnapshot) -> _Totals:
    call_oi = put_oi = call_chg = put_chg = 0
    for row in snapshot.rows:
        if row.is_call:
            call_oi += row.oi
            call_chg += row.oi_change
        else:
            put_oi += row.oi
            put_chg += row.oi_change
    # Summed from the legs' own day-change rather than differenced against the
    # open. The broker's `oi_change` is the authority, and the two diverge the
    # moment a strike is delisted mid-session.
    return _Totals(call_oi, put_oi, call_chg, put_chg)


def _empty(symbol: str, chain: ProviderChain, now: datetime) -> dict[str, Any]:
    """A well-formed payload for a day with nothing archived yet.

    Not an error: before two captures land there is genuinely no series, and the
    page should say so rather than fail.
    """
    return {
        "instrument_id": symbol,
        "symbol": symbol,
        "expiry_date": chain.expiry,
        "lot_size": chain.lot_size,
        "open_ts": iso(session_open_utc(now)),
        "now_ts": iso(now),
        "data_quality": "empty",
        "open_is_estimated": False,
        "t": [],
        "fut": [],
        "pcr": [],
        "call_oi": [],
        "put_oi": [],
        "call_oi_chg": [],
        "put_oi_chg": [],
    }
