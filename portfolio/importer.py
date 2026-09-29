"""Holdings from pasted text or a CSV file.

People keep holdings in a broker's export or a spreadsheet, so the fastest way to
build a portfolio is to paste it. Accepted: comma, semicolon or tab separated;
with or without a header row. With a header, columns are recognised by name
(symbol/ticker, quantity/shares/units, cost/book value, account, class); without
one, the order is ``symbol, quantity[, cost basis][, account][, asset class]``.

Parsing is separate from saving so the page can show a preview first.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from .assets import CLASSES

ALIASES = {
    "symbol": ("symbol", "ticker", "code", "security", "instrument"),
    "quantity": ("quantity", "qty", "shares", "units", "amount held", "holding"),
    "cost_basis": ("cost basis", "cost", "book value", "book cost", "total cost",
                   "cost_basis", "basis"),
    "account": ("account", "account name", "wrapper", "portfolio"),
    "asset_class": ("asset class", "class", "asset_class", "type"),
}
CLASS_WORDS = {v["label"].lower(): k for k, v in CLASSES.items()} | {k: k for k in CLASSES}


@dataclass
class Row:
    line: int
    symbol: str
    quantity: float | None
    cost_basis: float | None = None
    account: str = ""
    asset_class: str = ""
    error: str = ""


def _num(text):
    t = (text or "").strip().replace(",", "").replace("$", "").replace("£", "") \
        .replace("€", "").replace(" ", "")
    if t in ("", "-"):
        return None
    if t.startswith("(") and t.endswith(")"):
        t = "-" + t[1:-1]
    return float(t)


def parse(text: str) -> list[Row]:
    text = (text or "").strip()
    if not text:
        return []
    sample = text[:2000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        delim = dialect.delimiter
    except csv.Error:
        delim = "\t" if "\t" in sample else ("," if "," in sample else ";")
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    rows = [[c.strip() for c in r] for r in rows if any(c.strip() for c in r)]
    if not rows:
        return []
    cols = None
    head = [c.lower() for c in rows[0]]
    if any(a in h for h in head for a in ALIASES["symbol"]) and not _looks_numeric(rows[0]):
        cols = {}
        taken = set()
        # exact names first, then any header containing an alias ("Ticker Symbol",
        # "Qty held"); a column is used for one field only
        for exact in (True, False):
            for key, names in ALIASES.items():
                if key in cols:
                    continue
                for i, h in enumerate(head):
                    if i in taken:
                        continue
                    if (h in names) if exact else any(n in h for n in names):
                        cols[key] = i
                        taken.add(i)
                        break
        rows_iter = list(enumerate(rows[1:], start=2))
    else:
        rows_iter = list(enumerate(rows, start=1))
    order = ["symbol", "quantity", "cost_basis", "account", "asset_class"]
    out = []
    for line, r in rows_iter:
        def get(key):
            if cols is not None:
                i = cols.get(key)
            else:
                i = order.index(key)
            return r[i] if i is not None and i < len(r) else ""
        sym = get("symbol").upper()
        row = Row(line=line, symbol=sym, quantity=None)
        try:
            row.quantity = _num(get("quantity"))
            row.cost_basis = _num(get("cost_basis"))
        except ValueError:
            row.error = "a number could not be read"
        row.account = get("account")
        cls = get("asset_class").strip().lower()
        row.asset_class = CLASS_WORDS.get(cls, "")
        if not sym:
            row.error = row.error or "no symbol"
        elif row.quantity is None:
            row.error = row.error or "no quantity"
        out.append(row)
    return out


def _looks_numeric(cells) -> bool:
    for c in cells[1:2]:
        try:
            _num(c)
            return True
        except ValueError:
            return False
    return False
