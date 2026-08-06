"""Wire contract for the Open Interest view.

The service produces a plain dict (cheap to cache as JSON); these models give the
endpoint a typed, documented response and validate the shape on the way out.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StrikeOiResponse(_Schema):
    strike: float
    call_oi_open: int
    call_oi_now: int
    call_oi_chg: int
    call_oi_chg_pct: float
    put_oi_open: int
    put_oi_now: int
    put_oi_chg: int
    put_oi_chg_pct: float


class SeriesFrameResponse(_Schema):
    t: str
    strikes: list[float]
    call: list[int | None]
    put: list[int | None]
    # Optional because the live tier synthesises its two frames from one chain
    # and has no stored header to read them from; the client falls back to the
    # payload-level values there.
    spot: float | None = None
    atm: float | None = None
    max_pain: float | None = None


class SentimentResponse(_Schema):
    label: str
    bullish_pct: int
    insight: str
    analysis: str


class OiViewResponse(_Schema):
    instrument_id: str
    symbol: str
    spot: float
    atm_strike: float
    max_pain: float
    lot_size: int | None
    expiry_date: str | None
    pcr_oi: float
    pcr_change: float
    open_ts: str
    now_ts: str
    data_quality: str
    # True when the 09:15 baseline was derived from the broker's day-change
    # field rather than read from a stored capture — which is what happens
    # whenever the ingest worker started after the bell.
    open_is_estimated: bool = False
    total_call_oi: int
    total_put_oi: int
    total_call_oi_chg: int
    total_put_oi_chg: int
    sentiment: SentimentResponse
    strikes: list[StrikeOiResponse]
    series: list[SeriesFrameResponse]

    @classmethod
    def of(cls, payload: dict[str, Any]) -> OiViewResponse:
        return cls.model_validate(payload)


class ContractSeriesResponse(_Schema):
    """One contract's day, aligned to the payload's shared time axis.

    ``oi_change`` is absent on purpose: index 0 is the session open, so the
    client derives ``oi[i] - oi[0]``. Sending it as well would be a third array
    per contract carrying no new information — and a second source of truth for
    a figure the Open Interest page derives the same way.
    """

    id: str
    strike: float
    option_type: str
    oi: list[int]
    volume: list[int]


class OiSeriesResponse(_Schema):
    """Per-contract intraday series behind Multi OI & Volume."""

    instrument_id: str
    symbol: str
    expiry_date: str | None
    atm_strike: float
    lot_size: int | None
    open_ts: str
    now_ts: str
    data_quality: str
    open_is_estimated: bool = False
    # The bucket actually used, which can be coarser than the one requested:
    # no interval can produce resolution finer than the capture cadence.
    interval: str
    window: int
    t: list[str]
    # Aligned to `t`. The tradable current-month future, not index spot — and
    # `None` on the reconstructed 09:15 frame, where nothing was recorded.
    fut: list[float | None]
    contracts: list[ContractSeriesResponse]
    default_ids: list[str]
    default_vol_ids: list[str]

    @classmethod
    def of(cls, payload: dict[str, Any]) -> OiSeriesResponse:
        return cls.model_validate(payload)
