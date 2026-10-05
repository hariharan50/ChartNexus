"""The four NSE publications the FII/DII pages are built from, parsed.

Pure functions over bytes. No HTTP, no cache, no clock — so every shape
question ("what is an options net?", "which column is the put short leg?")
is answered in one place and pinned by a unit test against a real file.

The exchange publishes these separately, in three different formats, and they
do not agree on how to write a date:

``fao_participant_oi_DDMMYYYY.csv``
    Participant-wise **open interest**, in contracts. Four participants x four
    segments, long and short legs. This is the board on the Summary page.

``fii_stats_DD-Mon-YYYY.xls``
    FII **derivative statistics**, in rupees crore — buy and sell value per
    segment. A legacy BIFF workbook, which is why ``xlrd`` is a dependency.

``api/fiidiiTradeReact``
    FII and DII **cash market** value, in rupees crore. The one source with no
    date in it: it answers for the latest published session and nothing else.

``archives/equities/mkt/MADDMMYY.csv``
    The daily market activity report, read here for one row — where Nifty 50
    closed. It is the only way to print an index level beside an *archived*
    session that is actually that session's level.

Two of these live behind a webserver that answers a request for an unpublished
day with an HTML error page **under a 200**, so nothing here trusts a status
code: each parser validates the shape it expects and raises
:class:`NotPublishedError` when it does not find it.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final

import xlrd

from chartnexus.contexts.market_breadth.domain.flows import (
    Crore,
    FlowDay,
    Participant,
    ParticipantFlow,
    Segment,
    SegmentFlow,
)
from chartnexus.contexts.market_breadth.domain.open_interest import (
    FutureLegs,
    OptionLegs,
)

ARCHIVE_HOST: Final = "https://nsearchives.nseindia.com"
WWW_HOST: Final = "https://www.nseindia.com"

#: Sent on every request. The archive host serves these files to anything that
#: looks like a browser and rejects requests it does not recognise; the Referer
#: is what the ``www`` JSON endpoint checks.
BROWSER_HEADERS: Final[dict[str, str]] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{WWW_HOST}/",
}


class NotPublishedError(Exception):
    """The exchange has no file for that session — a holiday, or not yet.

    Distinct from a transport error on purpose. A missing file is an ordinary
    fact about the calendar and the caller steps to another day; a timeout is
    a fault and the caller falls back.
    """


# -- urls ---------------------------------------------------------------------

#: Month abbreviations as the ``fii_stats`` filename spells them. Built by hand
#: rather than with ``strftime`` because ``%b`` is locale-dependent, and a
#: server running under a non-English locale would ask for a file that has
#: never existed.
_MONTHS: Final[tuple[str, ...]] = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


def participant_oi_url(session: date) -> str:
    return f"{ARCHIVE_HOST}/content/nsccl/fao_participant_oi_{session:%d%m%Y}.csv"


def fii_derivative_stats_url(session: date) -> str:
    stamp = f"{session.day:02d}-{_MONTHS[session.month - 1]}-{session.year}"
    return f"{ARCHIVE_HOST}/content/fo/fii_stats_{stamp}.xls"


def market_activity_url(session: date) -> str:
    return f"{ARCHIVE_HOST}/archives/equities/mkt/MA{session:%d%m%y}.csv"


def cash_activity_url() -> str:
    return f"{WWW_HOST}/api/fiidiiTradeReact"


# -- participant-wise open interest -------------------------------------------

#: Row labels in the participant files, lowercased, to the domain's four
#: participants. ``TOTAL`` is deliberately absent: it is the column sum, not a
#: fifth participant, and including it would double every segment's board.
_PARTICIPANTS: Final[dict[str, Participant]] = {
    "client": Participant.CLIENT,
    "dii": Participant.DII,
    "fii": Participant.FII,
    "pro": Participant.PRO,
}

#: Which header each futures leg is under. Headers are matched by name rather
#: than by position because the published files pad several of them with
#: trailing spaces, and a column has been inserted upstream before now.
_FUTURE_LEGS: Final[dict[Segment, tuple[str, str]]] = {
    Segment.INDEX_FUTURES: ("future index long", "future index short"),
    Segment.STOCK_FUTURES: ("future stock long", "future stock short"),
}

#: The four option legs per segment, in ``OptionLegs`` field order.
_OPTION_LEGS: Final[dict[Segment, tuple[str, str, str, str]]] = {
    Segment.INDEX_OPTIONS: (
        "option index call long",
        "option index call short",
        "option index put long",
        "option index put short",
    ),
    Segment.STOCK_OPTIONS: (
        "option stock call long",
        "option stock call short",
        "option stock put long",
        "option stock put short",
    ),
}

#: Keyed by participant and segment — the shape the flow source assembles a
#: board from, and the shape the generator it replaces already produced.
OiBoard = dict[tuple[Participant, Segment], FutureLegs | OptionLegs]


def parse_participant_oi(payload: bytes, *, session: date) -> OiBoard:
    """One session's whole participant-wise open interest board.

    ``session`` is checked against the date written inside the file rather
    than trusted from the URL. The archive has served a stale file under a
    fresh name before, and a board dated one day and labelled another is the
    single worst thing this page could show.
    """
    rows = _csv_rows(payload)
    header_at = _header_row(rows, first="client type")
    columns = {name.strip().lower(): index for index, name in enumerate(rows[header_at])}
    _require_session(_oi_file_date(rows), session)

    board: OiBoard = {}
    for row in rows[header_at + 1 :]:
        if not row:
            continue
        participant = _PARTICIPANTS.get(row[0].strip().lower())
        if participant is None:
            continue
        for future_segment, (long_at, short_at) in _FUTURE_LEGS.items():
            board[(participant, future_segment)] = FutureLegs(
                long=_cell(row, columns, long_at),
                short=_cell(row, columns, short_at),
            )
        for option_segment, legs in _OPTION_LEGS.items():
            board[(participant, option_segment)] = OptionLegs(
                call_long=_cell(row, columns, legs[0]),
                call_short=_cell(row, columns, legs[1]),
                put_long=_cell(row, columns, legs[2]),
                put_short=_cell(row, columns, legs[3]),
            )

    _require_complete(board)
    return board


def _oi_file_date(rows: list[list[str]]) -> date:
    """The date in the file's own title line: ``... as on Sep 22, 2026``."""
    for row in rows[:4]:
        if not row:
            continue
        # The title is one cell containing a comma — `Sep 22, 2026` — so the
        # CSV reader has already split it in two. Rejoined rather than read
        # from cell 0, which would carry only half the date.
        title = ",".join(row).strip().strip('"')
        _, separator, tail = title.partition(" as on ")
        if separator:
            return _parse_long_date(tail.strip().strip('",').strip())
    raise NotPublishedError("no title line")


