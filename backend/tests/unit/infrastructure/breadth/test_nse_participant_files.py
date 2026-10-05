"""The NSE file parsers, against real published files.

The fixtures are the exchange's own output for 22 September 2026, byte for
byte, because the failure this module exists to prevent is a *plausible*
misreading — a column read one place left, an options net summed instead of
netted — which no synthetic fixture would catch and no reader of the page
could. The expected numbers below were checked against the figures the
exchange shows for that session.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from chartnexus.contexts.market_breadth.domain.flows import Participant, Segment
from chartnexus.contexts.market_breadth.domain.open_interest import (
    OI_SEGMENTS,
    PARTICIPANT_ORDER,
    FutureLegs,
    OptionLegs,
)
from chartnexus.infrastructure.breadth.nse.participant_files import (
    NotPublishedError,
    cash_activity_url,
    fii_derivative_stats_url,
    market_activity_url,
    parse_cash_activity,
    parse_fii_derivative_stats,
    parse_index_close,
    parse_participant_oi,
    participant_oi_url,
)

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "nse"
SESSION = date(2026, 9, 22)


@pytest.fixture(scope="module")
def oi_payload() -> bytes:
    return (FIXTURES / "fao_participant_oi_22092026.csv").read_bytes()


@pytest.fixture(scope="module")
def stats_payload() -> bytes:
    return (FIXTURES / "fii_stats_22-Sep-2026.xls").read_bytes()


@pytest.fixture(scope="module")
def cash_payload() -> bytes:
    return (FIXTURES / "fiidii_trade_react.json").read_bytes()


@pytest.fixture(scope="module")
def activity_payload() -> bytes:
    return (FIXTURES / "MA220926.csv").read_bytes()


# -- urls ----------------------------------------------------------------------


def test_urls_spell_each_date_the_way_its_own_publication_does() -> None:
    """Three files, three date formats, and none of them is negotiable."""
    assert participant_oi_url(SESSION).endswith("fao_participant_oi_22092026.csv")
    assert fii_derivative_stats_url(SESSION).endswith("fii_stats_22-Sep-2026.xls")
    assert market_activity_url(SESSION).endswith("MA220926.csv")
    assert cash_activity_url().endswith("/api/fiidiiTradeReact")


def test_the_month_name_is_not_taken_from_the_locale() -> None:
    """A server running under a non-English locale must ask for the same file."""
    assert fii_derivative_stats_url(date(2026, 1, 5)).endswith("05-Jan-2026.xls")
    assert fii_derivative_stats_url(date(2026, 12, 31)).endswith("31-Dec-2026.xls")


# -- participant-wise open interest --------------------------------------------


def test_every_participant_appears_in_every_segment(oi_payload: bytes) -> None:
    board = parse_participant_oi(oi_payload, session=SESSION)
    assert len(board) == len(PARTICIPANT_ORDER) * len(OI_SEGMENTS)


def test_futures_nets_match_the_published_file(oi_payload: bytes) -> None:
    board = parse_participant_oi(oi_payload, session=SESSION)
    # Long 40,257 against short 343,165 on the day — the FIIs were carrying a
    # large net short in index futures.
    assert board[(Participant.FII, Segment.INDEX_FUTURES)] == FutureLegs(long=40_257, short=343_165)
    assert board[(Participant.DII, Segment.INDEX_FUTURES)].net == 13_181


def test_an_options_net_is_the_bullish_side_minus_the_bearish_one(oi_payload: bytes) -> None:
    """Not a sum of legs: a short put is a bullish position, and counts as one."""
    legs = board_row(oi_payload, Participant.FII, Segment.INDEX_OPTIONS)
    assert isinstance(legs, OptionLegs)
    assert legs.net == (legs.call_long + legs.put_short) - (legs.call_short + legs.put_long)
    assert legs.net == -898_600


def test_the_four_nets_cancel_in_every_segment(oi_payload: bytes) -> None:
    """Every long is somebody's short.

    Allowed a contract or two of slack: the exchange's own participant rows
    occasionally disagree with its own total by that much, and the page has
    the same tolerance rather than standing a warning under a good board.
    """
    board = parse_participant_oi(oi_payload, session=SESSION)
    for segment in OI_SEGMENTS:
        residual = sum(board[(participant, segment)].net for participant in PARTICIPANT_ORDER)
        assert abs(residual) <= 10, segment


def test_a_file_dated_another_session_is_refused(oi_payload: bytes) -> None:
    """The archive has served a stale file under a fresh name before."""
    with pytest.raises(NotPublishedError):
        parse_participant_oi(oi_payload, session=date(2026, 9, 21))


def test_an_html_error_page_is_not_mistaken_for_a_file() -> None:
    """The archive answers an unpublished day with its 404 page under a 200."""
    with pytest.raises(NotPublishedError):
        parse_participant_oi(
            b"<!DOCTYPE html>\n<html><body>Not found</body></html>", session=SESSION
        )


def board_row(
    payload: bytes, participant: Participant, segment: Segment
) -> FutureLegs | OptionLegs:
    return parse_participant_oi(payload, session=SESSION)[(participant, segment)]


# -- FII derivative statistics --------------------------------------------------


def test_derivative_value_nets_match_the_published_workbook(stats_payload: bytes) -> None:
    flows = parse_fii_derivative_stats(stats_payload, session=SESSION)
    assert flows[Segment.INDEX_FUTURES].net == Decimal("-1903.18")
    assert flows[Segment.INDEX_OPTIONS].net == Decimal("-23213.82")
    assert flows[Segment.STOCK_FUTURES].net == Decimal("340.48")
    assert flows[Segment.STOCK_OPTIONS].net == Decimal("503.24")


def test_the_per_underlying_rows_are_not_added_to_their_segment(stats_payload: bytes) -> None:
    """``NIFTY FUTURES`` sits under ``INDEX FUTURES`` and is part of it.

    Summing the two would roughly double the segment, and the result would
    still look like a plausible number — which is exactly why it is tested.
    """
    flows = parse_fii_derivative_stats(stats_payload, session=SESSION)
    assert flows[Segment.INDEX_FUTURES].buy == Decimal("3621.17")
    assert set(flows) == {
        Segment.INDEX_FUTURES,
        Segment.INDEX_OPTIONS,
        Segment.STOCK_FUTURES,
        Segment.STOCK_OPTIONS,
    }


def test_a_workbook_dated_another_session_is_refused(stats_payload: bytes) -> None:
    with pytest.raises(NotPublishedError):
        parse_fii_derivative_stats(stats_payload, session=date(2026, 9, 21))


# -- cash market ----------------------------------------------------------------


def test_cash_activity_carries_both_participants_and_its_own_date(cash_payload: bytes) -> None:
    """The endpoint's date is used, not today's: it publishes after the close."""
    session, flow = parse_cash_activity(cash_payload)
    assert session == SESSION
    assert flow.segment is Segment.CASH
    assert flow.fii.net == Decimal("-3809.99")
    assert flow.dii is not None
    assert flow.dii.net == Decimal("4120.07")


def test_cash_activity_without_an_fii_line_is_not_a_session() -> None:
    with pytest.raises(NotPublishedError):
        parse_cash_activity(b"[]")


# -- index close ----------------------------------------------------------------


def test_the_index_row_is_that_sessions_close_not_todays(activity_payload: bytes) -> None:
    close, previous = parse_index_close(activity_payload, index="NIFTY50")
    assert close == Decimal("23329.00")
    assert previous == Decimal("23414.30")


def test_an_index_with_no_known_row_is_absent_rather_than_guessed(
    activity_payload: bytes,
) -> None:
    with pytest.raises(NotPublishedError):
        parse_index_close(activity_payload, index="SENSEX")
