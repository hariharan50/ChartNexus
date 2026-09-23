"""Sector and index membership for the F&O stock universe.

**This is the one hand-maintained table in the catalog.** Everything else comes
from the exchange's own symbol master, which carries no sector classification
and no index membership — so these two facts have to be written down.

That has a real cost, stated plainly: nothing here self-corrects. When NSE
reshuffles an index or a company reclassifies, this file is silently wrong until
a person edits it. It is deliberately one flat, alphabetised table so that
correcting it takes seconds and a diff is readable.

The blast radius is bounded. A wrong sector mislabels a filter and a sidebar
row; it never touches a price, an open-interest figure or a build-up
classification. Symbols absent from the table simply have no sector, and every
consumer already tolerates ``None``.

``NIFTY50`` membership in particular should be treated as best-effort and
reviewed against the NSE factsheet before anyone leans on the Advance/Decline
panel for a decision.
"""

from __future__ import annotations

# The sector vocabulary. Kept short on purpose — a filter with forty options is
# not a filter — and worded the way an Indian market terminal words them.
AUTO = "AUTO"
BANKING = "BANKING"
CAPITAL_GOODS = "CAPITAL GOODS"
CAPITAL_MARKETS = "CAPITAL MRKT"
CEMENT = "CEMENT"
CHEMICALS = "CHEMICALS"
CONSUMER_DURABLES = "CONSUMER DURABLES"
DEFENCE = "DEFENCE"
FINANCE = "FINANCE"
FMCG = "FMCG"
HEALTHCARE = "HEALTHCARE"
INFRA = "INFRA"
INSURANCE = "INSURANCE"
IT = "IT"
LOGISTICS = "LOGISTICS"
METAL = "METAL"
OIL_AND_GAS = "OIL & GAS"
PHARMA = "PHARMA"
POWER = "POWER"
REALTY = "REALTY"
RETAIL = "RETAIL"
SERVICES = "SERVICES"
TELECOM = "TELECOM"
TEXTILES = "TEXTILES"

