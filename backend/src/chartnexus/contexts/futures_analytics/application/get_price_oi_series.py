"""The intraday Price-vs-OI series behind Future Lab → Price vs OI.

Where the dashboard asks "what is the board doing right now", this asks "what
did one contract do today" — the front-month futures price and that contract's
own **futures open interest**, on a shared time axis.

**Futures open interest, not the option chain's.** The Options Lab serves a
similar-looking series whose OI line is the sum of every strike's open interest,
because when it was written the application captured no futures OI at all. It
does now: the board capture archives it per contract, and this reads that. The
two pages are therefore answering different questions, and the labels have to
keep saying so.

The three data tiers mirror the Options Lab's exactly, so the two pages never
disagree about whether a day has data:

    INTRADAY   (>=2 stored frames)  — the real session, as captured
    LIVE_PROXY (0 or 1)             — previous close vs now, off the live board
    EMPTY      (nothing to draw)    — no session and no board reading

``trade_date`` selects the archived day for **Historical**; ``None`` (the
default) reads today, which is **Live**.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from chartnexus.contexts.futures_analytics.application.ports import (
    BoardFrame,
    FuturesBoardHistoryReader,
    FuturesBoardSource,
)
from chartnexus.shared_kernel.types.identifiers import TenantId

#: Exchange-local time; the trading date a UTC instant belongs to is an IST fact.
_IST = timezone(timedelta(hours=5, minutes=30))

#: The bell, in exchange-local time. Both ends, because the chart is a picture
#: of a trading session: the broker keeps answering after the close with the
#: last traded price, so anything captured past the bell is a flat tail no
#: trading produced. Clipped here rather than only at capture, so a chart is a
#: session whatever happens to be sitting in the archive.
_SESSION_OPEN = (9, 15)
_SESSION_CLOSE = (15, 30)

#: Seconds per bucket, keyed by what the client asks for.
INTERVALS: dict[str, int] = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}
DEFAULT_INTERVAL = "1m"

#: Below this a day is not a session, it is a reading. Two points drawn as a
#: line would imply a shape the archive does not support.
_MIN_INTRADAY_FRAMES = 2


@dataclass(frozen=True, slots=True)
class PriceOiSeriesQuery:
    tenant_id: TenantId
    symbol: str
    interval: str = DEFAULT_INTERVAL
    #: The archived day to read. ``None`` means today — Live.
    trade_date: date | None = None


@dataclass(slots=True)
class GetFuturesPriceOiSeries:
    history: FuturesBoardHistoryReader
    board: FuturesBoardSource
    #: Injected so tests can pin "now" instead of racing the wall clock.
    now_utc: Any = None

    async def __call__(self, query: PriceOiSeriesQuery) -> dict[str, Any]:
        now = self.now_utc() if self.now_utc is not None else datetime.now(UTC)
        symbol = query.symbol.strip().upper()
        interval = query.interval if query.interval in INTERVALS else DEFAULT_INTERVAL
        session_date = query.trade_date or _session_date(now)

        frames = _within_session(await self.history.frames_for(symbol, session_date))
        if query.trade_date is None:
            # Only clip "future" frames on the live day — a past session is whole.
            frames = [frame for frame in frames if frame.captured_at <= now]

        if len(frames) >= _MIN_INTRADAY_FRAMES:
            bucketed = _downsample(frames, INTERVALS[interval])
            return _payload(symbol, bucketed, quality="intraday", interval=interval)

        # Nothing archived worth drawing. A past day has no live equivalent, so
        # it is simply empty; today can still say where the contract stands.
        if query.trade_date is not None:
            return _empty(symbol, now, interval)

        proxy = await self._proxy_frames(query.tenant_id, symbol, now, session_date)
        if not proxy:
            return _empty(symbol, now, interval)
        return _payload(symbol, proxy, quality="live_proxy", interval=interval)

    async def _proxy_frames(
        self,
        tenant_id: TenantId,
        symbol: str,
        now: datetime,
        session_date: date,
    ) -> list[BoardFrame]:
        """Previous close versus now, when the archive holds no session yet.

        Two honest points rather than a fabricated line: the opening end is the
        previous close the board already compares against, which is why the
        payload flags the open as estimated.
        """
        snapshot = await self.board.read(tenant_id)
        reading = next((row for row in snapshot.readings if row.symbol == symbol), None)
        if reading is None or reading.price <= 0:
            return []

        def frame(at: datetime, price: Decimal, open_interest: int | None) -> BoardFrame:
            return BoardFrame(
                symbol=symbol,
                session_date=session_date,
                captured_at=at,
                price=price,
                open_interest=open_interest,
                volume=reading.volume,
                expiry=reading.expiry,
                source=snapshot.source,
            )

        # Clamped to the bell for the same reason the archive is: opening the
        # page at 8pm must not stamp the day's last reading at 8pm and stretch
        # the axis four hours past the close.
        return [
            frame(_session_open_utc(now), reading.price_open, reading.open_interest_open),
            frame(_at_most_close(now), reading.price, reading.open_interest),
        ]


def _payload(
    symbol: str,
    frames: list[BoardFrame],
    *,
    quality: str,
    interval: str,
) -> dict[str, Any]:
    return {
        "instrument_id": symbol,
        "symbol": symbol,
        "expiry_date": frames[-1].expiry,
        "open_ts": _iso(frames[0].captured_at),
        "now_ts": _iso(frames[-1].captured_at),
        "data_quality": quality,
        "open_is_estimated": quality == "live_proxy",
        "interval": interval,
        "source": frames[-1].source,
        "t": [_iso(frame.captured_at) for frame in frames],
        "price": [float(frame.price) for frame in frames],
        # Nulls survive to the client on purpose. Open interest is swept on a
        # slower cadence than price, so a frame between sweeps genuinely has
        # none — and a gap in the line is the truth, where a zero would draw a
        # cliff that never happened.
        "oi": [frame.open_interest for frame in frames],
    }


def _empty(symbol: str, now: datetime, interval: str) -> dict[str, Any]:
    """A well-formed payload for a day with nothing to draw."""
    return {
        "instrument_id": symbol,
        "symbol": symbol,
        "expiry_date": None,
        "open_ts": _iso(_session_open_utc(now)),
        "now_ts": _iso(now),
        "data_quality": "empty",
        "open_is_estimated": False,
        "interval": interval,
        "source": "mock",
        "t": [],
        "price": [],
        "oi": [],
    }


def _downsample(frames: list[BoardFrame], bucket_seconds: int) -> list[BoardFrame]:
    """One frame per bucket — the last in each, and always the newest overall.

    Last rather than first or averaged: every other number on the page is a
    last-traded price, and a bucket that reported its mean would disagree with
    the board beside it.
    """
    if bucket_seconds <= 0:
        return frames

    chosen: dict[int, BoardFrame] = {}
    for frame in frames:
        key = int(frame.captured_at.timestamp()) // bucket_seconds
        chosen[key] = frame
    return [chosen[key] for key in sorted(chosen)]


def _within_session(frames: list[BoardFrame]) -> list[BoardFrame]:
    """Drop anything captured outside the trading day's own hours."""
    open_at, close_at = _SESSION_OPEN, _SESSION_CLOSE
    kept = []
    for frame in frames:
        local = frame.captured_at.astimezone(_IST)
        minutes = local.hour * 60 + local.minute
        if open_at[0] * 60 + open_at[1] <= minutes <= close_at[0] * 60 + close_at[1]:
            kept.append(frame)
    return kept


def _session_date(moment: datetime) -> date:
    return moment.astimezone(_IST).date()


def _at_most_close(moment: datetime) -> datetime:
    """``moment``, or the bell if the session has already ended."""
    local = moment.astimezone(_IST)
    hour, minute = _SESSION_CLOSE
    close = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return (close if local > close else local).astimezone(UTC)


def _session_open_utc(moment: datetime) -> datetime:
    """09:15 IST on the trading date this instant belongs to, in UTC."""
    local = moment.astimezone(_IST)
    hour, minute = _SESSION_OPEN
    return local.replace(hour=hour, minute=minute, second=0, microsecond=0).astimezone(UTC)


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")