def _parse_long_date(text: str) -> date:
    try:
        return datetime.strptime(text, "%b %d, %Y").date()  # noqa: DTZ007 — a date, not a moment
    except ValueError as exc:
        raise NotPublishedError(f"unreadable file date {text!r}") from exc


def _require_session(found: date, wanted: date) -> None:
    if found != wanted:
        raise NotPublishedError(f"file is dated {found}, asked for {wanted}")


def _require_complete(board: OiBoard) -> None:
    """Every participant in every segment, or the board is not worth drawing.

    A partial board would still render — and the four nets would not sum to
    zero, which the page reports as the exchange publishing an incomplete
    file rather than as us having dropped a row.
    """
    missing = [
        (participant, segment)
        for participant in _PARTICIPANTS.values()
        for segment in (*_FUTURE_LEGS, *_OPTION_LEGS)
        if (participant, segment) not in board
    ]
    if missing:
        raise NotPublishedError(f"{len(missing)} participant/segment cells missing")


def _cell(row: list[str], columns: dict[str, int], name: str) -> int:
    index = columns.get(name)
    if index is None or index >= len(row):
        raise NotPublishedError(f"column {name!r} missing")
    return _to_int(row[index])


def _to_int(text: str) -> int:
    cleaned = text.strip().replace(",", "")
    if not cleaned or cleaned == "-":
        return 0
    try:
        return int(Decimal(cleaned))
    except (InvalidOperation, ValueError) as exc:
        raise NotPublishedError(f"unreadable contract count {text!r}") from exc


