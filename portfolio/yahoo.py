"""A small Yahoo Finance client on the standard library.

Two public endpoints do everything RetPlan needs:

    /v8/finance/chart/<symbol>   daily or monthly bars, adjusted closes, events
    /v1/finance/search           symbol lookup for the ticker autocomplete

``yfinance`` would add pandas and a dozen transitive dependencies for the same
two calls, so this talks to the endpoints directly. The responses are
unofficial and can change; every parser here is defensive, and a failure for
one symbol is reported for that symbol rather than aborting a whole run.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import json
import logging
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"
# A bare product token. A full browser string is answered with 429, presumably
# because it claims a browser that then arrives without any browser cookies.
USER_AGENT = "Mozilla/5.0"
TIMEOUT = 20


class YahooError(RuntimeError):
    """The symbol could not be fetched (unknown, delisted, throttled, offline)."""


@dataclass
class Bar:
    date: str            # ISO date in the exchange's own time zone
    close: float
    adj_close: float
    volume: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None


@dataclass
class History:
    symbol: str
    name: str = ""
    quote_type: str = ""
    currency: str = ""
    exchange: str = ""
    price: float | None = None
    prev_close: float | None = None
    bars: list[Bar] = field(default_factory=list)
    dividends: list[tuple[str, float]] = field(default_factory=list)


def _get_json(url: str, retries: int = 2) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/json"})
    last = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # 404 carries a JSON body saying why; anything else may be transient.
            if exc.code == 404:
                try:
                    return json.loads(exc.read().decode("utf-8"))
                except ValueError:
                    raise YahooError("not found") from exc
            last = exc
            if exc.code == 429 and attempt < retries:
                time.sleep(5.0 * (attempt + 1))       # throttled: back off harder
                continue
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            last = exc
        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))
    raise YahooError(f"request failed: {last}")


def _iso(ts: int, gmtoffset: int) -> str:
    return datetime.fromtimestamp(ts + gmtoffset, tz=timezone.utc).date().isoformat()


def fetch_history(symbol: str, range_: str = "1y", interval: str = "1d") -> History:
    """Bars for one symbol. ``range_`` is Yahoo's: 5d, 1mo, 1y, 5y, 10y, max."""
    params = urllib.parse.urlencode({"range": range_, "interval": interval,
                                     "events": "div,splits",
                                     "includeAdjustedClose": "true"})
    url = CHART_URL.format(symbol=urllib.parse.quote(symbol)) + "?" + params
    data = _get_json(url)
    chart = data.get("chart") or {}
    if chart.get("error"):
        raise YahooError(chart["error"].get("description") or "unknown symbol")
    results = chart.get("result") or []
    if not results:
        raise YahooError("no data returned")
    r = results[0]
    meta = r.get("meta") or {}
    h = History(symbol=symbol.upper(),
                name=meta.get("longName") or meta.get("shortName") or "",
                quote_type=meta.get("instrumentType") or "",
                currency=meta.get("currency") or "",
                exchange=meta.get("fullExchangeName") or meta.get("exchangeName") or "",
                price=_num(meta.get("regularMarketPrice")),
                prev_close=_num(meta.get("chartPreviousClose")
                                or meta.get("previousClose")))
    offset = int(meta.get("gmtoffset") or 0)
    stamps = r.get("timestamp") or []
    ind = r.get("indicators") or {}
    quote = (ind.get("quote") or [{}])[0]
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    opens, highs, lows = (quote.get(k) or [] for k in ("open", "high", "low"))
    adj = ((ind.get("adjclose") or [{}])[0]).get("adjclose") or closes
    seen = {}
    for i, ts in enumerate(stamps):
        c = _num(closes[i] if i < len(closes) else None)
        a = _num(adj[i] if i < len(adj) else None)
        if c is None or c <= 0:
            continue                      # a halted or not-yet-closed session
        if a is None or a <= 0:
            a = c
        v = _num(volumes[i] if i < len(volumes) else None)

        def at(xs):
            x = _num(xs[i] if i < len(xs) else None)
            return x if x is not None and x > 0 else None
        # The live session can repeat the last date; the latest bar wins.
        seen[_iso(ts, offset)] = Bar(_iso(ts, offset), c, a, v, at(opens), at(highs), at(lows))
    h.bars = [seen[k] for k in sorted(seen)]
    for ev in ((r.get("events") or {}).get("dividends") or {}).values():
        amt = _num(ev.get("amount"))
        if amt and ev.get("date"):
            h.dividends.append((_iso(int(ev["date"]), offset), amt))
    h.dividends.sort()
    if not h.bars:
        raise YahooError("no priced sessions in range")
    return h


def search(query: str, limit: int = 8) -> list[dict]:
    """Ticker autocomplete: symbols, names and types matching ``query``."""
    query = (query or "").strip()
    if not query:
        return []
    params = urllib.parse.urlencode({"q": query, "quotesCount": limit,
                                     "newsCount": 0, "listsCount": 0,
                                     "enableFuzzyQuery": "false"})
    data = _get_json(f"{SEARCH_URL}?{params}", retries=1)
    out = []
    for q in data.get("quotes") or []:
        sym = q.get("symbol")
        if not sym:
            continue
        out.append({"symbol": sym,
                    "name": q.get("longname") or q.get("shortname") or "",
                    "type": q.get("quoteType") or q.get("typeDisp") or "",
                    "exchange": q.get("exchDisp") or q.get("exchange") or ""})
    return out[:limit]


def long_run_stats(symbol: str) -> dict | None:
    """Annualised return and volatility from up to 20 years of monthly bars.

    Used to calibrate the projection, then thrown away: only the three numbers
    are stored, never the monthly series, so price retention stays at a year.
    """
    try:
        h = fetch_history(symbol, range_="20y", interval="1mo")
    except YahooError as exc:
        logger.info("long-run stats for %s unavailable: %s", symbol, exc)
        return None
    px = [b.adj_close for b in h.bars]
    if len(px) < 25:
        return None
    rets = [math.log(px[i] / px[i - 1]) for i in range(1, len(px)) if px[i - 1] > 0]
    n = len(rets)
    mean = sum(rets) / n
    var = sum((x - mean) ** 2 for x in rets) / (n - 1)
    sigma = math.sqrt(var * 12)
    # log-mean -> arithmetic simple return: exp(mu_log + s^2/2) - 1
    arith = math.exp(mean * 12 + 0.5 * sigma ** 2) - 1
    return {"lt_return": arith, "lt_vol": sigma, "lt_years": n / 12.0}


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None
