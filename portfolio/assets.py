"""Asset classes: classification of a security and long-run assumptions.

Every holding belongs to one class. The class supplies the fallback return and
volatility when a security's own history is too short to say anything, the prior
its sample mean is shrunk towards, and the proxy used by the crisis replays. The
figures are deliberately round, conservative, long-run *nominal* assumptions of
the kind published in capital-market outlooks - a starting point the user can
override per holding, not a forecast.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

# key: (label, expected simple return, volatility, crisis proxy, icon)
CLASSES: dict[str, dict] = {
    "equity":      dict(label="Equity",          mu=0.070, sigma=0.170, proxy="equity",   icon="bi-graph-up"),
    "intl_equity": dict(label="Intl equity",     mu=0.070, sigma=0.180, proxy="equity",   icon="bi-globe2"),
    "em_equity":   dict(label="Emerging equity", mu=0.080, sigma=0.230, proxy="equity",   icon="bi-globe-americas"),
    "bond":        dict(label="Bonds",           mu=0.040, sigma=0.060, proxy="bond",     icon="bi-bank"),
    "cash":        dict(label="Cash",            mu=0.030, sigma=0.010, proxy="cash",     icon="bi-cash-coin"),
    "property":    dict(label="Property / REIT", mu=0.060, sigma=0.200, proxy="property", icon="bi-building"),
    "commodity":   dict(label="Commodities",     mu=0.040, sigma=0.180, proxy="commodity", icon="bi-gem"),
    "crypto":      dict(label="Crypto",          mu=0.080, sigma=0.700, proxy="equity",   icon="bi-currency-bitcoin"),
    "other":       dict(label="Other",           mu=0.050, sigma=0.150, proxy="equity",   icon="bi-question-circle"),
}

CLASS_OPTIONS = [(k, v["label"]) for k, v in CLASSES.items()]

# Long-run correlations between classes, used when two securities have too few
# overlapping days to estimate their own.
_CLASS_CORR = {
    ("equity", "intl_equity"): 0.80, ("equity", "em_equity"): 0.70,
    ("intl_equity", "em_equity"): 0.80, ("equity", "bond"): 0.10,
    ("intl_equity", "bond"): 0.10, ("em_equity", "bond"): 0.10,
    ("equity", "property"): 0.60, ("intl_equity", "property"): 0.55,
    ("em_equity", "property"): 0.50, ("bond", "property"): 0.20,
    ("equity", "commodity"): 0.30, ("intl_equity", "commodity"): 0.35,
    ("em_equity", "commodity"): 0.40, ("bond", "commodity"): 0.00,
    ("equity", "crypto"): 0.35, ("intl_equity", "crypto"): 0.30,
    ("em_equity", "crypto"): 0.30, ("bond", "crypto"): 0.05,
    ("property", "commodity"): 0.25, ("property", "crypto"): 0.25,
    ("commodity", "crypto"): 0.20,
}

CASH_SYMBOL = "CASH"


def class_corr(a: str, b: str) -> float:
    if a == b:
        return 0.90 if a != "cash" else 1.0
    if "cash" in (a, b):
        return 0.0
    if "other" in (a, b):
        return 0.50
    return _CLASS_CORR.get((a, b), _CLASS_CORR.get((b, a), 0.30))


def classify(symbol: str, name: str = "", quote_type: str = "") -> str:
    """A best guess from Yahoo's instrument type and the fund's name.

    Wrong guesses are cheap - the class is editable on every holding - but a good
    first guess is what makes entering a portfolio take a minute, not ten.
    """
    s, n, q = symbol.upper(), (name or "").lower(), (quote_type or "").upper()
    if s == CASH_SYMBOL or q == "MONEYMARKET" or "money market" in n:
        return "cash"
    if q == "CRYPTOCURRENCY" or s.endswith("-USD") and q != "CURRENCY":
        return "crypto"
    if q in ("FUTURE",) or any(w in n for w in ("gold", "silver", "commodity",
                                                  "oil fund", "precious metal")):
        return "commodity"
    bondish = ("bond", "treasury", "treasuries", "fixed income", "aggregate",
               "municipal", "t-bill", "tips", "income fund", "credit",
               "govt", "government", "corporate", "high yield", "duration")
    if any(w in n for w in bondish) and "equity" not in n:
        return "bond"
    if any(w in n for w in ("reit", "real estate", "property", "properties")):
        return "property"
    if any(w in n for w in ("emerging", "em markets")):
        return "em_equity"
    intl = ("international", "intl", "ex-us", "ex us", "world ex", "developed",
            "europe", "pacific", "foreign", "eafe", "global ex", "total intl")
    if any(w in n for w in intl):
        return "intl_equity"
    if q in ("EQUITY", "ETF", "MUTUALFUND", "INDEX"):
        return "equity"
    return "other"