# -- FII derivative statistics -------------------------------------------------

#: Row labels in the workbook's first column to the segment they describe.
#: The file also carries a per-underlying breakdown (``NIFTY FUTURES``,
#: ``BANKNIFTY OPTIONS`` and so on) directly beneath each of these; those are
#: components of the row above, and adding them in would double the segment.
_STATS_SEGMENTS: Final[dict[str, Segment]] = {
    "INDEX FUTURES": Segment.INDEX_FUTURES,
    "INDEX OPTIONS": Segment.INDEX_OPTIONS,
    "STOCK FUTURES": Segment.STOCK_FUTURES,
    "STOCK OPTIONS": Segment.STOCK_OPTIONS,
}

#: Columns in the workbook: label, buy contracts, buy crore, sell contracts,
#: sell crore, then the end-of-day open interest pair.
_STATS_BUY_CRORE: Final = 2
_STATS_SELL_CRORE: Final = 4


def parse_fii_derivative_stats(payload: bytes, *, session: date) -> dict[Segment, ParticipantFlow]:
    """FII buy and sell value per derivative segment, in rupees crore.

    FII only. The workbook carries no DII line, which is not an omission on
    our side: domestic institutions' derivative *value* is not published, and
    the pages render it as a dash rather than a zero.
    """
    try:
        sheet = xlrd.open_workbook(file_contents=payload).sheet_by_index(0)
    except Exception as exc:  # xlrd raises a family of errors of its own
        raise NotPublishedError(f"unreadable workbook: {exc!r}") from exc

    rows = [[_stats_text(cell.value) for cell in sheet.row(index)] for index in range(sheet.nrows)]
    _require_session(_stats_file_date(rows), session)

    flows: dict[Segment, ParticipantFlow] = {}
    for row in rows:
        segment = _STATS_SEGMENTS.get(row[0].strip().upper()) if row else None
        if segment is None or segment in flows:
            continue
        flows[segment] = ParticipantFlow(
            buy=_to_crore(row[_STATS_BUY_CRORE]),
            sell=_to_crore(row[_STATS_SELL_CRORE]),
        )

    if len(flows) != len(_STATS_SEGMENTS):
        raise NotPublishedError(f"only {len(flows)} of {len(_STATS_SEGMENTS)} segments found")
    return flows


def _stats_text(value: object) -> str:
    """Workbook cells arrive as text or as floats, depending on the row."""
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _stats_file_date(rows: list[list[str]]) -> date:
    """``FII DERIVATIVES STATISTICS FOR 22-Sep-2026``, in the title cell."""
    for row in rows[:3]:
        if not row:
            continue
        _, separator, tail = row[0].strip().partition(" FOR ")
        if separator:
            return _parse_short_date(tail)
    raise NotPublishedError("no title cell")


def _to_crore(text: str) -> Crore:
    cleaned = text.strip().replace(",", "")
    if not cleaned or cleaned == "-":
        return Decimal(0)
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise NotPublishedError(f"unreadable crore figure {text!r}") from exc


# -- cash market activity ------------------------------------------------------

#: How the JSON endpoint names the two participants. "FII/FPI" is the
#: exchange's own label — foreign portfolio investors are the same line.
_CASH_CATEGORIES: Final[dict[str, Participant]] = {
    "fii/fpi": Participant.FII,
    "fii": Participant.FII,
    "dii": Participant.DII,
}


