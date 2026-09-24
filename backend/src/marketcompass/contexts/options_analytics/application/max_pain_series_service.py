"""Max pain through the session, for the Intraday Max Pain chart.

Where the Max Pain page's bar chart answers "where is max pain *now*", this
answers "where has it been going". Max pain is not a fixed level: it migrates
as writers reposition, and the migration is the reading. A max pain stepping
down toward spot all morning is a different market from one pinned while spot
drifts up into it, and a single snapshot cannot tell those apart.

One number per capture, against the tradable future - the same shape as
``GetPcrSeries``, which this mirrors, including its three tiers:

    INTRADAY   (>=2 stored captures today) - real open vs the whole session
    LIVE_PROXY (0 or 1)                    - open-vs-now off the live chain
    EMPTY      (before the bell)           - no session to draw two ends of

**Stored where stored, computed where not.** The ingest worker already writes
``max_pain_strike`` on every capture, so an archived frame is a straight read -
no re-pricing 375 strikes against 750 legs eighty times a request. The frames
``session_open_frame`` and ``live_proxy_frames`` reconstruct carry rows but no
header values, so those get priced here with the very same
``oi_math.max_pain`` the bar chart uses. Reading only the stored field would
open the series with a hole at 09:15; using a different formula would let the
two panels on one page disagree.
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
    live_proxy_frames,
    session_open_frame,
    session_open_utc,
)
from marketcompass.contexts.options_analytics.domain.oi_math import max_pain
from marketcompass.shared_kernel.types.identifiers import TenantId

_MIN_INTRADAY_SNAPSHOTS = 2


class GetMaxPainSeries:
    """Assembles the Intraday Max Pain payload for one instrument."""

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

    async def __call__(
        self, tenant_id: TenantId, symbol: str, *, trade_date: datetime | None = None
    ) -> dict[str, Any]:
        now = self._now()
        # Live reads today; Historical replays the picked archived session.
        as_of = trade_date or now
        chain = await self._provider.fetch(tenant_id, symbol)
        snaps = await self._snapshots.day_snapshots(tenant_id, symbol, trade_date_utc=as_of)
        # Only the live day is clipped to "now"; a past session is whole.
        if trade_date is None:
            snaps = drop_future(snaps, now)

        if len(snaps) < _MIN_INTRADAY_SNAPSHOTS:
            # A past day with nothing archived is empty - never today's live chain.
            if trade_date is not None:
                return _empty(symbol, chain, now)
            return self._live_proxy(symbol, chain, snaps, now)

        ordered = sorted(snaps, key=lambda snap: snap.captured_at)
        reconstructed = session_open_frame(ordered)
        if reconstructed is not None:
            ordered = [reconstructed, *ordered]

        return _payload(
            symbol,
            chain,
            ordered,
            quality="intraday",
            open_is_estimated=reconstructed is not None,
        )

    def _live_proxy(
        self,
        symbol: str,
        chain: ProviderChain,
        snaps: list[ChainSnapshot],
        now: datetime,
    ) -> dict[str, Any]:
        """The tier for a day the ingest worker has not archived.

        Two points - the reconstructed open and now - which is honestly all
        there is. The page says so rather than drawing a two-point line that
        looks like a session where max pain never moved.
        """
        stored = snaps[0] if snaps else None
        rows = stored.rows if stored is not None else chain.rows
        spot = (stored.spot if stored is not None else None) or chain.spot
        frames = live_proxy_frames(
            rows,
            now,
            spot=spot,
            future_price=stored.future_price if stored is not None else None,
        )
        if not frames:
            return _empty(symbol, chain, now)

        return _payload(symbol, chain, frames, quality="live_proxy", open_is_estimated=True)


def _payload(
    symbol: str,
    chain: ProviderChain,
    frames: list[ChainSnapshot],
    *,
    quality: str,
    open_is_estimated: bool,
) -> dict[str, Any]:
    return {
        "instrument_id": symbol,
        "symbol": symbol,
        "expiry_date": chain.expiry,
        "lot_size": chain.lot_size,
        "spot": _spot_of(frames, chain),
        "open_ts": iso(frames[0].captured_at),
        "now_ts": iso(frames[-1].captured_at),
        "data_quality": quality,
        "open_is_estimated": open_is_estimated,
        "t": [iso(snap.captured_at) for snap in frames],
        "fut": [future_of(snap) for snap in frames],
        "max_pain": [_pain_of(snap) for snap in frames],
    }


def _spot_of(frames: list[ChainSnapshot], chain: ProviderChain) -> float:
    """The index level that belongs with the frames being returned.

    The newest frame's own spot first, then the live chain's. Resolved the same
    way ``GetOiView`` resolves it, and for the same reason: replaying an
    archived session must report where the index was *then*, not where it is
    now. Taking the live chain's unconditionally put this payload 950 points
    away from the very same page's profile panel on an archived day.
    """
    for snapshot in reversed(frames):
        if snapshot.spot is not None and snapshot.spot > 0:
            return snapshot.spot
    return chain.spot if chain.spot is not None else 0.0


def _pain_of(snapshot: ChainSnapshot) -> float | None:
    """This capture's max pain: the stored figure, or priced from its rows.

    ``None`` rather than 0.0 when there is nothing to price. Zero would draw
    the line down to the axis floor and drag the shared price scale with it,
    turning a missing point into a crash that never happened.
    """
    if snapshot.max_pain is not None and snapshot.max_pain > 0:
        return snapshot.max_pain
    if not snapshot.rows:
        return None

    strikes = sorted({row.strike for row in snapshot.rows})
    priced = max_pain(snapshot.rows, strikes)
    return priced if priced > 0 else None


def _empty(symbol: str, chain: ProviderChain, now: datetime) -> dict[str, Any]:
    """A well-formed payload for a day with nothing archived yet.

    Not an error: before two captures land there is genuinely no series, and
    the page should say so rather than fail.
    """
    return {
        "instrument_id": symbol,
        "symbol": symbol,
        "expiry_date": chain.expiry,
        "lot_size": chain.lot_size,
        "spot": chain.spot,
        "open_ts": iso(session_open_utc(now)),
        "now_ts": iso(now),
        "data_quality": "empty",
        "open_is_estimated": False,
        "t": [],
        "fut": [],
        "max_pain": [],
    }