SECTORS: dict[str, str] = {
    "360ONE": CAPITAL_MARKETS,
    "ABB": CAPITAL_GOODS,
    "ABCAPITAL": FINANCE,
    "ADANIENSOL": POWER,
    "ADANIENT": INFRA,
    "ADANIGREEN": POWER,
    "ADANIPORTS": LOGISTICS,
    "ADANIPOWER": POWER,
    "ALKEM": PHARMA,
    "AMBER": CONSUMER_DURABLES,
    "AMBUJACEM": CEMENT,
    "ANGELONE": CAPITAL_MARKETS,
    "APLAPOLLO": METAL,
    "APOLLOHOSP": HEALTHCARE,
    "ASHOKLEY": AUTO,
    "ASIANPAINT": CONSUMER_DURABLES,
    "ASTRAL": CHEMICALS,
    "ATHERENERG": AUTO,
    "AUBANK": BANKING,
    "AUROPHARMA": PHARMA,
    "AXISBANK": BANKING,
    "BAJAJ-AUTO": AUTO,
    "BAJAJFINSV": FINANCE,
    "BAJAJHLDNG": FINANCE,
    "BAJFINANCE": FINANCE,
    "BANDHANBNK": BANKING,
    "BANKBARODA": BANKING,
    "BANKINDIA": BANKING,
    "BDL": DEFENCE,
    "BEL": DEFENCE,
    "BHARATFORG": AUTO,
    "BHARTIARTL": TELECOM,
    "BHEL": CAPITAL_GOODS,
    "BIOCON": PHARMA,
    "BLUESTARCO": CONSUMER_DURABLES,
    "BOSCHLTD": AUTO,
    "BPCL": OIL_AND_GAS,
    "BRITANNIA": FMCG,
    "BSE": CAPITAL_MARKETS,
    "CAMS": CAPITAL_MARKETS,
    "CANBK": BANKING,
    "CDSL": CAPITAL_MARKETS,
    "CGPOWER": CAPITAL_GOODS,
    "CHOLAFIN": FINANCE,
    "CIPLA": PHARMA,
    "COALINDIA": METAL,
    "COCHINSHIP": DEFENCE,
    "COFORGE": IT,
    "COLPAL": FMCG,
    "CONCOR": LOGISTICS,
    "CROMPTON": CONSUMER_DURABLES,
    "CUMMINSIND": CAPITAL_GOODS,
    "DABUR": FMCG,
    "DELHIVERY": LOGISTICS,
    "DIVISLAB": PHARMA,
    "DIXON": CONSUMER_DURABLES,
    "DLF": REALTY,
    "DMART": RETAIL,
    "DRREDDY": PHARMA,
    "EICHERMOT": AUTO,
    "ETERNAL": SERVICES,
    "FEDERALBNK": BANKING,
    "FORCEMOT": AUTO,
    "FORTIS": HEALTHCARE,
    "GAIL": OIL_AND_GAS,
    "GLENMARK": PHARMA,
    "GMRAIRPORT": INFRA,
    "GODFRYPHLP": FMCG,
    "GODREJCP": FMCG,
    "GODREJPROP": REALTY,
    "GRASIM": CEMENT,
    "GVT&D": CAPITAL_GOODS,
    "HAL": DEFENCE,
    "HAVELLS": CONSUMER_DURABLES,
    "HCLTECH": IT,
    "HDFCAMC": CAPITAL_MARKETS,
    "HDFCBANK": BANKING,
    "HDFCLIFE": INSURANCE,
    "HEROMOTOCO": AUTO,
    "HINDALCO": METAL,
    "HINDPETRO": OIL_AND_GAS,
    "HINDUNILVR": FMCG,
    "HINDZINC": METAL,
    "HYUNDAI": AUTO,
    "ICICIBANK": BANKING,
    "ICICIGI": INSURANCE,
    "ICICIPRULI": INSURANCE,
    "IDEA": TELECOM,
    "IDFCFIRSTB": BANKING,
    "IEX": CAPITAL_MARKETS,
    "INDHOTEL": SERVICES,
    "INDIANB": BANKING,
    "INDIGO": SERVICES,
    "INDUSINDBK": BANKING,
    "INDUSTOWER": TELECOM,
    "INFY": IT,
    "INOXWIND": CAPITAL_GOODS,
    "IOC": OIL_AND_GAS,
    "IREDA": FINANCE,
    "IRFC": FINANCE,
    "ITC": FMCG,
    "JINDALSTEL": METAL,
    "JIOFIN": FINANCE,
    "JSWENERGY": POWER,
    "JSWSTEEL": METAL,
    "JUBLFOOD": SERVICES,
    "KALYANKJIL": RETAIL,
    "KAYNES": CAPITAL_GOODS,
    "KEI": CAPITAL_GOODS,
    "KFINTECH": CAPITAL_MARKETS,
    "KOTAKBANK": BANKING,
    "KPITTECH": IT,
    "LAURUSLABS": PHARMA,
    "LICHSGFIN": FINANCE,
    "LICI": INSURANCE,
    "LODHA": REALTY,
    "LT": INFRA,
    "LTF": FINANCE,
    "LTM": IT,
    "LUPIN": PHARMA,
    "M&M": AUTO,
    "MAHABANK": BANKING,
    "MANAPPURAM": FINANCE,
    "MANKIND": PHARMA,
    "MARICO": FMCG,
    "MARUTI": AUTO,
    "MAXHEALTH": HEALTHCARE,
    "MAZDOCK": DEFENCE,
    "MCX": CAPITAL_MARKETS,
    "MFSL": INSURANCE,
    "MOTHERSON": AUTO,
    "MOTILALOFS": CAPITAL_MARKETS,
    "MPHASIS": IT,
    "MUTHOOTFIN": FINANCE,
    "NAM-INDIA": CAPITAL_MARKETS,
    "NATIONALUM": METAL,
    "NAUKRI": SERVICES,
    "NBCC": INFRA,
    "NESTLEIND": FMCG,
    "NHPC": POWER,
    "NMDC": METAL,
    "NTPC": POWER,
    "NYKAA": RETAIL,
    "OBEROIRLTY": REALTY,
    "OFSS": IT,
    "OIL": OIL_AND_GAS,
    "ONGC": OIL_AND_GAS,
    "PAGEIND": TEXTILES,
    "PATANJALI": FMCG,
    "PAYTM": FINANCE,
    "PERSISTENT": IT,
    "PETRONET": OIL_AND_GAS,
    "PFC": FINANCE,
    "PGEL": CONSUMER_DURABLES,
    "PHOENIXLTD": REALTY,
    "PIDILITIND": CHEMICALS,
    "PIIND": CHEMICALS,
    "PNB": BANKING,
    "PNBHOUSING": FINANCE,
    "POLICYBZR": FINANCE,
    "POLYCAB": CAPITAL_GOODS,
    "POWERGRID": POWER,
    "POWERINDIA": CAPITAL_GOODS,
    "PREMIERENE": POWER,
    "PRESTIGE": REALTY,
    "RADICO": FMCG,
    "RBLBANK": BANKING,
    "RECLTD": FINANCE,
    "RELIANCE": OIL_AND_GAS,
    "RVNL": INFRA,
    "SAGILITY": IT,
    "SAIL": METAL,
    "SBICARD": FINANCE,
    "SBILIFE": INSURANCE,
    "SBIN": BANKING,
    "SHREECEM": CEMENT,
    "SHRIRAMFIN": FINANCE,
    "SIEMENS": CAPITAL_GOODS,
    "SOLARINDS": CHEMICALS,
    "SONACOMS": AUTO,
    "SRF": CHEMICALS,
    "SUNPHARMA": PHARMA,
    "SUPREMEIND": CHEMICALS,
    "SUZLON": CAPITAL_GOODS,
    "SWIGGY": SERVICES,
    "TATACONSUM": FMCG,
    "TATAELXSI": IT,
    "TATAPOWER": POWER,
    "TATASTEEL": METAL,
    "TCS": IT,
    "TECHM": IT,
    "TIINDIA": AUTO,
    "TITAN": CONSUMER_DURABLES,
    "TMPV": AUTO,
    "TORNTPHARM": PHARMA,
    "TRENT": RETAIL,
    "TVSMOTOR": AUTO,
    "ULTRACEMCO": CEMENT,
    "UNIONBANK": BANKING,
    "UNITDSPR": FMCG,
    "UNOMINDA": AUTO,
    "UPL": CHEMICALS,
    "VBL": FMCG,
    "VEDL": METAL,
    "VMM": RETAIL,
    "VOLTAS": CONSUMER_DURABLES,
    "WAAREEENER": POWER,
    "WIPRO": IT,
    "YESBANK": BANKING,
    "ZYDUSLIFE": PHARMA,
}

