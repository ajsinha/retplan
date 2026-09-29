"""Market data: securities collected every day whether anyone holds them or not.

An index, a fund, a currency pair or a future someone wants to follow is marked
for collection (``securities.collect``); the daily collector then stores its bar
- open, high, low, close, adjusted close, volume - alongside the held symbols,
keeping as much history as the security's ``keep_days`` asks (else the global
retention). This module holds the plain data the market-data page offers: the
ready-made sets, the history choices and how Yahoo's quote types are named.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

# Yahoo symbols: ^ for indices, =X for currency pairs, =F for futures, -USD for crypto.
PRESETS: list[dict] = [
    dict(key="us_indices", label="US indices", icon="flag",
         blurb="S&P 500, Dow, Nasdaq, Russell 2000, VIX.",
         symbols=["^GSPC", "^DJI", "^IXIC", "^RUT", "^VIX"]),
    dict(key="world_indices", label="World indices", icon="globe",
         blurb="FTSE 100, DAX, CAC 40, Euro Stoxx 50, Nikkei, Hang Seng, TSX, ASX 200.",
         symbols=["^FTSE", "^GDAXI", "^FCHI", "^STOXX50E", "^N225", "^HSI", "^GSPTSE",
                  "^AXJO"]),
    dict(key="funds", label="Broad index funds", icon="pie-chart",
         blurb="Total market, S&P 500, world, international and bond index funds.",
         symbols=["VTI", "VOO", "VT", "VXUS", "BND", "VTSAX", "FXAIX"]),
    dict(key="sectors", label="US sector ETFs", icon="grid-3x3-gap",
         blurb="The eleven Select Sector SPDRs.",
         symbols=["XLK", "XLF", "XLV", "XLE", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE",
                  "XLC"]),
    dict(key="rates", label="Rates and bonds", icon="percent",
         blurb="Treasury yields (13-week, 10-year, 30-year) and bond ETFs.",
         symbols=["^IRX", "^TNX", "^TYX", "AGG", "TLT", "SHY", "LQD", "HYG", "TIP"]),
    dict(key="commodities", label="Commodities", icon="droplet-half",
         blurb="Gold, silver, oil, natural gas, copper futures; gold and silver ETFs.",
         symbols=["GC=F", "SI=F", "CL=F", "NG=F", "HG=F", "GLD", "SLV"]),
    dict(key="currencies", label="Currencies", icon="currency-exchange",
         blurb="The major pairs and the dollar index.",
         symbols=["EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCAD=X", "AUDUSD=X", "USDCHF=X",
                  "USDINR=X", "DX-Y.NYB"]),
    dict(key="crypto", label="Crypto", icon="currency-bitcoin",
         blurb="Bitcoin, Ether, Solana in dollars.",
         symbols=["BTC-USD", "ETH-USD", "SOL-USD"]),
]
PRESET_BY_KEY = {p["key"]: p for p in PRESETS}

# How much history to keep for a collected security, in days (None: the global setting).
KEEP_CHOICES = [(None, "The global setting"), (730, "2 years"), (1827, "5 years"),
                (3653, "10 years"), (7305, "20 years")]
KEEP_DAYS = {k for k, _ in KEEP_CHOICES if k}

# Yahoo's instrument types, as the page groups them - in this order.
CATEGORIES = [("INDEX", "Indices"), ("EQUITY", "Stocks"), ("ETF", "ETFs"),
              ("MUTUALFUND", "Mutual funds"), ("MONEYMARKET", "Money market"),
              ("FUTURE", "Futures"), ("CURRENCY", "Currencies"),
              ("CRYPTOCURRENCY", "Crypto"), ("", "Not yet fetched")]
CATEGORY_LABEL = dict(CATEGORIES)


def category(quote_type: str | None) -> str:
    qt = (quote_type or "").upper()
    return qt if qt in CATEGORY_LABEL else ""


def parse_symbols(text: str) -> list[str]:
    """Symbols from a pasted list: commas, spaces, semicolons or lines; each once."""
    out = []
    for raw in (text or "").replace(";", ",").replace("\n", ",").replace("\t", ",").split(","):
        for part in raw.split():
            sym = part.strip().upper()
            if sym and sym not in out:
                out.append(sym)
    return out


def keep_for(value) -> int | None:
    """A form's history choice as keep_days (None for the global setting)."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return None
    return v if v in KEEP_DAYS else None
