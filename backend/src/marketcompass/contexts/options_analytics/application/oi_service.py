"""The Open Interest view service.

Builds the payload the OI tool renders from whatever data is available, choosing
the best tier and labelling which one it used:

    INTRADAY   (≥2 stored snapshots today)  — real open vs now
    LIVE_PROXY (1 stored snapshot)          — open ≈ now - oi_change
    LIVE       (no snapshots)               — one live chain, same proxy

Which tier a request lands on depends entirely on how much the ingest worker has
archived for the day so far. A machine that has never run it stays on LIVE.

Time rules that have bitten before, stated once:

* Stored datetimes are naive-UTC. Attach ``UTC`` on read; never guess a zone.
* IST is a FIXED ``+05:30`` offset — never ``ZoneInfo`` (DST tables it does not
  need, and a missing tzdata on the host would crash the tool).
* Session is 09:15-15:30 IST, Monday-Friday.
* ``iv`` is nullable end to end. It is never coerced to ``0``.

The service never raises on missing data — it degrades to an empty-but-shaped
payload so the page always renders.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import UTC, datetime
from itertools import pairwise
from typing import Any

from marketcompass.contexts.options_analytics.application.ports import (
    ChainProvider,
    ChainSnapshot,
    ProviderChain,
    SnapshotReader,
)
from marketcompass.contexts.options_analytics.application.session import (
    attach_utc as _attach_utc,
    drop_future,
    session_open_frame,
    session_open_utc,
)
from marketcompass.contexts.options_analytics.domain.oi_math import (
    ChainRow,
    atm_strike,
    max_pain,
    pcr_oi,
)
from marketcompass.shared_kernel.types.identifiers import TenantId

_DEFAULT_STEP = 50.0
_MIN_INTRADAY_SNAPSHOTS = 2
# Strikes either side of ATM kept in the intraday series. The widest filter the
# UI offers is ±20, so this is a superset — it exists to stop a day with a
# shifting ladder growing the payload without bound.
_SERIES_STRIKE_SPAN = 25
_BULLISH_AT = 60
_BEARISH_AT = 40


class GetOiView:
    """Assembles the Open Interest payload for one instrument."""

    def __init__(
        self,
        *,
        provider: ChainProvider,
        snapshots: SnapshotReader,
        now_utc: Any = None,
        strike_span: int = _SERIES_STRIKE_SPAN,
    ) -> None:
        self._provider = provider
        self._snapshots = snapshots
        # Injectable clock for tests; defaults to real UTC now.
        self._now = now_utc or (lambda: datetime.now(UTC))
        # The main lever on payload size — see `_series_axis`.
        self._strike_span = strike_span

    async def __call__(self, tenant_id: TenantId, symbol: str) -> dict[str, Any]:
        now = self._now()
        chain = await self._provider.fetch(tenant_id, symbol)

        # Snapshot tiers first; the null reader falls straight through to live.
        snaps = await self._snapshots.day_snapshots(tenant_id, symbol, trade_date_utc=now)
        snaps = drop_future(snaps, now)
        if len(snaps) >= _MIN_INTRADAY_SNAPSHOTS:
            return self._intraday(symbol, chain, snaps)
        if len(snaps) == 1:
            return self._live_proxy(symbol, chain, snaps[0].rows, now)
        return self._live_proxy(symbol, chain, chain.rows, now)

    # -- tiers --------------------------------------------------------------

    def _live_proxy(
        self, symbol: str, chain: ProviderChain, now_rows: tuple[ChainRow, ...], now: datetime
    ) -> dict[str, Any]:
        """LIVE / LIVE_PROXY: open is reconstructed per leg from ``oi_change``."""
        open_ts = session_open_utc(now)
        series = self._two_point_series(now_rows, open_ts, now)
        return self._build(
            symbol,
            chain,
            now_rows=now_rows,
            open_rows=None,  # None => derive open from oi_change
            open_ts=open_ts,
            now_ts=now,
            quality="live_proxy",
            series=series,
        )

    def _intraday(
        self, symbol: str, chain: ProviderChain, snaps: list[ChainSnapshot]
    ) -> dict[str, Any]:
        """INTRADAY: earliest in-session snapshot is the real open."""
        ordered = sorted(snaps, key=lambda s: s.captured_at)
        reconstructed = session_open_frame(ordered)
        if reconstructed is not None:
            ordered = [reconstructed, *ordered]
        open_snap = ordered[0]
        now_snap = ordered[-1]
        strike_axis = self._series_axis(ordered)
        series = self._series(ordered, strike_axis)
        return self._build(
            symbol,
            chain,
            now_rows=now_snap.rows,
            open_rows=open_snap.rows,
            open_ts=_attach_utc(open_snap.captured_at),
            now_ts=_attach_utc(now_snap.captured_at),
            quality="intraday",
            series=series,
            open_is_estimated=reconstructed is not None,
            # The archive's own spot, not the live chain's.
            #
            # These two are different observations of the market and can be far
            # apart — the newest snapshot may be minutes old, and on a machine
            # running the mock provider they are separate simulations entirely.
            # Taking spot from the live chain while the bars come from the
            # archive puts the spot line and the ATM-centred strike window on a
            # price that no bar on the chart was drawn from: the chart ends up
            # showing a monotonic decay off the side of the real OI peak.
            spot=now_snap.spot,
        )

    # -- payload assembly ---------------------------------------------------

    def _build(
        self,
        symbol: str,
        chain: ProviderChain,
        *,
        now_rows: tuple[ChainRow, ...],
        open_rows: tuple[ChainRow, ...] | None,
        open_ts: datetime,
        now_ts: datetime,
        quality: str,
        series: list[dict[str, Any]],
        spot: float | None = None,
        open_is_estimated: bool = False,
    ) -> dict[str, Any]:
        now_by = _index(now_rows)
        open_by = _index(open_rows) if open_rows is not None else {}
        strikes = sorted({row.strike for row in now_rows})

        if not strikes:
            return self._empty(symbol, chain, open_ts, now_ts)

        rows_out: list[dict[str, Any]] = []
        total_call_now = total_put_now = 0
        total_call_open = total_put_open = 0

        for strike in strikes:
            call_now = _oi(now_by.get((strike, "CE")))
            put_now = _oi(now_by.get((strike, "PE")))

            if open_rows is not None:
                call_open = _oi(open_by.get((strike, "CE")))
                put_open = _oi(open_by.get((strike, "PE")))
            else:
                # Proxy: open = now - change, per leg.
                call_open = call_now - _oi_change(now_by.get((strike, "CE")))
                put_open = put_now - _oi_change(now_by.get((strike, "PE")))

            total_call_now += call_now
            total_put_now += put_now
            total_call_open += call_open
            total_put_open += put_open

            rows_out.append(
                {
                    "strike": strike,
                    "call_oi_open": call_open,
                    "call_oi_now": call_now,
                    "call_oi_chg": call_now - call_open,
                    "call_oi_chg_pct": _pct(call_now - call_open, call_open),
                    "put_oi_open": put_open,
                    "put_oi_now": put_now,
                    "put_oi_chg": put_now - put_open,
                    "put_oi_chg_pct": _pct(put_now - put_open, put_open),
                }
            )

        step = _infer_step(strikes)
        # Caller's spot first (the tier that has one that matches `now_rows`),
        # then the live chain, then the middle of the ladder.
        resolved = spot if spot is not None else chain.spot
        spot = resolved if resolved is not None else strikes[len(strikes) // 2]
        atm = atm_strike(spot, strikes, step)
        mp = max_pain(now_rows, strikes)
        pcr_now = pcr_oi(now_rows)
        pcr_open = _pcr_from_totals(total_put_open, total_call_open)

        call_chg = total_call_now - total_call_open
        put_chg = total_put_now - total_put_open

        return {
            "instrument_id": symbol,
            "symbol": symbol,
            "spot": round(spot, 2),
            "atm_strike": atm,
            "max_pain": mp,
            "lot_size": chain.lot_size,
            "expiry_date": chain.expiry,
            "pcr_oi": pcr_now,
            "pcr_change": round(pcr_now - pcr_open, 2),
            "open_ts": _iso(open_ts),
            "now_ts": _iso(now_ts),
            "data_quality": quality,
            "open_is_estimated": open_is_estimated,
            "total_call_oi": total_call_now,
            "total_put_oi": total_put_now,
            "total_call_oi_chg": call_chg,
            "total_put_oi_chg": put_chg,
            "sentiment": _sentiment(pcr_now, call_chg, put_chg),
            "strikes": rows_out,
            "series": series,
        }

    def _empty(
        self, symbol: str, chain: ProviderChain, open_ts: datetime, now_ts: datetime
    ) -> dict[str, Any]:
        return {
            "instrument_id": symbol,
            "symbol": symbol,
            "spot": round(chain.spot, 2) if chain.spot is not None else 0.0,
            "atm_strike": 0.0,
            "max_pain": 0.0,
            "lot_size": chain.lot_size,
            "expiry_date": chain.expiry,
            "pcr_oi": 0.0,
            "pcr_change": 0.0,
            "open_ts": _iso(open_ts),
            "now_ts": _iso(now_ts),
            "data_quality": "empty",
            "open_is_estimated": False,
            "total_call_oi": 0,
            "total_put_oi": 0,
            "total_call_oi_chg": 0,
            "total_put_oi_chg": 0,
            "sentiment": _sentiment(0.0, 0, 0),
            "strikes": [],
            "series": [],
        }

    # -- series -------------------------------------------------------------

    def _two_point_series(
        self, now_rows: tuple[ChainRow, ...], open_ts: datetime, now_ts: datetime
    ) -> list[dict[str, Any]]:
        strike_axis = sorted({row.strike for row in now_rows})
        if not strike_axis:
            return []
        now_by = _index(now_rows)

        open_call = [
            _oi(now_by.get((s, "CE"))) - _oi_change(now_by.get((s, "CE"))) for s in strike_axis
        ]
        open_put = [
            _oi(now_by.get((s, "PE"))) - _oi_change(now_by.get((s, "PE"))) for s in strike_axis
        ]
        now_call = [_opt_oi(now_by.get((s, "CE"))) for s in strike_axis]
        now_put = [_opt_oi(now_by.get((s, "PE"))) for s in strike_axis]

        return [
            {"t": _iso(open_ts), "strikes": strike_axis, "call": open_call, "put": open_put},
            {"t": _iso(now_ts), "strikes": strike_axis, "call": now_call, "put": now_put},
        ]

    def _series_axis(self, ordered: list[ChainSnapshot]) -> list[float]:
        """One strike axis for every frame, spanning the whole session.

        Taking it from the newest snapshot alone loses any strike that was
        quoted at the open and had rolled off by the close — and because the
        client sums the frame arrays, that silently understates the baseline
        totals behind PCR change and the summary bars.

        Bounded to a window around ATM so a wild day cannot inflate the payload:
        the widest filter the UI offers is ±20 strikes, so ±25 is a superset.
        The newest snapshot's strikes are always kept regardless of that bound —
        they are what the per-strike table renders, and a table row with no
        matching frame column would draw a bar of zero.
        """
        union = sorted({row.strike for snap in ordered for row in snap.rows})
        if not union:
            return []

        newest = ordered[-1]
        current = {row.strike for row in newest.rows}
        anchor = newest.atm_strike
        if anchor is None:
            anchor = newest.spot if newest.spot is not None else union[len(union) // 2]

        reach = _infer_step(union) * self._strike_span
        return [s for s in union if s in current or abs(s - anchor) <= reach]

    def _series(
        self, ordered: list[ChainSnapshot], strike_axis: list[float]
    ) -> list[dict[str, Any]]:
        """Frames over a shared axis, carrying a leg forward once it stops quoting.

        Three cases per (strike, side): quoted now, quoted earlier but not now,
        never quoted. Only the last is genuinely absent — a leg that rolled off
        kept whatever OI it had, so emitting ``None`` there (which the client
        reads as zero) would invent a collapse that never happened.
        """
        last_known: dict[tuple[float, str], int] = {}
        frames: list[dict[str, Any]] = []

        for snap in ordered:
            by = _index(snap.rows)
            call: list[int | None] = []
            put: list[int | None] = []
            for strike in strike_axis:
                for side, column in (("CE", call), ("PE", put)):
                    row = by.get((strike, side))
                    if row is not None:
                        last_known[(strike, side)] = row.oi
                        column.append(row.oi)
                    else:
                        column.append(last_known.get((strike, side)))

            frames.append(
                {
                    "t": _iso(_attach_utc(snap.captured_at)),
                    "strikes": strike_axis,
                    "call": call,
                    "put": put,
                    # What the market looked like at *this* instant, so scrubbing
                    # moves the spot line and max-pain marker with the bars.
                    "spot": snap.spot,
                    "atm": snap.atm_strike,
                    "max_pain": snap.max_pain,
                }
            )

        return frames

    # -- session time -------------------------------------------------------


# -- module helpers ---------------------------------------------------------


def _index(rows: tuple[ChainRow, ...] | None) -> OrderedDict[tuple[float, str], ChainRow]:
    indexed: OrderedDict[tuple[float, str], ChainRow] = OrderedDict()
    for row in rows or ():
        indexed[(row.strike, row.option_type.upper())] = row
    return indexed


def _oi(row: ChainRow | None) -> int:
    return row.oi if row is not None else 0


def _opt_oi(row: ChainRow | None) -> int | None:
    """OI for a series frame — ``None`` marks a leg that is not listed."""
    return row.oi if row is not None else None


def _oi_change(row: ChainRow | None) -> int:
    return row.oi_change if row is not None else 0


def _pct(change: int, base: int) -> float:
    if base == 0:
        return 0.0
    return round(change / base * 100, 2)


def _pcr_from_totals(put_oi: int, call_oi: int) -> float:
    if call_oi <= 0:
        return 0.0
    return round(put_oi / call_oi, 4)


def _infer_step(strikes: list[float]) -> float:
    diffs = [b - a for a, b in pairwise(strikes) if b - a > 0]
    return min(diffs) if diffs else _DEFAULT_STEP


def _iso(dt: datetime) -> str:
    return _attach_utc(dt).astimezone(UTC).isoformat()


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _sentiment(pcr: float, call_chg: int, put_chg: int) -> dict[str, Any]:
    """A 0-100 bullish score blending PCR level and today's OI flow."""
    pcr_component = _clamp((pcr - 0.7) / 0.8, 0.0, 1.0)
    flow = (put_chg - call_chg) / (abs(call_chg) + abs(put_chg) + 1)
    bullish = round(100 * (0.5 * pcr_component + 0.5 * (flow + 1) / 2))
    bullish = int(_clamp(bullish, 0, 100))

    if bullish >= _BULLISH_AT:
        label = "Bullish"
        insight = "Put writers are defending lower levels — support is building."
    elif bullish <= _BEARISH_AT:
        label = "Bearish"
        insight = "Call writers are capping upside — resistance is building."
    else:
        label = "Neutral"
        insight = "Writing is balanced across calls and puts — no clear bias."

    analysis = (
        f"PCR {pcr:.2f} with call OI {'up' if call_chg >= 0 else 'down'} "
        f"{abs(call_chg):,} and put OI {'up' if put_chg >= 0 else 'down'} {abs(put_chg):,} "
        f"today points to a {label.lower()} tilt."
    )
    return {"label": label, "bullish_pct": bullish, "insight": insight, "analysis": analysis}