def parse_cash_activity(payload: bytes) -> tuple[date, SegmentFlow]:
    """The latest published cash session, and both participants in it.

    Returns the session the endpoint answered for rather than assuming it is
    today: it publishes after the close, so through a trading morning it is
    still yesterday, and dating it "now" would put the previous session's
    figures under the current date.
    """
    try:
        entries: Any = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise NotPublishedError("cash activity is not JSON") from exc
    if not isinstance(entries, list) or not entries:
        raise NotPublishedError("cash activity is empty")

    session: date | None = None
    flows: dict[Participant, ParticipantFlow] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        participant = _CASH_CATEGORIES.get(str(entry.get("category", "")).strip().lower())
        if participant is None:
            continue
        session = session or _parse_short_date(str(entry.get("date", "")))
        flows[participant] = ParticipantFlow(
            buy=_to_crore(str(entry.get("buyValue", ""))),
            sell=_to_crore(str(entry.get("sellValue", ""))),
        )

    fii = flows.get(Participant.FII)
    if session is None or fii is None:
        raise NotPublishedError("cash activity carried no FII line")
    return session, SegmentFlow(segment=Segment.CASH, fii=fii, dii=flows.get(Participant.DII))


def _parse_short_date(text: str) -> date:
    try:
        return datetime.strptime(  # noqa: DTZ007 — a date, not a moment
            text.strip(), "%d-%b-%Y"
        ).date()
    except ValueError as exc:
        raise NotPublishedError(f"unreadable session date {text!r}") from exc


# -- the daily market activity report ------------------------------------------

#: The index rows the report is read for, by the name it prints them under.
INDEX_ROW_NAMES: Final[dict[str, str]] = {
    "NIFTY50": "nifty 50",
    "BANKNIFTY": "nifty bank",
}

#: Offsets from the label cell across the index table: previous close, then
#: open, high, low and close.
_MA_PREVIOUS_CLOSE: Final = 1
_MA_CLOSE: Final = 5


def parse_index_close(payload: bytes, *, index: str) -> tuple[Decimal, Decimal]:
    """``(close, previous_close)`` for one index on the report's session.

    Read from the archived report rather than from the broker, because the
    broker answers for *now*: asking it about a session three weeks back
    returns today's level, which under that day's date is simply false.
    """
    wanted = INDEX_ROW_NAMES.get(index.upper())
    if wanted is None:
        raise NotPublishedError(f"no market-activity row known for {index}")

    for row in _csv_rows(payload):
        # The table is indented by one empty column, so the label is not
        # reliably in cell 0 — scan the row's leading cells for it instead.
        offset = next((at for at, cell in enumerate(row[:2]) if cell.strip().lower() == wanted), -1)
        if offset < 0:
            continue
        if offset + _MA_CLOSE >= len(row):
            raise NotPublishedError(f"{wanted} row is truncated")
        return (
            _to_crore(row[offset + _MA_CLOSE]),
            _to_crore(row[offset + _MA_PREVIOUS_CLOSE]),
        )
    raise NotPublishedError(f"{wanted} not in the market activity report")


# -- shared --------------------------------------------------------------------


def _csv_rows(payload: bytes) -> list[list[str]]:
    text = payload.decode("utf-8", errors="replace")
    if text.lstrip()[:15].lower().startswith(("<!doctype", "<html")):
        # The archive answers an unpublished day with its 404 page under a
        # 200, so the status code says nothing and the body says everything.
        raise NotPublishedError("archive returned an HTML page")
    return list(csv.reader(io.StringIO(text)))


def _header_row(rows: list[list[str]], *, first: str) -> int:
    for index, row in enumerate(rows[:8]):
        if row and row[0].strip().lower() == first:
            return index
    raise NotPublishedError(f"no {first!r} header row")


def flow_day(
    session: date,
    *,
    cash: SegmentFlow | None,
    derivatives: dict[Segment, ParticipantFlow] | None = None,
) -> FlowDay:
    """Assemble one published session from whichever files answered.

    Both halves are optional and they come from different publications, so a
    session can legitimately carry cash without derivative value or the other
    way round. What it must never do is carry a segment invented to fill a
    gap — an absent segment is dropped, and every page renders that as a dash.
    """
    segments: list[SegmentFlow] = []
    if cash is not None:
        segments.append(cash)
    segments.extend(
        SegmentFlow(segment=segment, fii=flow) for segment, flow in (derivatives or {}).items()
    )
    return FlowDay(session_date=session, segments=tuple(segments))
