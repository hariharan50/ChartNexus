"""The F&O universe, read from FYERS' published symbol masters.

These CSVs are public — they need no broker account, no OAuth, and no quota —
which is what lets the catalog refresh on a schedule even for a deployment
where nobody has connected a broker yet.

Two files per exchange:

* ``<EX>_FO.csv``  every derivative contract. Futures rows give the underlying
  list plus lot and tick size; option rows give the strike ladder.
* ``<EX>_CM.csv``  the cash segment, which also lists index rows. Joined on the
  underlying ticker it supplies the company name, the ISIN, and the spot symbol
  — including ``NSE:NIFTY50-INDEX`` and ``BSE:SENSEX-INDEX``, so not one
  broker string has to be written by hand.

NSE is parsed first and BSE only contributes symbols NSE did not already
provide. The fourteen stocks BSE also lists are the same companies on a
secondary venue, and the catalog holds one row per company.
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from itertools import pairwise

import httpx

from chartnexus.contexts.instrument_catalog.domain.instrument import (
    Instrument,
    InstrumentKind,
)
from chartnexus.infrastructure.catalog.sector_map import indices_for, sector_for
from chartnexus.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)

_BASE_URL = "https://public.fyers.in/sym_details"

#: India observes no DST, so a fixed offset is exact.
_IST = timezone(timedelta(hours=5, minutes=30))

# The masters are headerless and positional. Named here once so that a column
# shift upstream is a one-line fix rather than a hunt through index literals.
_COL_DESCRIPTION = 1
_COL_INSTRUMENT_TYPE = 2
_COL_LOT_SIZE = 3
_COL_TICK_SIZE = 4
_COL_ISIN = 5
_COL_EXPIRY_EPOCH = 8
_COL_TICKER = 9
_COL_UNDERLYING = 13
_COL_UNDERLYING_TOKEN = 14
_COL_STRIKE = 15
_COL_OPTION_TYPE = 16

_MIN_COLUMNS = 17

# Instrument-type codes, shared by both exchanges' files.
_TYPE_INDEX = "11"
_TYPE_STOCK = "13"

_OPTION_TYPES = frozenset({"CE", "PE"})


@dataclass(frozen=True, slots=True)
class ExchangeMaster:
    """One exchange's pair of master files."""

    exchange: str
    fo_url: str
    cm_url: str

    @classmethod
    def of(cls, exchange: str) -> ExchangeMaster:
        return cls(
            exchange=exchange,
            fo_url=f"{_BASE_URL}/{exchange}_FO.csv",
            cm_url=f"{_BASE_URL}/{exchange}_CM.csv",
        )


# Order matters: the first exchange to claim a symbol keeps it.
EXCHANGES: tuple[ExchangeMaster, ...] = (ExchangeMaster.of("NSE"), ExchangeMaster.of("BSE"))


class FyersSymbolMaster:
    """Implements the ``SymbolMasterPort``."""

    def __init__(
        self, http: httpx.AsyncClient, *, exchanges: tuple[ExchangeMaster, ...] = EXCHANGES
    ) -> None:
        self._http = http
        self._exchanges = exchanges

    async def fetch(self) -> list[Instrument]:
        universe: dict[str, Instrument] = {}

        for master in self._exchanges:
            try:
                fo_rows = await self._download(master.fo_url)
                cm_rows = await self._download(master.cm_url)
            except httpx.HTTPError as exc:
                # One exchange failing must not empty the catalog. NSE carries
                # 216 of the ~219 rows; losing BSE costs three indices, and the
                # sync refuses an entirely empty result anyway.
                log.warning(
                    "symbol_master_download_failed", exchange=master.exchange, error=str(exc)
                )
                continue

            for instrument in parse_universe(fo_rows, cm_rows, exchange=master.exchange):
                universe.setdefault(instrument.symbol, instrument)

        log.info("symbol_master_parsed", instruments=len(universe))
        return list(universe.values())

    async def _download(self, url: str) -> list[list[str]]:
        # These files are ~15 MB; the shared client's default timeout is tuned
        # for quote calls, so give the download its own budget.
        response = await self._http.get(url, timeout=httpx.Timeout(120.0))
        response.raise_for_status()
        return list(csv.reader(io.StringIO(response.text)))


