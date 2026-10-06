"""The adjusted short straddle replayed over stored sessions, for Straddle PnL.

Reads the option-chain archive, turns each capture into a frame the pure engine
in ``domain.straddle_pnl`` understands, and ships the resulting curve, trade log
and summary.

**All the arithmetic lives in the domain.** This module does three things the
engine deliberately cannot: it reads the archive, it decides which sessions and
which expiry are in scope, and it resolves the contract size. Keeping the split
that sharp is what lets the replay be pinned to a table of verified numbers
without a database anywhere near the test.

**No broker round trips.** Unlike the tool this clones, nothing here fetches a
candle series per strike: the archive already holds every strike's last traded
price at every capture, so the whole run is one read. The live chain is fetched
only to resolve which expiry is in force and what the lot size is — the same
thing Straddle Chart does next door.

**Stored sessions, not calendar days.** "5 Days" means five sessions the archive
actually holds. Counting back on the calendar hands a reader three and a half
over a long weekend with no way to tell that from a quiet market.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from chartnexus.contexts.options_analytics.application.ports import (
    ChainProvider,
    ChainSnapshot,
    ProviderChain,
    SnapshotReader,
)
from chartnexus.contexts.options_analytics.application.session import (
    IST,
    attach_utc,
    drop_future,
    for_expiry,
    iso,
    session_open_utc,
)
from chartnexus.contexts.options_analytics.domain.oi_math import DEFAULT_STRIKE_STEP, infer_step
from chartnexus.contexts.options_analytics.domain.straddle_pnl import (
    PnlFrame,
    Simulation,
    simulate,
)
from chartnexus.shared_kernel.domain.errors import ValidationError
from chartnexus.shared_kernel.types.identifiers import TenantId

#: Sessions a reader may ask for, matching the Straddle Chart next door. The
#: ceiling sits well inside the archive's retention window, so a full request
#: can always be answered.
DEFAULT_SESSIONS = 1
MAX_SESSIONS = 10

#: Contract size when the chain does not carry one. An index lot is never 1, and
#: a P&L computed on a quantity of 1 is off by two orders of magnitude without
#: looking obviously wrong — so refuse instead, and say so.
DEFAULT_LOTS = 1

_PLACES = 2


class GetStraddlePnl:
    """Assembles the Straddle PnL Simulator payload for one instrument."""

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
        expiry: str | None = None,
        sessions: int = DEFAULT_SESSIONS,
        adjustment_points: float | None = None,
        lot_size: int | None = None,
        lots: int = DEFAULT_LOTS,
        trade_date: datetime | None = None,
    ) -> dict[str, Any]:
        window = max(1, min(sessions, MAX_SESSIONS))
        now = self._now()
        end = trade_date or now
        chain = await self._provider.fetch(tenant_id, symbol, expiry=expiry)

        if window == 1:
            snaps = await self._snapshots.day_snapshots(tenant_id, symbol, trade_date_utc=end)
        else:
            snaps = await self._snapshots.recent_session_snapshots(
                tenant_id, symbol, end_utc=end, sessions=window
            )

        # Filtered by what the provider resolved to rather than what was asked
        # for: a broker handed an expiry it does not list answers with its
        # nearest, and keying off the request would replay one contract's
        # archived rows under another's header.
        snaps = for_expiry(snaps, chain.expiry)
        if trade_date is None:
            snaps = drop_future(snaps, now)

        ordered = sorted(snaps, key=lambda snap: snap.captured_at)
        frames = [frame for frame in (_frame(snap) for snap in ordered) if frame is not None]

        step = _step(frames, chain)
        size = _lot_size(lot_size, chain, symbol)
        threshold = adjustment_points if adjustment_points is not None else step

        if not frames:
            return _empty(
                symbol,
                chain,
                now,
                window=window,
                lot_size=size,
                lots=lots,
                adjustment_points=threshold,
                step=step,
            )

        result = simulate(
            frames,
            adjustment_points=threshold,
            lot_size=size,
            lots=lots,
            strike_step=step,
        )
        return _payload(
            symbol,
            chain,
            result,
            window=window,
            adjustment_points=threshold,
            step=step,
            lot_size=size,
            lots=lots,
        )


# -- assembly ----------------------------------------------------------------


def _frame(snap: ChainSnapshot) -> PnlFrame | None:
    """One capture as a replay frame, or ``None`` when it cannot anchor one.

    A capture with no rows, or none with a spot to read the at-the-money off,
    is dropped rather than guessed at: the strike the whole day's position
    hangs on is chosen from spot, and inventing one would quietly re-strike the
    straddle somewhere the market never was.
    """
    if not snap.rows or snap.spot is None:
        return None

    captured = attach_utc(snap.captured_at)
    return PnlFrame(
        # The IST trading date, which is what groups captures into sessions. An
        # IST day runs 03:45-10:00 UTC so it never straddles a UTC midnight,
        # but naming the timezone makes that a fact rather than a coincidence.
        session=captured.astimezone(IST).date().isoformat(),
        timestamp=iso(captured),
        spot=snap.spot,
        rows=snap.rows,
    )


def _step(frames: list[PnlFrame], chain: ProviderChain) -> float:
    """The strike ladder's spacing, read off the chain itself."""
    source = frames[-1].rows if frames else chain.rows
    strikes = sorted({row.strike for row in source})
    return infer_step(strikes) if strikes else DEFAULT_STRIKE_STEP