# Index membership, for the Advance/Decline panel.
#
# BANKNIFTY is a short, stable list and is reliable. NIFTY50 drifts at every
# semi-annual review and this copy is best-effort — verify against the NSE
# factsheet before treating its Advance/Decline row as authoritative.
#
# The sizes are asserted in tests/unit/infrastructure/catalog. A "NIFTY 50"
# holding 51 names is the obvious way for a well-meaning edit here to go wrong,
# and it is the kind of error nobody notices by eye.
INDEX_MEMBERS: dict[str, frozenset[str]] = {
    "BANKNIFTY": frozenset(
        {
            "AUBANK",
            "AXISBANK",
            "BANKBARODA",
            "CANBK",
            "FEDERALBNK",
            "HDFCBANK",
            "ICICIBANK",
            "IDFCFIRSTB",
            "INDUSINDBK",
            "KOTAKBANK",
            "PNB",
            "SBIN",
        }
    ),
    "NIFTY50": frozenset(
        {
            "ADANIENT",
            "ADANIPORTS",
            "APOLLOHOSP",
            "ASIANPAINT",
            "AXISBANK",
            "BAJAJ-AUTO",
            "BAJAJFINSV",
            "BAJFINANCE",
            "BEL",
            "BHARTIARTL",
            "CIPLA",
            "COALINDIA",
            "DRREDDY",
            "EICHERMOT",
            "ETERNAL",
            "GRASIM",
            "HCLTECH",
            "HDFCBANK",
            "HDFCLIFE",
            "HEROMOTOCO",
            "HINDALCO",
            "HINDUNILVR",
            "ICICIBANK",
            "INFY",
            "ITC",
            "JIOFIN",
            "JSWSTEEL",
            "KOTAKBANK",
            "LT",
            "M&M",
            "MARUTI",
            "MAXHEALTH",
            "NESTLEIND",
            "NTPC",
            "ONGC",
            "POWERGRID",
            "RELIANCE",
            "SBILIFE",
            "SBIN",
            "SHRIRAMFIN",
            "SUNPHARMA",
            "TATACONSUM",
            "TATASTEEL",
            "TCS",
            "TECHM",
            "TITAN",
            "TMPV",
            "TRENT",
            "ULTRACEMCO",
            "WIPRO",
        }
    ),
}


def sector_for(symbol: str) -> str | None:
    """The sector for a symbol, or ``None`` if it is not classified.

    ``None`` is a normal answer, not a failure: index contracts have no sector,
    and a stock newly added to the F&O list will not be in this table until
    someone adds it.
    """
    return SECTORS.get(symbol.strip().upper())


def indices_for(symbol: str) -> tuple[str, ...]:
    """Which tracked indices a symbol belongs to, alphabetically."""
    needle = symbol.strip().upper()
    return tuple(sorted(name for name, members in INDEX_MEMBERS.items() if needle in members))
