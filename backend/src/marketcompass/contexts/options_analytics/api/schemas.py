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
