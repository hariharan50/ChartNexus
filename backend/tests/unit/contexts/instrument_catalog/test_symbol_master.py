"""Parsing the exchange symbol masters into catalog rows.

The fixtures below are real rows, trimmed to the columns that matter. They
cover the shapes that actually differ between instruments rather than a single
happy path: an NSE index, an NSE stock, a BSE index, a fractional strike step,
a ticker containing ``&``, and the two exchanges' incompatible ways of marking
a futures row.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from marketcompass.contexts.instrument_catalog.domain.instrument import InstrumentKind
from marketcompass.infrastructure.catalog.fyers_symbol_master import parse_universe

pytestmark = pytest.mark.unit

# Column layout of the headerless masters, wide enough to index column 16.
_WIDTH = 21

# Expiry epochs: the nearest one is what the strike step is read from.
_NEAR = "1790676600"
_FAR = "1793095800"


def _blank() -> list[str]:
    return [""] * _WIDTH


def _future(
    *,
    underlying: str,
    kind: str,
    lot: int,
    tick: str = "0.05",
    marker: str = "XX",
) -> list[str]:
    row = _blank()
    row[1] = f"{underlying} FUT"
    row[2] = kind
    row[3] = str(lot)
    row[4] = tick
    row[8] = _NEAR
    row[13] = underlying
    row[14] = "999"
    row[15] = "-1.0"
    row[16] = marker
    return row


def _option(*, underlying: str, strike: str, expiry: str = _NEAR) -> list[str]:
    row = _blank()
    row[2] = "13"
    row[3] = "1"
    row[4] = "0.05"
    row[8] = expiry
    row[13] = underlying
    row[15] = strike
    row[16] = "CE"
    return row


def _cash(*, underlying: str, name: str, ticker: str, isin: str = "") -> list[str]:
    row = _blank()
    row[1] = name
    row[4] = "0.05"
    row[5] = isin
    row[9] = ticker
    row[13] = underlying
    row[15] = "-1.0"
    row[16] = "XX"
    return row


def _ladder(underlying: str, strikes: list[str], expiry: str = _NEAR) -> list[list[str]]:
    return [_option(underlying=underlying, strike=s, expiry=expiry) for s in strikes]


def test_parses_an_index_and_a_stock_from_the_nse_masters() -> None:
    fo = [
        _future(underlying="NIFTY", kind="11", lot=65, tick="0.1"),
        *_ladder("NIFTY", ["24000", "24050", "24100"]),
        _future(underlying="RELIANCE", kind="13", lot=500, tick="0.1"),
        *_ladder("RELIANCE", ["1200", "1210", "1220"]),
    ]
    cm = [
        _cash(underlying="NIFTY", name="NIFTY50-INDEX", ticker="NSE:NIFTY50-INDEX"),
        _cash(
            underlying="RELIANCE",
            name="RELIANCE INDUSTRIES LTD",
            ticker="NSE:RELIANCE-EQ",
            isin="INE002A01018",
        ),
    ]

    universe = {i.symbol: i for i in parse_universe(fo, cm, exchange="NSE")}
    assert set(universe) == {"NIFTY", "RELIANCE"}

    nifty = universe["NIFTY"]
    assert nifty.kind is InstrumentKind.INDEX
    # The suffix is plumbing, not a name a user should ever read.
    assert nifty.name == "NIFTY50"
    # Reproduces the mapping the old hardcoded ``_TO_FYERS`` dict held.
    assert nifty.spot_symbol == "NSE:NIFTY50-INDEX"
    assert nifty.lot_size == 65
    assert nifty.strike_step == Decimal("50")
    assert nifty.isin is None

    reliance = universe["RELIANCE"]
    assert reliance.kind is InstrumentKind.STOCK
    assert reliance.name == "RELIANCE INDUSTRIES LTD"
    # A stock is quoted ``-EQ``, not ``-INDEX``: the shape differs by kind,
    # which is why the mapping cannot be one flat table.
    assert reliance.spot_symbol == "NSE:RELIANCE-EQ"
    assert reliance.isin == "INE002A01018"
    assert reliance.strike_step == Decimal("10")


def test_bse_marks_futures_with_a_blank_option_type() -> None:
    """NSE writes ``XX``; BSE leaves the column empty. Both are futures."""
    fo = [
        _future(underlying="SENSEX", kind="11", lot=20, marker=""),
        *_ladder("SENSEX", ["80000", "80100"]),
    ]
    cm = [_cash(underlying="SENSEX", name="SENSEX-INDEX", ticker="BSE:SENSEX-INDEX")]

    universe = parse_universe(fo, cm, exchange="BSE")

    assert len(universe) == 1
    assert universe[0].symbol == "SENSEX"
    assert universe[0].exchange == "BSE"
    assert universe[0].spot_symbol == "BSE:SENSEX-INDEX"


def test_strike_step_takes_the_most_common_gap_not_the_smallest() -> None:
    """A corporate action leaves stray adjusted strikes behind.

    HINDPETRO really does list a 0.75 gap against a true step of 10. Seeding a
    synthetic chain from that outlier would produce hundreds of bogus strikes,
    so the modal gap wins.
    """
    fo = [
        _future(underlying="HINDPETRO", kind="13", lot=2025),
        *_ladder("HINDPETRO", ["400", "410", "420", "430", "430.75", "440"]),
    ]
    cm = [_cash(underlying="HINDPETRO", name="HPCL", ticker="NSE:HINDPETRO-EQ")]

    assert parse_universe(fo, cm, exchange="NSE")[0].strike_step == Decimal("10")


def test_strike_step_may_be_fractional() -> None:
    """Nineteen names trade on a 2.5 step, so this cannot be an int."""
    fo = [
        _future(underlying="ASHOKLEY", kind="13", lot=5000, tick="0.01"),
        *_ladder("ASHOKLEY", ["100", "102.5", "105", "107.5"]),
    ]
    cm = [_cash(underlying="ASHOKLEY", name="ASHOK LEYLAND LTD", ticker="NSE:ASHOKLEY-EQ")]

    assert parse_universe(fo, cm, exchange="NSE")[0].strike_step == Decimal("2.5")


def test_strike_step_is_read_from_the_nearest_expiry() -> None:
    fo = [
        _future(underlying="TCS", kind="13", lot=225),
        *_ladder("TCS", ["3000", "3020", "3040"], expiry=_NEAR),
        # A far month lists a coarser ladder; it must not be what we store.
        *_ladder("TCS", ["3000", "3100", "3200"], expiry=_FAR),
    ]
    cm = [_cash(underlying="TCS", name="TATA CONSULTANCY", ticker="NSE:TCS-EQ")]

    assert parse_universe(fo, cm, exchange="NSE")[0].strike_step == Decimal("20")


def test_ampersand_tickers_survive_parsing() -> None:
    """``M&M`` and ``GVT&D`` are real tickers. They must round-trip intact."""
    fo = [
        _future(underlying="M&M", kind="13", lot=200, tick="0.1"),
        *_ladder("M&M", ["3000", "3050"]),
    ]
    cm = [
        _cash(
            underlying="M&M",
            name="MAHINDRA & MAHINDRA LTD",
            ticker="NSE:M&M-EQ",
            isin="INE101A01026",
        )
    ]

    instrument = parse_universe(fo, cm, exchange="NSE")[0]
    assert instrument.symbol == "M&M"
    assert instrument.spot_symbol == "NSE:M&M-EQ"
    assert instrument.futures_root == "M&M"


def test_an_underlying_with_no_cash_row_is_skipped() -> None:
    """Without the cash row there is no spot symbol, and an instrument the app
    cannot price is worse than one it does not list."""
    fo = [_future(underlying="GHOST", kind="13", lot=100)]

    assert parse_universe(fo, [], exchange="NSE") == []


def test_rows_with_an_unknown_instrument_type_are_skipped() -> None:
    fo = [_future(underlying="WEIRD", kind="99", lot=100)]
    cm = [_cash(underlying="WEIRD", name="WEIRD", ticker="NSE:WEIRD-EQ")]

    assert parse_universe(fo, cm, exchange="NSE") == []


@pytest.mark.parametrize("lot", [0, -1])
def test_a_non_positive_lot_size_is_rejected(lot: int) -> None:
    fo = [_future(underlying="BADLOT", kind="13", lot=lot)]
    cm = [_cash(underlying="BADLOT", name="BAD", ticker="NSE:BADLOT-EQ")]

    assert parse_universe(fo, cm, exchange="NSE") == []


def test_the_front_month_expiry_is_read_from_the_master() -> None:
    """Not guessed from the calendar.

    NSE moved monthly expiry off the last Thursday — September 2026 settles on
    Tuesday the 29th, not Thursday the 24th — and the two disagree for five
    trading days, during which a calendar guess builds October symbols for
    contracts still trading in September.
    """
    fo = [
        _future(underlying="RELIANCE", kind="13", lot=500),
        *_ladder("RELIANCE", ["1200", "1210"]),
    ]
    cm = [_cash(underlying="RELIANCE", name="RELIANCE", ticker="NSE:RELIANCE-EQ")]

    instrument = parse_universe(fo, cm, exchange="NSE")[0]

    # _NEAR is 1790676600 -> 2026-09-29 in exchange-local time.
    assert instrument.front_expiry == date(2026, 9, 29)


def test_the_nearest_contract_decides_the_front_month() -> None:
    far = _future(underlying="TCS", kind="13", lot=225)
    far[8] = _FAR
    near = _future(underlying="TCS", kind="13", lot=225)
    cm = [_cash(underlying="TCS", name="TCS", ticker="NSE:TCS-EQ")]

    # Far month listed first, so order must not decide it.
    instrument = parse_universe([far, near], cm, exchange="NSE")[0]

    assert instrument.front_expiry == date(2026, 9, 29)
