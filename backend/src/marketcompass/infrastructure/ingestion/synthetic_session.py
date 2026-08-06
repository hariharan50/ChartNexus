"""Fabricates a whole trading session of option-chain snapshots.

The Open Interest tool's timeline can only be scrubbed when the archive holds
many snapshots for the day. Real ones only accumulate while the market is open
and a broker is connected, so on a developer machine at 07:41 with no FYERS
account the tool is permanently stuck on its two-point live estimate. This
module produces a session that looks like a real one, so the feature can be
built, demonstrated and tested at any hour.

It owns no simulation of its own. The prices and the book come from
``brokers/mock/session_model``, which is the same model the mock broker serves
live — so a seeded morning and an afternoon captured by the ingest worker are
one continuous session, and the Option Chain page agrees with this one. All that
happens here is the mapping into ``market_ingestion``'s write DTO and the header
metrics that go with it.

It lives in ``infrastructure`` rather than in a context because it needs
``market_data``'s instrument facts *and* ``market_ingestion``'s write DTO, and a
context may not import another context. ``ingestion/chain_source.py`` already
pairs those two here for the same reason.

It is deliberately not a ``market_ingestion`` use case: ``CaptureChainSnapshots``
is gated on market hours and captures *now*. Fabricating the past is a different
job that happens to write the same rows.
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.contexts.market_ingestion.application.ports import (
    ChainRowToWrite,
    SnapshotToWrite,
)
from marketcompass.contexts.market_ingestion.domain.chain_metrics import (
    MetricRow,
    atm_strike,
    max_pain_strike,
    pcr_oi,
    total_call_oi,
    total_put_oi,
)
from marketcompass.infrastructure.brokers.mock.session_model import (
    IST,
    SESSION_CLOSE,
    SESSION_OPEN,
    Leg,
    SessionFrame,
    lot_size,
    session_frames,
)

_SOURCE = "mock"
# Futures trade at a small cost-of-carry premium to spot.
_FUTURES_BASIS = 1.0007


def build_synthetic_session(
    *,
    symbol: str,
    session_date: date,
    interval_seconds: int = 180,
    start: time = SESSION_OPEN,
    end: time = SESSION_CLOSE,
    until: datetime | None = None,
) -> list[SnapshotToWrite]:
    """A session of snapshots for one symbol, deterministic per symbol-day.

    ``start``/``end`` are IST wall-clock; ``captured_at`` on each snapshot is
    UTC, matching what the real capture path stores.

    ``until`` cuts the session off at an instant, which is what seeding *today*
    must do: a real ingest worker cannot have captured 15:30 at 11:55, and an
    archive that claims otherwise makes the tool's "as of" handle read 3:30 pm
    all morning.
    """
    instrument = InstrumentSymbol.parse(symbol)
    if end <= start:
        return []

    frames = session_frames(
        instrument.value, session_date, interval_seconds=interval_seconds, until=until
    )
    return [_snapshot(instrument, session_date, frame) for frame in _within(frames, start, end)]


def _within(frames: list[SessionFrame], start: time, end: time) -> list[SessionFrame]:
    """Honour a caller's narrower window inside the model's fixed session."""
    if start == SESSION_OPEN and end == SESSION_CLOSE:
        return frames
    return [frame for frame in frames if start <= frame.captured_at.astimezone(IST).time() <= end]


def _snapshot(
    instrument: InstrumentSymbol, session_date: date, frame: SessionFrame
) -> SnapshotToWrite:
    rows = tuple(_row(leg) for leg in frame.legs)
    metric_rows = [
        MetricRow(strike=row.strike, option_type=row.option_type, oi=row.oi) for row in rows
    ]
    strikes = [Decimal(str(strike)) for strike in frame.strikes]
    spot = _money(frame.spot)

    return SnapshotToWrite(
        symbol=instrument.value,
        session_date=session_date,
        captured_at=frame.captured_at,
        spot=spot,
        source=_SOURCE,
        rows=rows,
        expiry=None,
        future_price=_money(frame.spot * _FUTURES_BASIS),
        lot_size=lot_size(instrument),
        atm_strike=atm_strike(spot, strikes),
        total_call_oi=total_call_oi(metric_rows),
        total_put_oi=total_put_oi(metric_rows),
        pcr_oi=pcr_oi(metric_rows),
        max_pain_strike=max_pain_strike(metric_rows, strikes),
    )


def _row(leg: Leg) -> ChainRowToWrite:
    return ChainRowToWrite(
        strike=Decimal(str(leg.strike)),
        option_type=leg.option_type,
        oi=leg.oi,
        # The day change a broker reports, which the live tier inverts to
        # reconstruct an open. Anything else corrupts the single-snapshot tier.
        oi_change=leg.oi_change,
        volume=leg.volume,
        ltp=_money(leg.ltp),
        # Never None: part of why the archive exists is to keep IV available.
        iv=Decimal(str(leg.iv)),
        delta=None,
    )


def _money(value: float) -> Decimal:
    return Decimal(str(round(value, 2)))
