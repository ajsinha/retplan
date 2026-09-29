"""Trading calendars: which days a market is open, so a missing daily bar can be
told apart from a day the market was shut.

Five calendars cover what RetPlan collects:

- ``us``     - NYSE and Nasdaq (US stocks, ETFs, mutual funds, the US indices and
               yields, CME futures as an approximation): weekdays less the NYSE
               holidays, computed by rule, and the special closures.
- ``uk``     - the London Stock Exchange: weekdays less the bank holidays of England
               and Wales, including the one-off ones.
- ``fx``     - currency pairs: every weekday but 1 January and 25 December
               (currencies trade on national holidays, but not on those two).
- ``crypto`` - every day of the year.
- ``weekdays`` - any other exchange: every weekday. Its own holidays are not known,
               so a day missing on one of them is retried a few times and then
               recorded as a known gap - never an error.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

CALENDARS = {
    "us": "US markets (NYSE, Nasdaq)",
    "uk": "London Stock Exchange",
    "fx": "Currency markets (weekdays but 1 Jan and 25 Dec)",
    "crypto": "Every day",
    "weekdays": "Weekdays (holidays not known)",
}

# NYSE closures that no rule produces.
US_SPECIAL = {date(2001, 9, 11), date(2001, 9, 12), date(2001, 9, 13), date(2001, 9, 14),
              date(2004, 6, 11), date(2007, 1, 2), date(2012, 10, 29), date(2012, 10, 30),
              date(2018, 12, 5), date(2025, 1, 9)}
# UK bank holidays moved or added by proclamation.
UK_MOVED = {2002: {"spring": date(2002, 6, 4)}, 2012: {"spring": date(2012, 6, 4)},
            2020: {"early_may": date(2020, 5, 8)}, 2022: {"spring": date(2022, 6, 2)}}
UK_EXTRA = {date(2002, 6, 3), date(2011, 4, 29), date(2012, 6, 5), date(2022, 6, 3),
            date(2022, 9, 19), date(2023, 5, 8)}
US_INDICES = {"^GSPC", "^DJI", "^IXIC", "^NDX", "^RUT", "^VIX", "^NYA", "^XAX", "^OEX",
              "^TNX", "^IRX", "^TYX", "^FVX", "^SP400", "^SP600", "^W5000", "^SOX", "^DJT",
              "^DJU", "^MID", "DX-Y.NYB"}
UK_INDICES = {"^FTSE", "^FTMC", "^FTAS", "^FTLC"}
US_EXCHANGES = {"NMS", "NGM", "NCM", "NYQ", "PCX", "ASE", "BTS", "NIM", "OPR", "CBO",
                "CME", "CMX", "NYM", "CBT", "NAS", "NASDAQ", "NYSE", "NYSEARCA", "AMEX",
                "NASDAQGS", "NASDAQGM", "NASDAQCM", "NYSEAMERICAN", "CBOE", "BATS",
                "SNP", "DJI", "NEW YORK", "NEW YORK MERCANTILE", "COMEX", "CHICAGO"}


def easter(year: int) -> date:
    """Western Easter Sunday (the anonymous Gregorian algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def _nth_weekday(year, month, weekday, n):
    """The n-th given weekday (0 = Monday) of a month; n = -1 for the last."""
    if n > 0:
        d = date(year, month, 1)
        d += timedelta(days=(weekday - d.weekday()) % 7)
        return d + timedelta(weeks=n - 1)
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    d = nxt - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def _observed_us(d: date) -> date | None:
    """Saturday holidays are kept on the Friday, Sunday ones on the Monday."""
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


@lru_cache(maxsize=None)
def us_holidays(year: int) -> frozenset:
    """NYSE full-day closures in a year."""
    out = set()
    ny = date(year, 1, 1)
    if ny.weekday() == 6:
        out.add(ny + timedelta(days=1))
    elif ny.weekday() != 5:                 # a Saturday New Year's Day is not moved
        out.add(ny)
    if year >= 1998:
        out.add(_nth_weekday(year, 1, 0, 3))        # Martin Luther King Jr. Day
    out.add(_nth_weekday(year, 2, 0, 3))            # Washington's Birthday
    out.add(easter(year) - timedelta(days=2))       # Good Friday
    out.add(_nth_weekday(year, 5, 0, -1))           # Memorial Day
    if year >= 2022:
        out.add(_observed_us(date(year, 6, 19)))    # Juneteenth
    out.add(_observed_us(date(year, 7, 4)))         # Independence Day
    out.add(_nth_weekday(year, 9, 0, 1))            # Labor Day
    out.add(_nth_weekday(year, 11, 3, 4))           # Thanksgiving
    out.add(_observed_us(date(year, 12, 25)))       # Christmas
    # a Saturday New Year's Day of the next year closes nothing this year
    out |= {d for d in US_SPECIAL if d.year == year}
    return frozenset(d for d in out if d and d.year == year)


def _next_weekday(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


@lru_cache(maxsize=None)
def uk_holidays(year: int) -> frozenset:
    """Bank holidays in England and Wales, which close the London Stock Exchange."""
    moved = UK_MOVED.get(year, {})
    out = {_next_weekday(date(year, 1, 1)),
           easter(year) - timedelta(days=2),              # Good Friday
           easter(year) + timedelta(days=1),              # Easter Monday
           moved.get("early_may", _nth_weekday(year, 5, 0, 1)),
           moved.get("spring", _nth_weekday(year, 5, 0, -1)),
           _nth_weekday(year, 8, 0, -1)}                  # Summer bank holiday
    xmas, boxing = date(year, 12, 25), date(year, 12, 26)
    if xmas.weekday() == 5:                               # Saturday: Mon and Tue
        out |= {xmas + timedelta(days=2), xmas + timedelta(days=3)}
    elif xmas.weekday() == 6:                             # Sunday: Mon (Boxing) and Tue
        out |= {boxing, xmas + timedelta(days=2)}
    elif xmas.weekday() == 4:                             # Friday: Boxing Day moves to Mon
        out |= {xmas, xmas + timedelta(days=3)}
    else:
        out |= {xmas, boxing}
    out |= {d for d in UK_EXTRA if d.year == year}
    return frozenset(out)


def is_trading_day(cal: str, d: date) -> bool:
    if cal == "crypto":
        return True
    if d.weekday() >= 5:
        return False
    if cal == "us":
        return d not in us_holidays(d.year)
    if cal == "uk":
        return d not in uk_holidays(d.year)
    if cal == "fx":
        return (d.month, d.day) not in ((1, 1), (12, 25))
    return True                                           # weekdays


def trading_days(cal: str, start: date, end: date) -> list[date]:
    """Every trading day from ``start`` to ``end``, both included."""
    out, d = [], start
    while d <= end:
        if is_trading_day(cal, d):
            out.append(d)
        d += timedelta(days=1)
    return out


def last_complete_day(cal: str, today: date | None = None) -> date:
    """The latest trading day before ``today`` - whose bar must exist by now."""
    d = (today or date.today()) - timedelta(days=1)
    while not is_trading_day(cal, d):
        d -= timedelta(days=1)
    return d


def calendar_for(symbol: str, quote_type: str = "", exchange: str = "",
                 currency: str = "") -> str:
    """Which calendar a security trades on, from its symbol, type and exchange."""
    sym = (symbol or "").upper()
    qt = (quote_type or "").upper()
    ex = (exchange or "").upper().replace(" ", "")
    if qt == "CRYPTOCURRENCY" or sym.endswith(("-USD", "-EUR", "-GBP", "-USDT", "-BTC")):
        return "crypto"
    if qt == "CURRENCY" or sym.endswith("=X"):
        return "fx"
    if sym.endswith(".L") or sym.endswith(".IL") or sym in UK_INDICES or ex in ("LSE", "LONDON"):
        return "uk"
    if sym in US_INDICES or sym.endswith("=F"):
        return "us"
    if sym.startswith("^"):
        return "weekdays"
    if "." in sym and not sym.endswith((".A", ".B")):     # another exchange's suffix
        return "weekdays"
    if ex in {e.replace(" ", "") for e in US_EXCHANGES} or (currency or "").upper() == "USD" \
            or not currency:
        return "us"
    return "weekdays"
