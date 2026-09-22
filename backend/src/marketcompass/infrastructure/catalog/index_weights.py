"""Free-float index weights for the indices the Analysis pages cover.

**The second hand-maintained table in the catalog**, and it carries the same
warning as :mod:`sector_map`: nothing here self-corrects. NSE rebalances
these indices semi-annually and the free-float factors drift between
rebalances, so this file is silently stale until someone edits it against the
current factsheet.

The blast radius is bounded and worth stating precisely, because "the weights
are approximate" sounds worse than it is:

* Advance/Decline is a **count**. Weights do not enter it at all.
* Sector Rotation uses weights to *average* and to *size bubbles*. A weight
  that is 0.3 points stale moves a bubble slightly; it does not move a sector
  across a quadrant boundary.
* Contributors and Weightage are the two that read weights directly. There,
  a stale table shows up as a contribution that is a fraction of a point off —
  never as a wrong sign, because the sign comes entirely from the price.

The contribution maths renormalises whatever is here to sum to 100 across the
members it could price (see the ``contribution`` domain module), so the table
does **not** have to add up exactly and a missing member costs only its own
row. Keep it alphabetical inside each index so a diff is readable.

Percentages, not fractions: 13.2 means 13.2% of the index.
"""

from __future__ import annotations

from decimal import Decimal

#: Approximate free-float weights, percent of index.
#:
#: Sourced from the NSE factsheets and rounded to one decimal — a second
#: decimal would imply a precision this table cannot keep. The dict is keyed
#: by the same trading symbols ``sector_map.INDEX_MEMBERS`` uses; the two are
#: cross-checked in ``tests/unit/infrastructure/catalog``, which is what keeps
#: a renamed ticker from silently losing its weight.
INDEX_WEIGHTS: dict[str, dict[str, Decimal]] = {
    "NIFTY50": {
        "ADANIENT": Decimal("0.9"),
        "ADANIPORTS": Decimal("0.8"),
        "APOLLOHOSP": Decimal("0.6"),
        "ASIANPAINT": Decimal("1.1"),
        "AXISBANK": Decimal("3.1"),
        "BAJAJ-AUTO": Decimal("0.6"),
        "BAJAJFINSV": Decimal("1.0"),
        "BAJFINANCE": Decimal("2.1"),
        "BEL": Decimal("0.9"),
        "BHARTIARTL": Decimal("4.5"),
        "CIPLA": Decimal("0.7"),
        "COALINDIA": Decimal("0.9"),
        "DRREDDY": Decimal("0.7"),
        "EICHERMOT": Decimal("0.6"),
        "ETERNAL": Decimal("1.0"),
        "GRASIM": Decimal("0.8"),
        "HCLTECH": Decimal("1.5"),
        "HDFCBANK": Decimal("13.2"),
        "HDFCLIFE": Decimal("0.6"),
        "HEROMOTOCO": Decimal("0.5"),
        "HINDALCO": Decimal("0.8"),
        "HINDUNILVR": Decimal("2.1"),
        "ICICIBANK": Decimal("9.0"),
        "INFY": Decimal("5.3"),
        "ITC": Decimal("3.7"),
        "JIOFIN": Decimal("0.8"),
        "JSWSTEEL": Decimal("0.9"),
        "KOTAKBANK": Decimal("2.6"),
        "LT": Decimal("3.6"),
        "M&M": Decimal("2.4"),
        "MARUTI": Decimal("1.7"),
        "MAXHEALTH": Decimal("0.4"),
        "NESTLEIND": Decimal("0.8"),
        "NTPC": Decimal("1.6"),
        "ONGC": Decimal("0.8"),
        "POWERGRID": Decimal("1.2"),
        "RELIANCE": Decimal("8.3"),
        "SBILIFE": Decimal("0.7"),
        "SBIN": Decimal("3.0"),
        "SHRIRAMFIN": Decimal("0.7"),
        "SUNPHARMA": Decimal("1.8"),
        "TATACONSUM": Decimal("0.6"),
        "TATASTEEL": Decimal("1.2"),
        "TCS": Decimal("3.8"),
        "TECHM": Decimal("0.8"),
        "TITAN": Decimal("1.3"),
        "TMPV": Decimal("1.2"),
        "TRENT": Decimal("1.0"),
        "ULTRACEMCO": Decimal("1.3"),
        "WIPRO": Decimal("0.6"),
    },
    "BANKNIFTY": {
        "AUBANK": Decimal("2.2"),
        "AXISBANK": Decimal("9.0"),
        "BANKBARODA": Decimal("2.6"),
        "CANBK": Decimal("2.4"),
        "FEDERALBNK": Decimal("2.3"),
        "HDFCBANK": Decimal("30.0"),
        "ICICIBANK": Decimal("25.5"),
        "IDFCFIRSTB": Decimal("1.9"),
        "INDUSINDBK": Decimal("3.2"),
        "KOTAKBANK": Decimal("8.0"),
        "PNB": Decimal("2.4"),
        "SBIN": Decimal("10.0"),
    },
}

#: The instrument each index's own level is read from, so the pages can print
#: the published level rather than a figure reconstructed from the members.
#: Keyed the way the instrument catalog spells them.
INDEX_INSTRUMENTS: dict[str, str] = {
    "NIFTY50": "NIFTY",
    "BANKNIFTY": "BANKNIFTY",
}

#: Display order for the index picker — the broad benchmark first.
TRACKED_INDICES: tuple[str, ...] = ("NIFTY50", "BANKNIFTY")

#: How each index is labelled on screen. The internal keys are terse because
#: they are also cache keys and query parameters; these are for people.
INDEX_LABELS: dict[str, str] = {
    "NIFTY50": "NIFTY 50",
    "BANKNIFTY": "BANK NIFTY",
}


def weights_for(index: str) -> dict[str, Decimal]:
    """Every member weight for ``index``, or an empty mapping if untracked."""
    return INDEX_WEIGHTS.get(index.strip().upper(), {})


def weight_of(index: str, symbol: str) -> Decimal:
    """One member's weight, or zero when the table does not carry it.

    Zero rather than ``None``: an unweighted member still belongs to the index
    and still appears in the counts, it simply contributes nothing to any
    weighted figure until someone adds its row.
    """
    return weights_for(index).get(symbol.strip().upper(), Decimal(0))


def label_for(index: str) -> str:
    key = index.strip().upper()
    return INDEX_LABELS.get(key, key)
