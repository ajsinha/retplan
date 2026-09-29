"""The portfolio builder: a spreadsheet of positions in, a reviewed portfolio out.

Broker and bank exports are messy in predictable ways, and each is handled:

- **Where the table is.** A preamble (account holder, dates, disclaimers) sits
  above the header; the header row is found by scoring each of the first rows
  against a vocabulary of column names. Every sheet of a workbook is read.
- **What each column is.** Headers are matched to roles - symbol, name, ISIN /
  CUSIP / SEDOL, quantity, price, market value, cost (total or per share),
  account, asset class, currency - by vocabulary; a symbol column is also
  recognised from its content when the header says nothing useful.
- **Rows that are not positions.** Totals, subtotals, blank lines and section
  headings are skipped; cash, sweep and money-market lines become CASH.
- **Missing numbers.** No quantity but a value and a price: quantity =
  value / price. A cost column is read as per-share or total by comparing its
  size with the price and the value.
- **Which security it is.** In order of reliability: the symbol as written
  (cleaned of "NASDAQ:", " US Equity", "(AAPL)" wrappers), then an ISIN or other
  identifier looked up on Yahoo, then the name searched on Yahoo and matched by
  similarity. Each line carries a confidence and the alternatives considered.
- **Sanity.** When the file states a value, it is compared with Yahoo's price
  times the quantity; a large gap (another share class, a pence/pound mix-up, a
  wrong match) is flagged for review.
- **Duplicates.** The same security in the same account is merged.

Nothing is saved until the review screen is confirmed.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import csv
import difflib
import io
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field

from . import yahoo
from .assets import CASH_SYMBOL, CLASSES, classify
from .fx import major

logger = logging.getLogger(__name__)

MAX_ROWS = 2000
HEADER_SCAN = 40
LOOKUP_THREADS = 6

ROLE_WORDS: dict[str, tuple[str, ...]] = {
    "symbol": ("symbol", "ticker", "ticker symbol", "stock symbol", "code", "epic",
               "instrument code", "security id", "sym"),
    "isin": ("isin", "cusip", "sedol", "identifier", "security identifier", "figi",
             "wkn", "valor"),
    "name": ("name", "description", "security", "security name", "investment",
             "holding", "instrument", "fund name", "asset", "security description",
             "investment name", "product"),
    "quantity": ("quantity", "qty", "shares", "units", "share quantity", "no. of shares",
                 "number of shares", "position", "holding quantity", "nominal",
                 "quantity held", "shares held", "units held"),
    "price": ("price", "last price", "current price", "market price", "close",
              "closing price", "unit price", "share price", "last", "nav"),
    "value": ("market value", "value", "current value", "market val", "total value",
              "valuation", "amount", "balance", "position value", "mkt value",
              "value (usd)", "ending value", "total market value"),
    "cost_total": ("cost basis", "total cost", "book cost", "book value", "cost",
                   "cost basis total", "purchase value", "invested", "cost value",
                   "total cost basis", "amount invested"),
    "cost_unit": ("average cost", "avg cost", "unit cost", "cost per share",
                  "average price", "avg price", "purchase price", "cost/share",
                  "avg. cost", "average unit cost", "price paid"),
    "account": ("account", "account name", "account number", "account type",
                "portfolio", "wrapper", "account no", "acct"),
    "asset_class": ("asset class", "class", "asset type", "type", "security type",
                    "category", "sector"),
    "currency": ("currency", "ccy", "cur", "trading currency", "price currency"),
}
SKIP_ROW = re.compile(r"^\s*(sub\s*-?\s*)?totals?\b|^\s*grand total|^\s*account total"
                      r"|^\s*total (market )?value|^\s*net assets", re.I)
CASH_WORDS = re.compile(r"\b(cash|money market|sweep|core position|settlement fund|"
                        r"deposit|cash balance|uninvested|pending activity|fdrxx|spaxx|"
                        r"vmfxx|swvxx)\b", re.I)
TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-^=]{0,14}$")
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
CUSIP_RE = re.compile(r"^[0-9A-Z]{8}[0-9]$")
CLASS_HINTS = [("bond", "bond"), ("fixed income", "bond"), ("treasur", "bond"),
               ("cash", "cash"), ("money market", "cash"), ("real estate", "property"),
               ("reit", "property"), ("property", "property"), ("commodit", "commodity"),
               ("gold", "commodity"), ("crypto", "crypto"), ("emerging", "em_equity"),
               ("international", "intl_equity"), ("foreign", "intl_equity"),
               ("equit", "equity"), ("stock", "equity"), ("share", "equity")]


# --------------------------------------------------------------------------- #
# reading
# --------------------------------------------------------------------------- #
def read_sheets(content: bytes, filename: str) -> list[tuple[str, list[list]]]:
    """[(sheet name, rows of cell values)] from an .xlsx/.xlsm or a .csv/.txt."""
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")) or content[:2] == b"PK":
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        out = []
        for ws in wb.worksheets:
            rows = []
            for row in ws.iter_rows(values_only=True):
                rows.append(list(row))
                if len(rows) > MAX_ROWS + HEADER_SCAN:
                    break
            out.append((ws.title, rows))
        wb.close()
        return out
    if name.endswith(".xls"):
        raise ValueError("old-style .xls files are not supported; open it and "
                         "'Save as' .xlsx or .csv")
    text = content.decode("utf-8-sig", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text[:4000], delimiters=",;\t|")
        delim = dialect.delimiter
    except csv.Error:
        delim = ","
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim)]
    return [(filename or "file", rows[:MAX_ROWS + HEADER_SCAN])]


# --------------------------------------------------------------------------- #
# understanding the table
# --------------------------------------------------------------------------- #
def _norm(h) -> str:
    return re.sub(r"[\s_]+", " ", str(h or "").strip().lower()).strip(" :*#")


def _role_for(header: str) -> tuple[str | None, int]:
    """Best role for a header text, with a score (2 exact, 1 contains)."""
    h = _norm(header)
    if not h:
        return None, 0
    h2 = re.sub(r"\(.*?\)", "", h).strip()      # "market value (usd)" -> "market value"
    for cand in (h, h2):
        for role, words in ROLE_WORDS.items():
            if cand in words:
                return role, 2
    best, best_len = None, 0
    for role, words in ROLE_WORDS.items():
        for w in words:
            if len(w) >= 3 and re.search(r"\b" + re.escape(w) + r"\b", h) and len(w) > best_len:
                best, best_len = role, len(w)
    return (best, 1) if best else (None, 0)


def find_header(rows: list[list]) -> tuple[int | None, dict[str, int]]:
    """Index of the header row and {role: column}. None when nothing looks like one."""
    best_i, best_score, best_map = None, 0, {}
    for i, row in enumerate(rows[:HEADER_SCAN]):
        texts = [c for c in row if isinstance(c, str) and c.strip()]
        if len(texts) < 2:
            continue
        roles, score = {}, 0
        for j, cell in enumerate(row):
            if not isinstance(cell, str):
                continue
            role, s = _role_for(cell)
            if role and role not in roles:
                roles[role] = j
                score += s
        # a header must name something that identifies a security and an amount
        ident = any(r in roles for r in ("symbol", "isin", "name"))
        amount = any(r in roles for r in ("quantity", "value"))
        if ident and amount and score > best_score:
            best_i, best_score, best_map = i, score, roles
    return best_i, best_map


def _num(v):
    """A number from a cell: 1,234.50 / $1,234 / (123.4) / 12.5% / '-' -> value."""
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip()
    if t in ("", "-", "--", "n/a", "N/A", "NA"):
        return None
    neg = t.startswith("(") and t.endswith(")")
    t = re.sub(r"[^\d.\-eE]", "", t.replace(",", ""))
    try:
        x = float(t)
    except ValueError:
        return None
    return -abs(x) if neg else x


def _text(v) -> str:
    return "" if v is None else str(v).strip()


def clean_symbol(raw: str) -> str:
    """'NASDAQ:AAPL' / 'AAPL US Equity' / 'aapl ' / 'BRK/B' -> a Yahoo-style symbol."""
    s = _text(raw).upper()
    s = re.sub(r"\s+(US|LN|CN|GR|FP|JP|AU)\s+EQUITY$", "", s)
    s = re.sub(r"\s+EQUITY$", "", s)
    if ":" in s:
        s = s.split(":")[-1]
    s = s.replace("/", "-").replace(" ", "")
    if s.endswith("*"):
        s = s[:-1]
    return s


def symbol_in_name(name: str) -> str:
    """'Apple Inc (AAPL)' -> 'AAPL'."""
    m = re.search(r"\(([A-Z][A-Z0-9.\-]{0,9})\)\s*$", _text(name))
    return m.group(1) if m else ""


@dataclass
class Line:
    """One proposed holding."""
    sheet: str
    row: int
    raw_symbol: str = ""
    raw_name: str = ""
    raw_id: str = ""
    quantity: float | None = None
    price: float | None = None           # from the file
    value: float | None = None           # from the file
    cost: float | None = None            # total
    account: str = ""
    asset_class: str = ""
    currency: str = ""
    symbol: str = ""                     # resolved
    name: str = ""                       # resolved
    quote_type: str = ""
    yahoo_price: float | None = None
    yahoo_currency: str = ""
    confidence: str = "none"             # high | medium | low | none | cash
    how: str = ""
    notes: list = field(default_factory=list)
    alternatives: list = field(default_factory=list)
    include: bool = True
    merged: int = 1


def extract(sheets) -> tuple[list[Line], list[str]]:
    """Proposed lines from every sheet that has a positions table, and messages
    about what was found (or not)."""
    lines, msgs = [], []
    tables = []
    for title, rows in sheets:
        hi, roles = find_header(rows)
        if hi is None:
            # no header: a symbol-like first column and a number beside it
            if rows and _looks_headerless(rows):
                roles = {"symbol": 0, "quantity": 1}
                if any(len(r) > 2 and _num(r[2]) is not None for r in rows[:10]):
                    roles["cost_total"] = 2
                tables.append((title, -1, roles, rows))
                msgs.append(f"“{title}”: no header row; read as symbol, quantity"
                            + (", cost" if "cost_total" in roles else "") + ".")
            else:
                msgs.append(f"“{title}”: no table of positions found - skipped.")
            continue
        tables.append((title, hi, roles, rows))
        named = ", ".join(f"{r.replace('_', ' ')} = “{_text(rows[hi][c])}”"
                          for r, c in sorted(roles.items(), key=lambda x: x[1]))
        msgs.append(f"“{title}”: header on row {hi + 1}; {named}.")
    multi = len(tables) > 1
    for title, hi, roles, rows in tables:
        blank_run = 0
        for i in range(hi + 1, len(rows)):
            row = rows[i]
            cell = lambda role: row[roles[role]] if role in roles and roles[role] < len(row) else None  # noqa: E731
            first_text = next((_text(c) for c in row if _text(c)), "")
            if not first_text:
                blank_run += 1
                if blank_run >= 3 and len(lines) > 0:
                    break
                continue
            blank_run = 0
            if SKIP_ROW.search(first_text) or SKIP_ROW.search(_text(cell("name"))) \
                    or SKIP_ROW.search(_text(cell("symbol"))):
                continue
            ln = Line(sheet=title, row=i + 1, raw_symbol=_text(cell("symbol")),
                      raw_name=_text(cell("name")), raw_id=_text(cell("isin")).upper(),
                      quantity=_num(cell("quantity")), price=_num(cell("price")),
                      value=_num(cell("value")), account=_text(cell("account")),
                      currency=_text(cell("currency")).upper()[:3])
            if not (ln.raw_symbol or ln.raw_name or ln.raw_id):
                continue
            if ln.quantity is None and ln.value is None:
                continue                  # a heading or a note, not a position
            if not ln.account and multi:
                ln.account = title
            # an identifier sitting in the symbol column
            if not ln.raw_id and ISIN_RE.match(ln.raw_symbol.upper()):
                ln.raw_id, ln.raw_symbol = ln.raw_symbol.upper(), ""
            cls_text = _text(cell("asset_class")).lower()
            for word, key in CLASS_HINTS:
                if word in cls_text:
                    ln.asset_class = key
                    break
            _costs(ln, _num(cell("cost_total")), _num(cell("cost_unit")))
            if ln.quantity is None and ln.value is not None and ln.price:
                ln.quantity = ln.value / ln.price
                ln.notes.append("quantity worked out as value ÷ price")
            lines.append(ln)
            if len(lines) >= MAX_ROWS:
                msgs.append(f"Stopped after {MAX_ROWS} positions.")
                return lines, msgs
    return lines, msgs


def _looks_headerless(rows) -> bool:
    sample = [r for r in rows[:15] if r and _text(r[0])]
    if len(sample) < 1:
        return False
    ok = sum(1 for r in sample if TICKER_RE.match(clean_symbol(r[0]))
             and len(r) > 1 and _num(r[1]) is not None)
    return ok >= max(1, int(0.7 * len(sample)))


def _costs(ln: Line, total, unit) -> None:
    """Decide what the cost numbers mean and store a total cost."""
    if total is not None and total <= 0:
        total = None
    if unit is not None and unit <= 0:
        unit = None
    q = ln.quantity
    if total is not None and unit is None and q:
        # A column called "cost" is sometimes per share. Sized like the whole
        # position, it is a total; sized like one share (and not like the whole
        # position), it is per share; anything else is taken at its word.
        ref_value = ln.value or ((ln.price * q) if ln.price else None)
        ref_unit = ln.price or ((ln.value / q) if ln.value else None)
        if ref_value and 0.2 <= total / ref_value <= 5:
            ln.cost = total
        elif ref_unit and 0.2 <= total / ref_unit <= 5 and abs(q) > 1.5:
            ln.cost = total * q
            ln.notes.append("cost read as per share")
        else:
            ln.cost = total
        return
    elif unit is not None and q:
        ln.cost = unit * q
    elif total is not None:
        ln.cost = total


# --------------------------------------------------------------------------- #
# resolving securities
# --------------------------------------------------------------------------- #
class Resolver:
    """Symbol -> quote, name/ISIN -> candidates; cached, thread-safe enough (dict
    writes are atomic) for a small pool."""

    def __init__(self, fetch=yahoo.fetch_history, search=yahoo.search):
        self._fetch, self._search = fetch, search
        self.quotes: dict[str, object] = {}
        self.searches: dict[str, list] = {}

    def quote(self, sym: str):
        if sym not in self.quotes:
            try:
                self.quotes[sym] = self._fetch(sym, range_="5d")
            except Exception as exc:  # noqa: BLE001 - absence is an answer
                logger.info("builder: %s not found (%s)", sym, exc)
                self.quotes[sym] = None
        return self.quotes[sym]

    def find(self, q: str) -> list:
        key = q.lower().strip()
        if key not in self.searches:
            try:
                self.searches[key] = self._search(q, limit=6)
            except Exception as exc:  # noqa: BLE001
                logger.info("builder: search %r failed (%s)", q, exc)
                self.searches[key] = []
        return self.searches[key]


def _similar(a: str, b: str) -> float:
    words = lambda s: re.sub(r"\b(inc|corp|corporation|plc|ltd|limited|co|class|cl|the|"  # noqa: E731
                             r"shares|share|ord|ordinary|etf|fund|adr|sa|ag|nv)\b|[^a-z0-9 ]",
                             " ", s.lower()).split()
    wa, wb = " ".join(words(a)), " ".join(words(b))
    if not wa or not wb:
        return 0.0
    return difflib.SequenceMatcher(None, wa, wb).ratio()


def resolve(lines: list[Line], resolver: Resolver | None = None) -> None:
    """Fill symbol, name, confidence and alternatives on every line, in parallel."""
    resolver = resolver or Resolver()
    with ThreadPoolExecutor(max_workers=LOOKUP_THREADS) as pool:
        list(pool.map(lambda ln: _resolve_one(ln, resolver), lines))


def _resolve_one(ln: Line, r: Resolver) -> None:
    text = f"{ln.raw_symbol} {ln.raw_name}"
    if CASH_WORDS.search(text) or ln.raw_symbol.upper() in ("CASH", "$", "USD", "CASH$"):
        ln.symbol, ln.name, ln.confidence, ln.how = CASH_SYMBOL, "Cash", "cash", "cash line"
        amount = ln.value if ln.value is not None else ln.quantity
        ln.quantity = amount
        ln.cost = amount
        ln.asset_class = "cash"
        return
    tried = []
    for cand, how in ((clean_symbol(ln.raw_symbol), "symbol as written"),
                      (symbol_in_name(ln.raw_name), "symbol in the name")):
        if cand and TICKER_RE.match(cand) and cand not in tried:
            tried.append(cand)
            h = r.quote(cand)
            if h is not None:
                _accept(ln, cand, h, "high", how)
                if ln.raw_name and h.name and _similar(ln.raw_name, h.name) < 0.35:
                    ln.confidence = "medium"
                    ln.notes.append(f"the file calls it “{ln.raw_name}”; Yahoo calls "
                                    f"{cand} “{h.name}”")
                _check_value(ln)
                return
    # identifier, then name
    for query, how, conf in ((ln.raw_id, "identifier", "high"),
                             (ln.raw_name, "name search", None)):
        if not query:
            continue
        found = [c for c in r.find(query) if c.get("symbol")]
        if not found:
            continue
        ln.alternatives = [dict(symbol=c["symbol"], name=c.get("name", ""),
                                type=c.get("type", ""), exchange=c.get("exchange", ""))
                           for c in found[:5]]
        if how == "name search":
            scored = sorted(((_similar(query, c.get("name") or ""), c) for c in found),
                            key=lambda x: -x[0])
            best_score, best = scored[0]
            conf = "medium" if best_score >= 0.75 else "low"
        else:
            best = found[0]
        h = r.quote(best["symbol"])
        if h is None:
            continue
        _accept(ln, best["symbol"], h, conf, how)
        _check_value(ln)
        return
    ln.confidence, ln.how = "none", "not found"
    ln.include = False
    ln.notes.append("no match on Yahoo - type the symbol, or add it as a manual security")
    if tried:
        ln.symbol = tried[0]


def _accept(ln: Line, sym: str, h, confidence: str, how: str) -> None:
    ln.symbol, ln.name, ln.quote_type = sym, h.name or ln.raw_name, h.quote_type
    ln.yahoo_price, ln.yahoo_currency = h.price, h.currency
    ln.confidence, ln.how = confidence, how
    if not ln.asset_class:
        ln.asset_class = classify(sym, h.name, h.quote_type)
    if not ln.alternatives:
        ln.alternatives = [dict(symbol=sym, name=h.name or "", type=h.quote_type,
                                exchange=h.exchange)]
    if ln.quantity is None and ln.value and h.price:
        cur, scale = major(h.currency)
        ln.quantity = ln.value / (h.price * scale)
        ln.notes.append("quantity worked out from the value and Yahoo's price")


def _check_value(ln: Line) -> None:
    """Flag a match whose price disagrees badly with what the file says."""
    if ln.yahoo_price is None or not ln.quantity:
        return
    _, scale = major(ln.yahoo_currency)
    mine = None
    if ln.price:
        ratio = ln.price / (ln.yahoo_price * scale) if ln.yahoo_price else None
        what = "price"
    elif ln.value:
        ratio = ln.value / (ln.quantity * ln.yahoo_price * scale) if ln.yahoo_price else None
        what = "value"
    else:
        return
    if ratio is None:
        return
    if 0.75 <= ratio <= 1.33:
        return
    if 80 <= ratio <= 125 or 0.008 <= ratio <= 0.0125:
        ln.notes.append(f"the file's {what} is about 100× Yahoo's - pence versus pounds, "
                        "or cents versus dollars?")
    else:
        ln.notes.append(f"the file's {what} is {ratio:.2f}× what Yahoo implies - check it "
                        "is the same security and share class")
    if ln.confidence == "high":
        ln.confidence = "medium"
    elif ln.confidence == "medium":
        ln.confidence = "low"


def merge(lines: list[Line]) -> list[Line]:
    """One line per (symbol, account); quantities, values and costs add up."""
    out: dict[tuple, Line] = {}
    order = []
    for ln in lines:
        if not ln.symbol:
            order.append(ln)
            continue
        key = (ln.symbol, ln.account)
        if key not in out:
            out[key] = ln
            order.append(ln)
            continue
        m = out[key]
        m.quantity = (m.quantity or 0) + (ln.quantity or 0)
        m.value = (m.value or 0) + (ln.value or 0) if (m.value or ln.value) else None
        m.cost = (m.cost or 0) + (ln.cost or 0) if (m.cost is not None or ln.cost is not None) else None
        m.merged += 1
        m.notes = list(dict.fromkeys(m.notes + ln.notes))
    return order


def analyse(content: bytes, filename: str, resolver: Resolver | None = None) -> dict:
    """The whole pipeline, returning a JSON-able draft for the review screen."""
    sheets = read_sheets(content, filename)
    lines, msgs = extract(sheets)
    if not lines:
        return dict(filename=filename, lines=[], messages=msgs + [
            "No positions were recognised. The sheet needs a column that names the "
            "security (symbol, ISIN or name) and one with a quantity or a value."])
    resolve(lines, resolver)
    lines = merge(lines)
    currencies = sorted({ln.currency for ln in lines if ln.currency} |
                        {major(ln.yahoo_currency)[0] for ln in lines if ln.yahoo_currency})
    counts = {k: sum(1 for ln in lines if ln.confidence == k)
              for k in ("high", "medium", "low", "none", "cash")}
    return dict(filename=filename, lines=[asdict(ln) for ln in lines], messages=msgs,
                counts=counts, currencies=currencies,
                file_value=sum(ln.value for ln in lines if ln.value) or None)


def guess_currency(draft: dict) -> str:
    cur = [c for c in draft.get("currencies", []) if c]
    return cur[0] if len(cur) == 1 else ("USD" if "USD" in cur or not cur else cur[0])


def classes() -> list[tuple[str, str]]:
    return [(k, v["label"]) for k, v in CLASSES.items()]