def _lot_size(requested: int | None, chain: ProviderChain, symbol: str) -> int:
    if requested is not None:
        if requested <= 0:
            raise ValidationError("Lot size must be positive.", field="lot_size")
        return requested
    if chain.lot_size:
        return chain.lot_size
    raise ValidationError(
        f"No lot size is known for {symbol}; pass one explicitly.", field="lot_size"
    )


def _payload(
    symbol: str,
    chain: ProviderChain,
    result: Simulation,
    *,
    window: int,
    adjustment_points: float,
    step: float,
    lot_size: int,
    lots: int,
) -> dict[str, Any]:
    last = result.series[-1]
    return {
        "instrument_id": symbol,
        "symbol": symbol,
        "expiry_date": chain.expiry,
        "lot_size": lot_size,
        "lots": lots,
        "quantity": result.quantity,
        "adjustment_points": adjustment_points,
        "strike_step": step,
        "requested_sessions": window,
        "covered_sessions": len(result.sessions),
        "open_ts": result.series[0].t,
        "now_ts": last.t,
        "spot": last.spot,
        "entry_strike": last.entry_strike,
        "data_quality": "intraday",
        "summary": {
            "total_pnl": result.total_pnl,
            "max_pnl": result.max_pnl,
            "min_pnl": result.min_pnl,
            "total_adjustments": result.total_adjustments,
        },
        "series": [
            {
                "t": point.t,
                "spot": point.spot,
                "atm_strike": point.atm_strike,
                "entry_strike": point.entry_strike,
                "ce_price": point.ce_price,
                "pe_price": point.pe_price,
                "straddle": point.straddle,
                "synthetic_future": point.synthetic_future,
                "pnl": point.pnl,
                "adjustments": point.adjustments,
            }
            for point in result.series
        ],
        "trades": [
            {
                "type": trade.type,
                "t": trade.t,
                "strike": trade.strike,
                "old_strike": trade.old_strike,
                "ce_price": trade.ce_price,
                "pe_price": trade.pe_price,
                "straddle": trade.straddle,
                "exit_ce": trade.exit_ce,
                "exit_pe": trade.exit_pe,
                "exit_straddle": trade.exit_straddle,
                "spot": trade.spot,
                "leg_pnl": trade.leg_pnl,
                "cumulative_pnl": trade.cumulative_pnl,
            }
            for trade in result.trades
        ],
    }


def _empty(
    symbol: str,
    chain: ProviderChain,
    now: datetime,
    *,
    window: int,
    lot_size: int,
    lots: int,
    adjustment_points: float,
    step: float,
) -> dict[str, Any]:
    """A day the archive never captured: an honest nothing, not a fabricated run.

    Deliberately not the live-chain fallback the series pages use. One frame
    makes a point on a chart, but a *simulation* of one capture is a position
    opened and closed at the same price — a flat zero line that looks like a
    strategy that broke even rather than a day with no data.
    """
    return {
        "instrument_id": symbol,
        "symbol": symbol,
        "expiry_date": chain.expiry,
        "lot_size": lot_size,
        "lots": lots,
        "quantity": lot_size * lots,
        "adjustment_points": adjustment_points,
        "strike_step": step,
        "requested_sessions": window,
        "covered_sessions": 0,
        "open_ts": iso(session_open_utc(now)),
        "now_ts": iso(now),
        "spot": round(chain.spot, _PLACES) if chain.spot is not None else None,
        "entry_strike": None,
        "data_quality": "empty",
        "summary": {
            "total_pnl": 0.0,
            "max_pnl": 0.0,
            "min_pnl": 0.0,
            "total_adjustments": 0,
        },
        "series": [],
        "trades": [],
    }
