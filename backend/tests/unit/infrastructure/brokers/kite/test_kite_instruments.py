"""Zerodha's instrument dump: what is kept, how it is validated, how it is named."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from chartnexus.infrastructure.brokers.kite.instruments import (
    MIN_ROWS,
    InstrumentDumpError,
    KiteInstrument,
    derivative_exchange,
    parse_dump,
    spot_key,
    validate,
)

pytestmark = pytest.mark.unit

DUMP = (Path(__file__).resolve().parents[4] / "fixtures" / "kite" / "instruments.csv").read_text(
    encoding="utf-8"
)


def _parsed() -> dict[str, KiteInstrument]:
    rows = parse_dump(DUMP, equities=["RELIANCE", "HDFCBANK"])
    return {row.tradingsymbol: row for row in rows}


class TestParse:
    def test_index_spots_we_name_are_kept(self) -> None:
        rows = _parsed()
        for name in ("NIFTY 50", "NIFTY BANK", "SENSEX", "INDIA VIX"):
            assert name in rows

    def test_indices_we_do_not_name_are_dropped(self) -> None:
        assert "NIFTY AUTO" not in _parsed()

    def test_unless_asked_for(self) -> None:
        rows = parse_dump(DUMP, index_names=["NIFTY AUTO"])
        assert any(row.tradingsymbol == "NIFTY AUTO" for row in rows)

    def test_only_catalog_equities_are_kept(self) -> None:
        rows = _parsed()
        assert "RELIANCE" in rows
        assert "HDFCBANK" in rows
        assert "TCS" not in rows

    def test_all_nfo_and_bfo_derivatives_are_kept(self) -> None:
        rows = _parsed()
        for symbol in (
            "NIFTY26AUGFUT",
            "NIFTY26SEPFUT",
            "NIFTY2680624500CE",
            "NIFTY2680624500PE",
            "SENSEX2680781000CE",
        ):
            assert symbol in rows

    def test_currency_and_commodity_are_dropped(self) -> None:
        rows = _parsed()
        assert "USDINR26AUGFUT" not in rows
        assert "GOLDM26AUGFUT" not in rows

    def test_an_option_row_is_fully_typed(self) -> None:
        row = _parsed()["NIFTY2680624500CE"]
        assert row.instrument_token == 10184450
        assert row.exchange == "NFO"
        assert row.name == "NIFTY"
        assert row.expiry == date(2026, 8, 6)
        assert row.strike == Decimal("24500")
        assert row.lot_size == 75
        assert row.is_option
        assert row.quote_key == "NFO:NIFTY2680624500CE"

    def test_a_spot_has_no_strike_or_expiry(self) -> None:
        row = _parsed()["NIFTY 50"]
        assert row.strike is None
        assert row.expiry is None

    def test_a_row_with_a_bad_token_is_skipped(self) -> None:
        broken = DUMP.replace("13238786,", "not-a-number,", 1)
        rows = parse_dump(broken)
        assert "NIFTY26AUGFUT" not in {row.tradingsymbol for row in rows}


class TestValidate:
    def _many(self) -> list[KiteInstrument]:
        rows = parse_dump(DUMP)
        future = next(row for row in rows if row.exchange == "NFO")
        filler = [replace(future, instrument_token=i) for i in range(MIN_ROWS)]
        return rows + filler

    def test_a_full_dump_passes(self) -> None:
        validate(self._many())

    def test_a_truncated_dump_is_refused(self) -> None:
        with pytest.raises(InstrumentDumpError, match="usable rows"):
            validate(parse_dump(DUMP))

    def test_a_dump_missing_bfo_is_refused(self) -> None:
        rows = [row for row in self._many() if row.exchange != "BFO"]
        with pytest.raises(InstrumentDumpError, match="BFO"):
            validate(rows)

    def test_a_dump_without_index_spots_is_refused(self) -> None:
        rows = [row for row in self._many() if row.segment != "INDICES"]
        with pytest.raises(InstrumentDumpError, match="index"):
            validate(rows)


class TestNaming:
    @pytest.mark.parametrize(
        ("symbol", "expected"),
        [
            ("NIFTY", ("NSE", "NIFTY 50")),
            ("BANKNIFTY", ("NSE", "NIFTY BANK")),
            ("FINNIFTY", ("NSE", "NIFTY FIN SERVICE")),
            ("MIDCPNIFTY", ("NSE", "NIFTY MID SELECT")),
            ("SENSEX", ("BSE", "SENSEX")),
            ("INDIAVIX", ("NSE", "INDIA VIX")),
            ("reliance", ("NSE", "RELIANCE")),
        ],
    )
    def test_spot_keys(self, symbol: str, expected: tuple[str, str]) -> None:
        assert spot_key(symbol, "NSE") == expected

    def test_a_bse_listed_equity_keeps_its_exchange(self) -> None:
        assert spot_key("XYZ", "BSE") == ("BSE", "XYZ")

    def test_derivative_exchange(self) -> None:
        assert derivative_exchange("BSE") == "BFO"
        assert derivative_exchange("NSE") == "NFO"
