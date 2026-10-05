"""The intraday Price-vs-OI series behind Future Lab → Price vs OI.

Where ``GetOiSeries`` transposes the archive into one line *per contract*, this
collapses it into the two aggregate lines that page reads together: the tradable
**future price** and the **total open interest of the whole chain**, on a shared
time axis. Same archive, same session tiers, a far smaller payload.

The OI line is deliberately the *whole chain's* OI (every captured strike, both
sides), not a windowed slice — "price up while OI builds" is a market-wide read,
and summing only the strikes near the money would understate it. Futures OI would
be the truer quantity, but the app captures none; total chain OI is the faithful,
available proxy.

The three data tiers mirror ``GetOiSeries`` exactly, so the two pages never
disagree about whether a day has data:

    INTRADAY   (>=2 stored captures)  — real open vs the whole session
    LIVE_PROXY (0 or 1)               — open-vs-now off the live chain
    EMPTY      (before the bell)      — no session to draw two ends of

``trade_date`` selects the archived day for **Historical** mode; ``None`` (the
default) reads today, which is **Live**.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from chartnexus.contexts.options_analytics.application.oi_series_service import (
    _MIN_INTRADAY_SNAPSHOTS,
    DEFAULT_INTERVAL,
    INTERVALS,
    _downsample,
    _effective_interval,
)
from chartnexus.contexts.options_analytics.application.ports import (
    ChainProvider,
    ChainSnapshot,
    ProviderChain,
    SnapshotReader,
)
from chartnexus.contexts.options_analytics.application.session import (
    drop_future,
    for_expiry,
    future_of,
    iso as _iso,
    live_proxy_frames,
    session_open_frame,
    session_open_utc,
)
from chartnexus.shared_kernel.types.identifiers import TenantId


class GetPriceOiSeries:
    """Assembles the {time, price, total-OI} series for one instrument."""

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
        self,
        tenant_id: TenantId,
        symbol: str,
        *,
        interval: str = DEFAULT_INTERVAL,
        expiry: str | None = None,
        trade_date: datetime | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        # The day whose archive we read. Live is today; Historical is the picked
        # date, replayed as a whole session from its stored captures.
        as_of = trade_date or now
        bucket = INTERVALS.get(interval, INTERVALS[DEFAULT_INTERVAL])

        chain = await self._provider.fetch(tenant_id, symbol, expiry=expiry)
        snaps = await self._snapshots.day_snapshots(tenant_id, symbol, trade_date_utc=as_of)
        # Filtered by what the chain actually resolved to, not by what was
        # asked for. A provider handed an expiry it does not list answers
        # with its nearest instead, and keying off the request would then
        # draw one contract's archived rows under another's header. Anything
        # the archive does not hold drops to live-proxy, which is honest.
        snaps = for_expiry(snaps, chain.expiry)
        # Only clip "future" frames on the live day — a past session is whole.
        if trade_date is None:
            snaps = drop_future(snaps, now)

        if len(snaps) < _MIN_INTRADAY_SNAPSHOTS:
            return self._live_proxy(symbol, chain, snaps, now, interval=interval)

        ordered = sorted(snaps, key=lambda snap: snap.captured_at)
        reconstructed = session_open_frame(ordered)
        if reconstructed is not None:
            ordered = [reconstructed, *ordered]

        frames = _downsample(ordered, bucket)
        return self._payload(
            symbol,
            chain,
            frames,
            quality="intraday",
            open_is_estimated=reconstructed is not None,
            interval=_effective_interval(bucket, snaps),
        )

    def _live_proxy(
        self,
        symbol: str,
        chain: ProviderChain,
        snaps: list[ChainSnapshot],
        now: datetime,
        *,
        interval: str,
    ) -> dict[str, Any]:
        """Open-vs-now off the live chain when nothing is archived for the day."""
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
            return self._empty(symbol, chain, now, interval)

        return self._payload(
            symbol,
            chain,
            frames,
            quality="live_proxy",
            open_is_estimated=True,
            interval=interval,
        )

    def _payload(
        self,
        symbol: str,
        chain: ProviderChain,
        frames: list[ChainSnapshot],
        *,
        quality: str,
        open_is_estimated: bool,
        interval: str,
    ) -> dict[str, Any]:
        anchor = frames[-1]
        return {
            "instrument_id": symbol,
            "symbol": symbol,
            "expiry_date": chain.expiry,
            "lot_size": chain.lot_size,
            "open_ts": _iso(frames[0].captured_at),
            "now_ts": _iso(anchor.captured_at),
            "data_quality": quality,
            "open_is_estimated": open_is_estimated,
            "interval": interval,
            "t": [_iso(frame.captured_at) for frame in frames],
            "price": [future_of(frame) for frame in frames],
            "oi": [_total_oi(frame) for frame in frames],
        }

    def _empty(
        self,
        symbol: str,
        chain: ProviderChain,
        now: datetime,
        interval: str,
    ) -> dict[str, Any]:
        """A well-formed payload for a day with nothing archived yet."""
        return {
            "instrument_id": symbol,
            "symbol": symbol,
            "expiry_date": chain.expiry,
            "lot_size": chain.lot_size,
            "open_ts": _iso(session_open_utc(now)),
            "now_ts": _iso(now),
            "data_quality": "empty",
            "open_is_estimated": False,
            "interval": interval,
            "t": [],
            "price": [],
            "oi": [],
        }


def _total_oi(frame: ChainSnapshot) -> int:
    """The whole chain's open interest at one instant — every strike, both sides."""
    return sum(row.oi for row in frame.rows)
