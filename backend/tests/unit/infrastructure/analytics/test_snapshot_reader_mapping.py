"""Pure mapping in the SQLAlchemy snapshot reader.

The DB round-trip is an integration concern; here we pin the record → domain
translation and the IST session-date derivation, which are the parts that have
bitten before (a nullable IV coerced to 0.0, or a UTC/IST date-boundary slip).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from marketcompass.infrastructure.analytics.oi_chain_source import (
    _ist_session_date,
    _to_chain_snapshot,
)


def _row(**kwargs: object) -> SimpleNamespace:
    base = {
        "strike": Decimal("100"),
        "option_type": "CE",
        "oi": 200,
        "oi_change": 10,
        "volume": 5,
        "ltp": Decimal("12.50"),
        "iv": Decimal("13.200"),
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_ist_session_date_crosses_no_boundary_within_session() -> None:
    # 03:45 UTC == 09:15 IST — session open, same calendar date.
    assert _ist_session_date(datetime(2026, 8, 4, 3, 45, tzinfo=UTC)).isoformat() == "2026-08-04"


def test_ist_session_date_handles_naive_as_utc() -> None:
    naive = datetime(2026, 8, 4, 4, 0)  # noqa: DTZ001 — the naive path is the assertion
    assert _ist_session_date(naive).isoformat() == "2026-08-04"


def test_null_iv_is_preserved_not_zeroed() -> None:
    record = SimpleNamespace(
        captured_at=datetime(2026, 8, 4, 4, 0, tzinfo=UTC),
        rows=[_row(iv=None), _row(option_type="PE", iv=Decimal("14.0"))],
    )

    snapshot = _to_chain_snapshot(record)

    assert snapshot.rows[0].iv is None  # never coerced to 0.0
    assert snapshot.rows[1].iv == 14.0


def test_rows_map_to_float_chain_rows() -> None:
    record = SimpleNamespace(
        captured_at=datetime(2026, 8, 4, 4, 0, tzinfo=UTC),
        rows=[_row()],
    )

    snapshot = _to_chain_snapshot(record)

    row = snapshot.rows[0]
    assert (row.strike, row.option_type, row.oi, row.oi_change, row.volume) == (
        100.0,
        "CE",
        200,
        10,
        5,
    )
    assert row.ltp == 12.5
    assert snapshot.captured_at == datetime(2026, 8, 4, 4, 0, tzinfo=UTC)
