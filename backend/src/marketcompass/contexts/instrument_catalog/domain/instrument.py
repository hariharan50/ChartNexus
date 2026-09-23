"""What the application knows about a tradeable underlying.

The catalog is the answer to "which instruments exist?", a question the rest of
the application used to answer with a three-member enum. It holds reference
data only — identity, contract geometry, and the broker strings needed to ask
for a quote. Market data never lives here; the single price-shaped field,
``reference_price``, is a mock seed and says so.

Everything in this module is derived from an exchange symbol master, not typed
by hand: the F&O list changes by NSE circular several times a year, and lot
sizes are revised more often than that.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from marketcompass.shared_kernel.domain.errors import ValidationError

# NSE tickers run to 10 characters today (``MIDCPNIFTY``, ``BAJAJ-AUTO``). The
# limit is deliberately looser than the observed maximum but still tight enough
# that a malformed string is rejected rather than stored.
MAX_SYMBOL_LENGTH = 20


class InstrumentKind(StrEnum):
    """Whether the underlying is an index or a single company.

    The distinction is not cosmetic. It decides the shape of the broker's spot
    symbol (an index is quoted as ``-INDEX``, a company as ``-EQ``), and it is
    the honest way to answer "does this have weekly expiries?" — stock options
    are monthly-only, and only some indices carry weeklies.
    """

    INDEX = "index"
    STOCK = "stock"


@dataclass(frozen=True, slots=True)
class Instrument:
    """One tradeable F&O underlying.

    ``symbol`` is the canonical name the whole application speaks — ``NIFTY``,
    ``RELIANCE``. ``spot_symbol`` and ``futures_root`` are the only
    broker-shaped strings, and they exist here so that the symbol mapper can be
    a lookup rather than a hand-maintained table.
    """

    symbol: str
    kind: InstrumentKind
    name: str
    exchange: str
    lot_size: int
    tick_size: Decimal
    spot_symbol: str
    futures_root: str
    # Indices have no ISIN. Stocks always do, and it is the only identifier
    # that survives a ticker rename, which is why it is worth carrying.
    isin: str | None = None
    # The gap between adjacent strikes near the money. Live analytics infer
    # this from the chain the broker returns, so this value is for the mock
    # provider (which has to *synthesise* a ladder) and for display. Decimal,
    # not int: eleven names in the universe trade on a 2.5 step.
    strike_step: Decimal | None = None
    #: The nearest listed futures expiry, straight from the exchange master.
    #:
    #: Load-bearing, not decoration. NSE moved monthly expiry off the last
    #: Thursday, so the calendar heuristic that used to stand in for this is
    #: simply wrong — and wrong in a way that builds October symbols for
    #: contracts still trading in September.
    front_expiry: date | None = None
    #: Every listed futures expiry for this underlying, ascending, the front
    #: month first. Empty for a row synced before the field existed.
    #:
    #: The exchange lists three monthly series at a time, and which one a page
    #: is showing is a *choice* — so the whole list is carried rather than only
    #: the nearest. Per instrument, not universe-wide, because the dates do not
    #: agree across it: NSE and BSE settle on different days, and a name whose
    #: contract was holiday-shifted differs from its neighbours.
    futures_expiries: tuple[date, ...] = ()
    underlying_token: str | None = None
    # A plausible price level, NOT a quote. Derived from the middle of the
    # listed strike ladder, which brackets the money by construction. It exists
    # so the mock provider can seed a believable random walk for an instrument
    # nobody has a live price for; it is stale the moment it is written and
    # must never be served as market data.
    reference_price: Decimal | None = None
    # Neither of the next two is carried by any exchange symbol master; both
    # come from a curated table, so every consumer must tolerate them being
    # absent.
    sector: str | None = None
    #: Tracked indices this instrument belongs to, e.g. ("NIFTY50",).
    indices: tuple[str, ...] = ()
    is_active: bool = True

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise ValidationError("instrument symbol must not be blank", field="symbol")
        if len(self.symbol) > MAX_SYMBOL_LENGTH:
            raise ValidationError(
                f"instrument symbol exceeds {MAX_SYMBOL_LENGTH} characters", field="symbol"
            )
        if self.symbol != self.symbol.strip().upper():
            raise ValidationError("instrument symbol must be upper-case", field="symbol")
        if self.lot_size <= 0:
            raise ValidationError("lot size must be positive", field="lot_size")
        if self.tick_size <= 0:
            raise ValidationError("tick size must be positive", field="tick_size")
        if self.strike_step is not None and self.strike_step <= 0:
            raise ValidationError("strike step must be positive", field="strike_step")
        if self.reference_price is not None and self.reference_price <= 0:
            raise ValidationError("reference price must be positive", field="reference_price")
        if not self.spot_symbol:
            raise ValidationError("spot symbol must not be blank", field="spot_symbol")
        if not self.futures_root:
            raise ValidationError("futures root must not be blank", field="futures_root")
        if list(self.futures_expiries) != sorted(set(self.futures_expiries)):
            # Consumers index into this by series — element 0 is the near
            # month, 1 the next — so the order is load-bearing rather than
            # cosmetic, and a duplicate would shift every series after it.
            raise ValidationError(
                "futures expiries must be ascending and unique", field="futures_expiries"
            )

    @property
    def is_index(self) -> bool:
        return self.kind is InstrumentKind.INDEX