def parse_universe(
    fo_rows: list[list[str]],
    cm_rows: list[list[str]],
    *,
    exchange: str,
) -> list[Instrument]:
    """Turn one exchange's masters into catalog rows.

    Pure and synchronous so it can be tested against a fixture without a
    network round trip.
    """
    cash = _index_by_underlying(cm_rows)

    futures: dict[str, list[str]] = {}
    # Every listed series per underlying, not just the nearest: which contract
    # a page shows is a choice, and the exchange lists three at a time.
    series: dict[str, set[date]] = {}
    strikes: dict[str, dict[str, list[Decimal]]] = {}

    for row in fo_rows:
        if len(row) < _MIN_COLUMNS:
            continue
        underlying = row[_COL_UNDERLYING].strip().upper()
        if not underlying:
            continue

        if row[_COL_OPTION_TYPE] in _OPTION_TYPES:
            strike = _decimal(row[_COL_STRIKE])
            if strike is not None and strike > 0:
                strikes.setdefault(underlying, {}).setdefault(row[_COL_EXPIRY_EPOCH], []).append(
                    strike
                )
            continue

        # Not an option, so a future. NSE marks these ``XX`` and BSE leaves the
        # column blank, which is why membership of the option set is the test
        # rather than equality with any one sentinel.
        expiry = _expiry_date(row)
        if expiry is not None:
            series.setdefault(underlying, set()).add(expiry)

        existing = futures.get(underlying)
        if existing is None or _epoch(row) < _epoch(existing):
            futures[underlying] = row

    instruments: list[Instrument] = []
    for underlying, row in futures.items():
        cash_row = cash.get(underlying)
        if cash_row is None:
            # Without the cash row there is no spot symbol, and an instrument
            # the app cannot price is worse than one it does not list.
            log.warning("instrument_missing_cash_row", symbol=underlying, exchange=exchange)
            continue

        instrument = _build(
            underlying,
            row,
            cash_row,
            strikes.get(underlying),
            exchange,
            expiries=tuple(sorted(series.get(underlying, ()))),
        )
        if instrument is not None:
            instruments.append(instrument)

    return instruments


def _build(
    underlying: str,
    futures_row: list[str],
    cash_row: list[str],
    ladders: dict[str, list[Decimal]] | None,
    exchange: str,
    *,
    expiries: tuple[date, ...] = (),
) -> Instrument | None:
    kind = _kind(futures_row[_COL_INSTRUMENT_TYPE])
    if kind is None:
        return None

    lot_size = _int(futures_row[_COL_LOT_SIZE])
    tick_size = _decimal(futures_row[_COL_TICK_SIZE])
    if lot_size is None or lot_size <= 0 or tick_size is None or tick_size <= 0:
        log.warning("instrument_bad_contract_size", symbol=underlying, exchange=exchange)
        return None

    try:
        return Instrument(
            symbol=underlying,
            kind=kind,
            name=_display_name(cash_row[_COL_DESCRIPTION], underlying, kind),
            exchange=exchange,
            lot_size=lot_size,
            tick_size=tick_size,
            spot_symbol=cash_row[_COL_TICKER].strip(),
            # The root inside the futures ticker is the underlying name itself
            # for every contract both exchanges publish.
            futures_root=underlying,
            isin=(cash_row[_COL_ISIN].strip() or None),
            strike_step=_strike_step(ladders),
            reference_price=_reference_price(ladders),
            underlying_token=(futures_row[_COL_UNDERLYING_TOKEN].strip() or None),
            # `futures_row` is the nearest-dated contract, so its expiry is the
            # front month — exactly, as the exchange lists it.
            front_expiry=_expiry_date(futures_row),
            futures_expiries=expiries,
            # From the curated table; absent for indices and for any stock
            # newly added to the F&O list that nobody has classified yet.
            sector=sector_for(underlying),
            indices=indices_for(underlying),
        )
    except Exception as exc:  # domain validation rejected the row
        log.warning("instrument_rejected", symbol=underlying, exchange=exchange, error=str(exc))
        return None


