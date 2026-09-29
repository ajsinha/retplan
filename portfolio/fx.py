"""Currency conversion for portfolios holding securities quoted in other currencies.

Yahoo quotes every symbol in its listing currency, sometimes in minor units (a
London share in pence, "GBp"). A portfolio has one base currency; a holding in
another is converted with Yahoo's ``<FROM><TO>=X`` pair, which the collector
prices alongside the securities. Price series are converted day by day, so a
projection sees currency risk as part of each holding's volatility.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

# Minor-unit quotes: Yahoo's code -> (major currency, multiplier to major)
MINOR = {"GBp": ("GBP", 0.01), "GBX": ("GBP", 0.01), "ZAc": ("ZAR", 0.01),
         "ILA": ("ILS", 0.01), "KWF": ("KWD", 0.001)}


def major(currency: str) -> tuple[str, float]:
    """('GBp') -> ('GBP', 0.01); ('usd') -> ('USD', 1.0)."""
    if not currency:
        return "", 1.0
    if currency in MINOR:
        return MINOR[currency]
    return currency.upper(), 1.0


def pair(currency: str, base: str) -> tuple[str | None, float]:
    """The FX symbol that converts ``currency`` into ``base``, and the minor-unit
    scale. No pair is needed (None) when the currencies match or are unknown."""
    cur, scale = major(currency)
    base = (base or "").upper()
    if not cur or not base or cur == base:
        return None, scale
    return f"{cur}{base}=X", scale


def is_fx(symbol: str) -> bool:
    return symbol.endswith("=X")