def _reference_price(ladders: dict[str, list[Decimal]] | None) -> Decimal | None:
    """A plausible spot level, taken as the median listed strike.

    Exchanges list strikes around the money and thin them out towards the
    wings, so the median of the nearest expiry's ladder sits close to spot —
    within about 4% of this app's own hand-captured index levels when checked
    against them. That is nowhere near good enough to *show* anyone, and it is
    never served as a quote; it is the seed the mock provider's random walk
    starts from, replacing a hand-maintained table that could only ever cover
    three instruments.

    Crucially it cannot be wildly wrong, because it is bracketed by strikes the
    exchange actually lists.
    """
    if not ladders:
        return None

    nearest = min(ladders, key=lambda epoch: int(epoch) if epoch.isdigit() else 0)
    ordered = sorted(set(ladders[nearest]))
    if not ordered:
        return None

    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _strike_step(ladders: dict[str, list[Decimal]] | None) -> Decimal | None:
    """The representative gap between adjacent strikes in the nearest expiry.

    Strike ladders are not uniform: the step widens away from the money on all
    but one of the underlyings in the universe. What is wanted here is the
    step that describes the ladder as a whole, so this takes the *most common*
    gap rather than the smallest.

    The distinction matters on exactly five names today, but it matters a lot.
    A corporate action leaves stray adjusted strikes behind, so HINDPETRO's
    smallest gap is 0.75 against a real step of 10, and MPHASIS' is 12 against
    50. Seeding the mock generator from the outlier would synthesise a chain
    with hundreds of implausible strikes.

    This deliberately differs from the Options Lab's ``_infer_step``, which
    takes the minimum: that runs over a *live* chain already centred on the
    money, where the tightest gap is the right answer.
    """
    if not ladders:
        return None

    nearest = min(ladders, key=lambda epoch: int(epoch) if epoch.isdigit() else 0)
    ordered = sorted(set(ladders[nearest]))
    gaps = [b - a for a, b in pairwise(ordered) if b > a]
    if not gaps:
        return None

    counts = Counter(gaps)
    # Ties break to the smaller gap, which is the denser, more conservative
    # ladder to synthesise.
    return min(counts, key=lambda gap: (-counts[gap], gap))


def _display_name(raw: str, underlying: str, kind: InstrumentKind) -> str:
    name = raw.strip()
    if kind is InstrumentKind.INDEX:
        # Cash rows name indices ``NIFTYBANK-INDEX``; the suffix is plumbing.
        name = name.removesuffix("-INDEX").strip()
    return name or underlying


def _index_by_underlying(rows: list[list[str]]) -> dict[str, list[str]]:
    """Cash rows keyed by their underlying ticker, first occurrence winning."""
    indexed: dict[str, list[str]] = {}
    for row in rows:
        if len(row) < _MIN_COLUMNS:
            continue
        key = row[_COL_UNDERLYING].strip().upper()
        if key:
            indexed.setdefault(key, row)
    return indexed


def _kind(instrument_type: str) -> InstrumentKind | None:
    if instrument_type == _TYPE_INDEX:
        return InstrumentKind.INDEX
    if instrument_type == _TYPE_STOCK:
        return InstrumentKind.STOCK
    return None


def _expiry_date(row: list[str]) -> date | None:
    epoch = _epoch(row)
    if epoch <= 0:
        return None
    # The masters stamp expiries in exchange-local time; read them there so a
    # late-evening contract does not land on the previous day.
    return datetime.fromtimestamp(epoch, tz=_IST).date()


def _epoch(row: list[str]) -> int:
    try:
        return int(row[_COL_EXPIRY_EPOCH])
    except (ValueError, TypeError, IndexError):
        return 0


def _int(raw: str) -> int | None:
    try:
        return int(str(raw).strip())
    except (ValueError, TypeError):
        return None


def _decimal(raw: str) -> Decimal | None:
    try:
        return Decimal(str(raw).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None
