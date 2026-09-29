"""Portfolio, holding, security and price persistence.

Everything the web layer reads or writes about portfolios goes through
:class:`PortfolioRepo`, so SQL lives in one module and every query that touches a
portfolio is scoped by its owner - one workspace can never read another's
portfolios, accounts or holdings.

A portfolio is a collection of accounts (portfolio/account_types.py). Investment
accounts hold positions; cash, property and debt accounts carry a value set by
hand, and a debt pays itself down from the day it was set. The valuation covers
all of it: investable assets (positions, plus cash accounts as cash), property,
debts and net worth. Securities and prices are deliberately shared (a price is
a fact about a symbol); the pages only show a workspace the symbols it holds.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from . import account_types as at
from .assets import CASH_SYMBOL, CLASSES, classify
from .fx import is_fx, pair
from .db import PRICE_RETENTION_DAYS, Database, utcnow

logger = logging.getLogger(__name__)


class NotFound(LookupError):
    pass


@dataclass
class Position:
    """A holding joined with its security and latest price."""
    id: int
    symbol: str
    name: str
    quantity: float
    cost_basis: float | None
    account: str                    # the account's name
    asset_class: str
    notes: str
    price: float | None
    prev_close: float | None
    price_date: str | None
    currency: str
    fetch_error: str | None
    class_inherited: bool = False
    fx: float = 1.0                 # local price -> portfolio currency
    fx_missing: bool = False
    value: float = 0.0
    weight: float = 0.0
    account_id: int = 0
    account_type: str = ""
    synthetic: bool = False         # a cash account shown as a cash position

    @property
    def gain(self):
        if self.cost_basis is None or self.price is None:
            return None
        return self.value - self.cost_basis

    @property
    def gain_pct(self):
        if not self.cost_basis or self.price is None:
            return None
        return self.value / self.cost_basis - 1.0

    @property
    def day_change(self):
        if self.price is None or not self.prev_close:
            return None
        return (self.price - self.prev_close) * self.quantity * self.fx

    @property
    def day_change_pct(self):
        if self.price is None or not self.prev_close:
            return None
        return self.price / self.prev_close - 1.0

    @property
    def is_cash(self):
        return self.symbol == CASH_SYMBOL

    @property
    def class_label(self):
        return CLASSES.get(self.asset_class, CLASSES["other"])["label"]


@dataclass
class AccountValue:
    """One account and what it is worth today."""
    id: int
    name: str
    type: str
    owner_person: int
    institution: str
    notes: str
    value: float = 0.0              # today's value; for a debt, what is owed today
    set_value: float = 0.0          # the value typed in on as_of
    as_of: str | None = None
    rate: float | None = None
    payment: float | None = None
    term_months: int | None = None
    months_left: int | None = None
    n_holdings: int = 0
    cost: float = 0.0
    cost_value: float = 0.0
    day_change: float = 0.0
    unpriced: int = 0
    position: int = 0

    @property
    def info(self) -> dict:
        return at.get(self.type)

    @property
    def kind(self) -> str:
        return self.info["kind"]

    @property
    def label(self) -> str:
        return self.info["label"]

    @property
    def icon(self) -> str:
        return self.info["icon"]

    @property
    def tax(self) -> str:
        return self.info["tax"]

    @property
    def owner_label(self) -> str:
        return at.OWNER_LABEL.get(self.owner_person, "You")

    @property
    def gain(self):
        return self.cost_value - self.cost if self.cost else None

    @property
    def age_days(self) -> int | None:
        """Days since a hand-set value was last updated."""
        if not self.as_of or self.kind == "investments":
            return None
        try:
            return (date.today() - date.fromisoformat(self.as_of[:10])).days
        except ValueError:
            return None


@dataclass
class Valuation:
    positions: list[Position] = field(default_factory=list)
    accounts: list[AccountValue] = field(default_factory=list)
    total: float = 0.0              # investable: positions plus cash accounts
    property_total: float = 0.0
    debts: float = 0.0
    cost: float = 0.0
    day_change: float = 0.0
    priced: int = 0
    unpriced: list[str] = field(default_factory=list)
    as_of: str | None = None
    currency: str = "USD"

    @property
    def fx_missing(self) -> list[str]:
        return sorted({p.currency for p in self.positions if p.fx_missing})

    cost_value: float = 0.0          # value of the holdings that have a cost basis

    @property
    def assets(self) -> float:
        return self.total + self.property_total

    @property
    def net_worth(self) -> float:
        return self.assets - self.debts

    def kind_total(self, kind: str) -> float:
        return sum(a.value for a in self.accounts if a.kind == kind)

    def of_kind(self, kind: str) -> list[AccountValue]:
        return [a for a in self.accounts if a.kind == kind]

    def by_tax(self) -> list[tuple[str, float, float]]:
        """Investable assets by how they are taxed."""
        out: dict[str, float] = {}
        for a in self.accounts:
            if a.kind in ("investments", "cash"):
                k = at.TAX_LABEL[a.tax]
                out[k] = out.get(k, 0.0) + a.value
        return sorted(((k, v, v / self.total if self.total else 0.0)
                       for k, v in out.items() if v), key=lambda r: -r[1])

    def by_owner(self) -> list[tuple[str, float, float]]:
        out: dict[str, float] = {}
        for a in self.accounts:
            if a.kind in ("investments", "cash"):
                out[a.owner_label] = out.get(a.owner_label, 0.0) + a.value
        return sorted(((k, v, v / self.total if self.total else 0.0)
                       for k, v in out.items() if v), key=lambda r: -r[1])

    @property
    def gain(self):
        """Gain on the holdings whose cost is known - never mixes in the rest."""
        return self.cost_value - self.cost if self.cost else None

    @property
    def gain_pct(self):
        return self.cost_value / self.cost - 1.0 if self.cost else None

    @property
    def day_change_pct(self):
        base = self.total - self.day_change
        return self.day_change / base if base else None

    def by(self, key: str) -> list[tuple[str, float, float]]:
        """(bucket, value, weight) grouped by 'asset_class' or 'account'."""
        buckets: dict[str, float] = {}
        for p in self.positions:
            k = (p.class_label if key == "asset_class"
                 else (p.account or "Unassigned") if key == "account"
                 else getattr(p, key))
            buckets[k] = buckets.get(k, 0.0) + p.value
        out = [(k, v, v / self.total if self.total else 0.0)
               for k, v in buckets.items()]
        return sorted(out, key=lambda r: -r[1])


class PortfolioRepo:
    def __init__(self, db: Database):
        self.db = db

    # -- portfolios --------------------------------------------------------
    def list(self, owner: str) -> list[dict]:
        return self.db.query(
            "SELECT p.*, (SELECT COUNT(*) FROM holdings h WHERE h.portfolio_id = p.id)"
            " AS n_holdings, (SELECT COUNT(*) FROM accounts a WHERE a.portfolio_id = p.id)"
            " AS n_accounts FROM portfolios p WHERE p.owner = :o ORDER BY p.name",
            {"o": owner})

    def get(self, owner: str, pid: int) -> dict:
        d = self.db.one("SELECT * FROM portfolios WHERE id = :id AND owner = :o",
                        {"id": pid, "o": owner})
        if d is None:
            raise NotFound(f"portfolio {pid}")
        d["settings"] = _loads(d.get("settings"))
        return d

    def create(self, owner: str, name: str, currency: str = "USD",
               description: str = "", settings: dict | None = None) -> int:
        now = utcnow()
        with self.db.tx() as c:
            return self.db.insert(
                c, "INSERT INTO portfolios (owner, name, currency, description, settings,"
                   " created_at, updated_at) VALUES (:o, :n, :c, :d, :s, :t, :t)",
                {"o": owner, "n": name.strip() or "My portfolio",
                 "c": (currency or "USD").strip().upper(), "d": description.strip(),
                 "s": json.dumps(settings or {}), "t": now})

    def update(self, owner: str, pid: int, **fields) -> None:
        self.get(owner, pid)
        sets = {k: v for k, v in fields.items()
                if k in ("name", "currency", "description")}
        if "settings" in fields:
            sets["settings"] = json.dumps(fields["settings"])
        if not sets:
            return
        sets["updated_at"] = utcnow()
        cols = ", ".join(f"{k} = :{k}" for k in sets)
        with self.db.tx() as c:
            self.db.run(c, f"UPDATE portfolios SET {cols} WHERE id = :_id AND owner = :_o",
                        {**sets, "_id": pid, "_o": owner})

    def delete(self, owner: str, pid: int) -> None:
        with self.db.tx() as c:
            # holdings and projections go with it (ON DELETE CASCADE), but say so
            # explicitly too: a SQLite file opened without foreign keys would not
            self.db.run(c, "DELETE FROM holdings WHERE portfolio_id IN (SELECT id FROM"
                           " portfolios WHERE id = :id AND owner = :o)",
                        {"id": pid, "o": owner})
            self.db.run(c, "DELETE FROM accounts WHERE portfolio_id IN (SELECT id FROM"
                           " portfolios WHERE id = :id AND owner = :o)",
                        {"id": pid, "o": owner})
            self.db.run(c, "DELETE FROM projections WHERE portfolio_id IN (SELECT id FROM"
                           " portfolios WHERE id = :id AND owner = :o)",
                        {"id": pid, "o": owner})
            self.db.run(c, "DELETE FROM portfolios WHERE id = :id AND owner = :o",
                        {"id": pid, "o": owner})

    def duplicate(self, owner: str, pid: int) -> int:
        src = self.get(owner, pid)
        new = self.create(owner, f"{src['name']} (copy)", src["currency"],
                          src["description"], src["settings"])
        for a in self.accounts(owner, pid):
            aid = self.create_account(owner, new, a["name"], a["type"], a["owner_person"],
                                      a["institution"], a["value"], a["as_of"], a["rate"],
                                      a["payment"], a["term_months"], a["notes"])
            for h in self.holdings(owner, pid, a["id"]):
                self.add_holding(owner, new, aid, h["symbol"], h["quantity"],
                                 h["cost_basis"], h["asset_class"], h["notes"])
        return new

    def _touch(self, c, pid: int) -> None:
        self.db.run(c, "UPDATE portfolios SET updated_at = :t WHERE id = :id",
                    {"t": utcnow(), "id": pid})

    # -- accounts ----------------------------------------------------------
    ACCOUNT_FIELDS = ("name", "type", "owner_person", "institution", "value", "as_of",
                      "rate", "payment", "term_months", "notes", "position")

    def accounts(self, owner: str, pid: int) -> list[dict]:
        self.get(owner, pid)
        return self.db.query("SELECT * FROM accounts WHERE portfolio_id = :p"
                             " ORDER BY position, id", {"p": pid})

    def account(self, owner: str, pid: int, aid: int) -> dict:
        self.get(owner, pid)
        row = self.db.one("SELECT * FROM accounts WHERE id = :a AND portfolio_id = :p",
                          {"a": aid, "p": pid})
        if row is None:
            raise NotFound(f"account {aid}")
        return row

    def create_account(self, owner: str, pid: int, name: str, type: str,
                       owner_person: int = 0, institution: str = "", value: float = 0.0,
                       as_of: str | None = None, rate: float | None = None,
                       payment: float | None = None, term_months: int | None = None,
                       notes: str = "") -> int:
        self.get(owner, pid)
        if type not in at.BY_KEY:
            raise ValueError(f"unknown account type {type!r}")
        info = at.BY_KEY[type]
        if info["kind"] == "debt" and payment is None and term_months:
            payment = at.monthly_payment(value, rate or 0.0, term_months / 12)
        now = utcnow()
        with self.db.tx() as c:
            pos = self.db.run(c, "SELECT COALESCE(MAX(position), 0) FROM accounts"
                                 " WHERE portfolio_id = :p", {"p": pid}).scalar() or 0
            aid = self.db.insert(
                c, "INSERT INTO accounts (portfolio_id, name, type, owner_person,"
                   " institution, value, as_of, rate, payment, term_months, notes,"
                   " position, created_at, updated_at) VALUES (:p, :n, :t, :o, :i, :v,"
                   " :d, :r, :pay, :tm, :nt, :pos, :now, :now)",
                {"p": pid, "n": (name or "").strip() or info["label"], "t": type,
                 "o": int(owner_person), "i": (institution or "").strip(),
                 "v": float(value or 0.0),
                 "d": as_of or (None if info["kind"] == "investments"
                                else date.today().isoformat()),
                 "r": rate, "pay": payment, "tm": term_months, "nt": (notes or "").strip(),
                 "pos": int(pos) + 1, "now": now})
            self._touch(c, pid)
            return aid

    def update_account(self, owner: str, pid: int, aid: int, **fields) -> None:
        old = self.account(owner, pid, aid)
        sets = {k: v for k, v in fields.items() if k in self.ACCOUNT_FIELDS}
        if "type" in sets and sets["type"] not in at.BY_KEY:
            raise ValueError(f"unknown account type {sets['type']!r}")
        # a new value is a new starting point for pay-down and for staleness
        if "value" in sets and "as_of" not in sets and \
                float(sets["value"] or 0) != float(old["value"] or 0):
            sets["as_of"] = date.today().isoformat()
        if not sets:
            return
        sets["updated_at"] = utcnow()
        cols = ", ".join(f"{k} = :{k}" for k in sets)
        with self.db.tx() as c:
            self.db.run(c, f"UPDATE accounts SET {cols} WHERE id = :_a AND portfolio_id = :_p",
                        {**sets, "_a": aid, "_p": pid})
            self._touch(c, pid)

    def delete_account(self, owner: str, pid: int, aid: int) -> None:
        self.account(owner, pid, aid)
        with self.db.tx() as c:
            self.db.run(c, "DELETE FROM holdings WHERE account_id = :a AND portfolio_id = :p",
                        {"a": aid, "p": pid})
            self.db.run(c, "DELETE FROM accounts WHERE id = :a AND portfolio_id = :p",
                        {"a": aid, "p": pid})
            self._touch(c, pid)

    def find_or_create_account(self, owner: str, pid: int, name: str,
                               type: str | None = None) -> int:
        """The account called ``name`` in the portfolio, made (type guessed from the
        name) if there is none - for imports that name accounts by label."""
        name = (name or "").strip() or "Brokerage"
        for a in self.accounts(owner, pid):
            if a["name"].strip().lower() == name.lower():
                return a["id"]
        kind = type or at.guess(name)
        if at.get(kind)["kind"] != "investments":
            kind = "brokerage"
        return self.create_account(owner, pid, name, kind)

    # -- holdings ----------------------------------------------------------
    def holdings(self, owner: str, pid: int, aid: int | None = None) -> list[dict]:
        self.get(owner, pid)
        if aid is None:
            return self.db.query(
                "SELECT h.*, a.name AS account FROM holdings h JOIN accounts a"
                " ON a.id = h.account_id WHERE h.portfolio_id = :p"
                " ORDER BY a.position, a.id, h.symbol", {"p": pid})
        return self.db.query(
            "SELECT h.*, a.name AS account FROM holdings h JOIN accounts a"
            " ON a.id = h.account_id WHERE h.portfolio_id = :p AND h.account_id = :a"
            " ORDER BY h.symbol", {"p": pid, "a": aid})

    def holding(self, owner: str, pid: int, hid: int) -> dict:
        self.get(owner, pid)
        row = self.db.one("SELECT * FROM holdings WHERE id = :h AND portfolio_id = :p",
                          {"h": hid, "p": pid})
        if row is None:
            raise NotFound(f"holding {hid}")
        return row

    def add_holding(self, owner: str, pid: int, aid: int, symbol: str, quantity: float,
                    cost_basis: float | None = None, asset_class: str = "",
                    notes: str = "") -> int:
        acct = self.account(owner, pid, aid)
        if at.get(acct["type"])["kind"] != "investments":
            raise ValueError(f"'{acct['name']}' is not an investment account")
        symbol = normalise_symbol(symbol)
        if not symbol:
            raise ValueError("a holding needs a symbol")
        self.ensure_security(symbol)
        if symbol == CASH_SYMBOL and cost_basis is None:
            cost_basis = quantity
        # blank = follow the security's class, which the first fetch fills in
        if asset_class not in CLASSES:
            asset_class = ""
        with self.db.tx() as c:
            hid = self.db.insert(
                c, "INSERT INTO holdings (portfolio_id, account_id, symbol, quantity,"
                   " cost_basis, asset_class, notes, added_at)"
                   " VALUES (:p, :a, :s, :q, :cb, :ac, :n, :t)",
                {"p": pid, "a": aid, "s": symbol, "q": float(quantity), "cb": cost_basis,
                 "ac": asset_class, "n": (notes or "").strip(), "t": utcnow()})
            self._touch(c, pid)
            return hid

    def update_holding(self, owner: str, pid: int, hid: int, **fields) -> None:
        self.holding(owner, pid, hid)
        sets = {k: v for k, v in fields.items()
                if k in ("quantity", "cost_basis", "account_id", "asset_class", "notes")}
        if "asset_class" in sets and sets["asset_class"] not in CLASSES:
            sets["asset_class"] = ""
        if "account_id" in sets:
            acct = self.account(owner, pid, int(sets["account_id"]))
            if at.get(acct["type"])["kind"] != "investments":
                raise ValueError(f"'{acct['name']}' is not an investment account")
        if not sets:
            return
        cols = ", ".join(f"{k} = :{k}" for k in sets)
        with self.db.tx() as c:
            self.db.run(c, f"UPDATE holdings SET {cols} WHERE id = :_h AND portfolio_id = :_p",
                        {**sets, "_h": hid, "_p": pid})
            self._touch(c, pid)

    def delete_holding(self, owner: str, pid: int, hid: int) -> None:
        self.get(owner, pid)
        with self.db.tx() as c:
            self.db.run(c, "DELETE FROM holdings WHERE id = :h AND portfolio_id = :p",
                        {"h": hid, "p": pid})
            self._touch(c, pid)

    # -- securities --------------------------------------------------------
    def ensure_security(self, symbol: str) -> dict:
        symbol = normalise_symbol(symbol)
        row = self.security(symbol)
        if row is not None:
            return row
        is_cash = symbol == CASH_SYMBOL
        with self.db.tx() as c:
            self.db.run(
                c, "INSERT INTO securities (symbol, name, quote_type, asset_class,"
                   " last_price, prev_close, last_price_date)"
                   " VALUES (:s, :n, :q, :ac, :px, :px, :d)"
                   " ON CONFLICT (symbol) DO NOTHING",
                {"s": symbol, "n": "Cash" if is_cash else "",
                 "q": "CASH" if is_cash else "", "ac": "cash" if is_cash else "",
                 "px": 1.0 if is_cash else None,
                 "d": date.today().isoformat() if is_cash else None})
        return self.security(symbol)

    def security(self, symbol: str) -> dict | None:
        return self.db.one("SELECT * FROM securities WHERE symbol = :s",
                           {"s": normalise_symbol(symbol)})

    def securities(self) -> list[dict]:
        return self.db.query(
            "SELECT s.*,"
            " (SELECT COUNT(*) FROM prices p WHERE p.symbol = s.symbol) AS n_prices,"
            " (SELECT MIN(p.date) FROM prices p WHERE p.symbol = s.symbol) AS first_date,"
            " (SELECT COUNT(DISTINCT h.portfolio_id) FROM holdings h"
            "   WHERE h.symbol = s.symbol) AS n_portfolios"
            " FROM securities s ORDER BY s.symbol")

    def tracked_symbols(self) -> list[str]:
        """Every Yahoo-priced symbol held anywhere, plus the FX pairs their
        portfolios need - which is what the collector keeps priced. Manually
        priced securities are left alone."""
        rows = self.db.query("SELECT DISTINCT h.symbol FROM holdings h"
                             " JOIN securities s ON s.symbol = h.symbol"
                             " WHERE h.symbol <> :c AND s.source <> 'manual'"
                             " ORDER BY h.symbol", {"c": CASH_SYMBOL})
        out = [r["symbol"] for r in rows]
        return sorted(set(out) | set(self.fx_pairs_needed()))

    def fx_pairs_needed(self) -> list[str]:
        rows = self.db.query(
            "SELECT DISTINCT s.currency, p.currency AS base FROM holdings h"
            " JOIN securities s ON s.symbol = h.symbol"
            " JOIN portfolios p ON p.id = h.portfolio_id"
            " WHERE h.symbol <> :c AND s.currency <> ''", {"c": CASH_SYMBOL})
        return sorted({sym for r in rows
                       for sym, _ in [pair(r["currency"], r["base"])] if sym})

    def fx_rate(self, currency: str, base: str) -> tuple[float, bool]:
        """(rate, missing): multiply a ``currency`` price by rate to get ``base``."""
        sym, scale = pair(currency, base)
        if sym is None:
            return scale, False
        sec = self.security(sym)
        if sec and sec.get("last_price"):
            return sec["last_price"] * scale, False
        return scale, True

    def fx_series(self, currency: str, base: str) -> tuple[dict | None, float]:
        """{date: rate} for converting daily prices, or None when not needed."""
        sym, scale = pair(currency, base)
        if sym is None:
            return None, scale
        return {d: px for d, px in self.series([sym])[sym]}, scale

    def record_quote(self, history) -> None:
        """Update a security's descriptive fields and latest price from a fetch."""
        sym = history.symbol
        cur = self.ensure_security(sym)
        last = history.bars[-1] if history.bars else None
        price = history.price or (last.close if last else None)
        prev = history.bars[-2].close if len(history.bars) >= 2 else None
        prev = prev or history.prev_close
        cutoff = (date.today() - timedelta(days=365)).isoformat()
        divs = sum(a for d, a in history.dividends if d >= cutoff)
        dy = divs / price if price and divs else None
        asset_class = cur.get("asset_class") or classify(sym, history.name,
                                                         history.quote_type)
        with self.db.tx() as c:
            self.db.run(
                c, "UPDATE securities SET name = :n, quote_type = :q, currency = :cur,"
                   " exchange = :ex, asset_class = :ac, last_price = :px,"
                   " prev_close = :pc, last_price_date = :d, fetched_at = :t,"
                   " fetch_error = NULL, dividend_yield = COALESCE(:dy, dividend_yield)"
                   " WHERE symbol = :s",
                {"n": history.name or cur.get("name") or "", "q": history.quote_type,
                 "cur": history.currency, "ex": history.exchange, "ac": asset_class,
                 "px": price, "pc": prev, "d": last.date if last else None,
                 "t": utcnow(), "dy": dy, "s": sym})

    def record_error(self, symbol: str, message: str) -> None:
        self.ensure_security(symbol)
        with self.db.tx() as c:
            self.db.run(c, "UPDATE securities SET fetch_error = :m, fetched_at = :t"
                           " WHERE symbol = :s",
                        {"m": message[:300], "t": utcnow(),
                         "s": normalise_symbol(symbol)})

    def record_long_run(self, symbol: str, stats: dict) -> None:
        with self.db.tx() as c:
            self.db.run(c, "UPDATE securities SET lt_return = :r, lt_vol = :v,"
                           " lt_years = :y, lt_updated = :t WHERE symbol = :s",
                        {"r": stats["lt_return"], "v": stats["lt_vol"],
                         "y": stats["lt_years"], "t": utcnow(), "s": symbol})

    def set_security_class(self, symbol: str, asset_class: str) -> None:
        if asset_class not in CLASSES:
            raise ValueError(f"unknown asset class {asset_class!r}")
        with self.db.tx() as c:
            self.db.run(c, "UPDATE securities SET asset_class = :ac WHERE symbol = :s",
                        {"ac": asset_class, "s": normalise_symbol(symbol)})

    # -- security administration --------------------------------------------
    SECURITY_FIELDS = ("name", "quote_type", "currency", "exchange", "asset_class",
                       "source", "notes")

    def create_security(self, symbol: str, **fields) -> dict:
        symbol = normalise_symbol(symbol)
        if not symbol or symbol == CASH_SYMBOL:
            raise ValueError("choose a symbol other than CASH")
        if not re.fullmatch(r"[A-Z0-9.^=\-_:/&]{1,32}", symbol):
            raise ValueError("a symbol is 1-32 letters, digits or . ^ = - _ : / &")
        if self.security(symbol):
            raise ValueError(f"{symbol} already exists")
        self.ensure_security(symbol)
        self.update_security(symbol, **fields)
        return self.security(symbol)

    def update_security(self, symbol: str, **fields) -> None:
        sets = {k: (v or "").strip() if isinstance(v, str) or v is None else v
                for k, v in fields.items() if k in self.SECURITY_FIELDS}
        if "asset_class" in sets and sets["asset_class"] not in CLASSES:
            raise ValueError(f"unknown asset class {sets['asset_class']!r}")
        if "source" in sets and sets["source"] not in ("yahoo", "manual"):
            raise ValueError("source is yahoo or manual")
        if not sets:
            return
        cols = ", ".join(f"{k} = :{k}" for k in sets)
        with self.db.tx() as c:
            self.db.run(c, f"UPDATE securities SET {cols} WHERE symbol = :_s",
                        {**sets, "_s": normalise_symbol(symbol)})

    def holders(self, symbol: str) -> int:
        """How many holdings, in any workspace, reference the symbol."""
        return int(self.db.scalar("SELECT COUNT(*) FROM holdings WHERE symbol = :s",
                                  {"s": normalise_symbol(symbol)}, 0))

    def delete_security(self, symbol: str) -> None:
        symbol = normalise_symbol(symbol)
        n = self.holders(symbol)
        if n:
            raise ValueError(f"{symbol} is held in {n} holding(s); remove those first")
        with self.db.tx() as c:
            self.db.run(c, "DELETE FROM prices WHERE symbol = :s", {"s": symbol})
            self.db.run(c, "DELETE FROM securities WHERE symbol = :s", {"s": symbol})

    def put_prices(self, symbol: str, rows, retention_days: int = PRICE_RETENTION_DAYS) -> dict:
        """Upsert typed-in closes [(date, close, adj_close|None)]; then refresh the
        security's latest price from what is stored. Returns counts."""
        symbol = normalise_symbol(symbol)
        cutoff = retention_cutoff(retention_days)
        keep = [r for r in rows if r[0] >= cutoff]
        bars = [type("B", (), dict(date=d, close=float(c),
                                   adj_close=float(a if a is not None else c), volume=None))
                for d, c, a in keep]
        n = self.store_bars(symbol, bars, retention_days)
        self.refresh_latest(symbol)
        return dict(stored=n, too_old=len(rows) - len(keep))

    def delete_prices(self, symbol: str, dates) -> int:
        dates = list(dates)
        if not dates:
            return 0
        names = {f"d{i}": d for i, d in enumerate(dates)}
        with self.db.tx() as c:
            n = self.db.run(c, "DELETE FROM prices WHERE symbol = :s AND date IN ("
                               + ", ".join(":" + k for k in names) + ")",
                            dict(names, s=normalise_symbol(symbol))).rowcount
        self.refresh_latest(symbol)
        return n

    def refresh_latest(self, symbol: str) -> None:
        """Latest and previous close from the stored rows (for manual prices)."""
        rows = self.db.query("SELECT date, close FROM prices WHERE symbol = :s"
                             " ORDER BY date DESC LIMIT 2", {"s": normalise_symbol(symbol)})
        with self.db.tx() as c:
            self.db.run(c, "UPDATE securities SET last_price = :p, prev_close = :q,"
                           " last_price_date = :d, fetched_at = :t WHERE symbol = :s",
                        {"p": rows[0]["close"] if rows else None,
                         "q": rows[1]["close"] if len(rows) > 1 else None,
                         "d": rows[0]["date"] if rows else None, "t": utcnow(),
                         "s": normalise_symbol(symbol)})

    # -- prices ------------------------------------------------------------
    def last_price_date(self, symbol: str) -> str | None:
        return self.db.scalar("SELECT MAX(date) FROM prices WHERE symbol = :s",
                              {"s": symbol})

    def store_bars(self, symbol: str, bars, retention_days: int = PRICE_RETENTION_DAYS) -> int:
        """Upsert daily bars inside the retention window; returns rows written."""
        cutoff = retention_cutoff(retention_days)
        rows = [{"s": symbol, "d": b.date, "c": b.close, "a": b.adj_close,
                 "v": b.volume} for b in bars if b.date >= cutoff]
        if not rows:
            return 0
        with self.db.tx() as c:
            # Adjusted closes are restated after every dividend and split, so a
            # re-fetched date replaces what was stored rather than being skipped.
            self.db.run(c, "INSERT INTO prices (symbol, date, close, adj_close, volume)"
                           " VALUES (:s, :d, :c, :a, :v)"
                           " ON CONFLICT (symbol, date) DO UPDATE SET"
                           " close = excluded.close, adj_close = excluded.adj_close,"
                           " volume = excluded.volume", rows)
        return len(rows)

    def prune(self, days: int = PRICE_RETENTION_DAYS) -> int:
        with self.db.tx() as c:
            return self.db.run(c, "DELETE FROM prices WHERE date < :d",
                               {"d": retention_cutoff(days)}).rowcount

    def series(self, symbols, since: str | None = None) -> dict[str, list[tuple[str, float]]]:
        """{symbol: [(date, adj_close), ...]} in date order."""
        symbols = list(symbols)
        out: dict[str, list] = {s: [] for s in symbols}
        if not symbols:
            return out
        names = {f"s{i}": s for i, s in enumerate(symbols)}
        sql = (f"SELECT symbol, date, adj_close FROM prices WHERE symbol IN"
               f" ({', '.join(':' + k for k in names)})"
               + (" AND date >= :since" if since else "") + " ORDER BY symbol, date")
        params = dict(names, since=since) if since else names
        for r in self.db.query(sql, params):
            out[r["symbol"]].append((r["date"], r["adj_close"]))
        return out

    def series_in(self, symbol: str, base: str) -> list[tuple[str, float]]:
        """Adjusted closes converted to ``base`` day by day (FX carried forward
        over days one market is shut and the other open)."""
        raw = self.series([symbol])[symbol]
        sec = self.security(symbol) or {}
        fx, scale = self.fx_series(sec.get("currency") or "", base)
        if fx is None:
            return [(d, px * scale) for d, px in raw]
        if not fx:
            return []                     # the pair has not been priced yet
        out, last = [], None
        fx_dates = sorted(fx)
        j = 0
        for d, px in raw:
            while j < len(fx_dates) and fx_dates[j] <= d:
                last = fx[fx_dates[j]]
                j += 1
            if last is not None:
                out.append((d, px * last * scale))
        return out

    def close_series(self, symbol: str) -> list[tuple[str, float, float]]:
        return [(r["date"], r["close"], r["adj_close"]) for r in self.db.query(
            "SELECT date, close, adj_close FROM prices WHERE symbol = :s ORDER BY date",
            {"s": symbol})]

    def price_stats_for(self, symbol: str) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM prices WHERE symbol = :s",
                                  {"s": normalise_symbol(symbol)}, 0))

    def price_stats(self) -> dict:
        r = self.db.one("SELECT COUNT(*) AS n_rows, COUNT(DISTINCT symbol) AS n_symbols,"
                        " MIN(date) AS first, MAX(date) AS last FROM prices")
        return dict(rows=r["n_rows"], symbols=r["n_symbols"], first=r["first"],
                    last=r["last"])

    # -- valuation ---------------------------------------------------------
    def valuation(self, owner: str, pid: int, aid: int | None = None) -> Valuation:
        """Today's value of everything in the portfolio (or of one account)."""
        base = self.get(owner, pid)["currency"]
        accts = [a for a in self.accounts(owner, pid) if aid is None or a["id"] == aid]
        if aid is not None and not accts:
            raise NotFound(f"account {aid}")
        by_id = {a["id"]: _account_value(a) for a in accts}
        rows = self.db.query(
            "SELECT h.*, s.name, s.last_price, s.prev_close, s.last_price_date,"
            " s.currency, s.fetch_error, s.asset_class AS sec_class FROM holdings h"
            " LEFT JOIN securities s ON s.symbol = h.symbol"
            " WHERE h.portfolio_id = :p ORDER BY h.account_id, h.symbol", {"p": pid})
        v = Valuation()
        dates = []
        for r in rows:
            acct = by_id.get(r["account_id"])
            if acct is None:
                continue
            p = Position(id=r["id"], symbol=r["symbol"], name=r["name"] or "",
                         quantity=r["quantity"], cost_basis=r["cost_basis"],
                         account=acct.name, account_id=acct.id, account_type=acct.type,
                         asset_class=r["asset_class"] or r["sec_class"] or "other",
                         notes=r["notes"], price=r["last_price"],
                         prev_close=r["prev_close"], price_date=r["last_price_date"],
                         currency=r["currency"] or "", fetch_error=r["fetch_error"],
                         class_inherited=not r["asset_class"])
            if not p.is_cash:
                p.fx, p.fx_missing = self.fx_rate(p.currency, base)
            acct.n_holdings += 1
            if p.price is not None:
                p.value = p.quantity * p.price * p.fx
                v.priced += 1
                if p.price_date and not p.is_cash:
                    dates.append(p.price_date)
                v.day_change += p.day_change or 0.0
                acct.day_change += p.day_change or 0.0
            else:
                v.unpriced.append(p.symbol)
                acct.unpriced += 1
            acct.value += p.value
            if p.cost_basis is not None:
                v.cost += p.cost_basis
                v.cost_value += p.value
                acct.cost += p.cost_basis
                acct.cost_value += p.value
            v.positions.append(p)
        for a in by_id.values():
            if a.kind == "cash":
                # a cash account counts as a cash position in every analysis
                v.positions.append(Position(
                    id=-a.id, symbol=CASH_SYMBOL, name=a.name, quantity=a.value,
                    cost_basis=a.value, account=a.name, account_id=a.id,
                    account_type=a.type, asset_class="cash", notes="", price=1.0,
                    prev_close=1.0, price_date=a.as_of, currency=base, fetch_error=None,
                    value=a.value, synthetic=True))
                v.cost += a.value
                v.cost_value += a.value
            elif a.kind == "property":
                v.property_total += a.value
            elif a.kind == "debt":
                v.debts += a.value
        v.total = sum(p.value for p in v.positions)
        for p in v.positions:
            p.weight = p.value / v.total if v.total else 0.0
        v.accounts = sorted(by_id.values(), key=lambda a: (a.position, a.id))
        v.as_of = max(dates) if dates else None
        v.currency = base
        return v

    def value_history(self, owner: str, pid: int) -> list[tuple[str, float]]:
        """Daily value of the *current* holdings over the stored price window.

        A back-cast, not a performance record: it answers "what would today's
        portfolio have been worth", which is what a snapshot of holdings allows.
        """
        base = self.get(owner, pid)["currency"]
        holdings = self.holdings(owner, pid)
        syms = sorted({h["symbol"] for h in holdings if h["symbol"] != CASH_SYMBOL})
        cash = sum(h["quantity"] for h in holdings if h["symbol"] == CASH_SYMBOL)
        cash += sum(a["value"] or 0.0 for a in self.accounts(owner, pid)
                    if at.get(a["type"])["kind"] == "cash")
        series = {s: self.series_in(s, base) for s in syms}
        # a symbol with no prices at all counts as zero, exactly as the valuation
        # does - otherwise one bad ticker would blank the whole chart
        syms = [s for s in syms if series[s]]
        qty: dict[str, float] = {}
        for h in holdings:
            qty[h["symbol"]] = qty.get(h["symbol"], 0.0) + h["quantity"]
        all_dates = sorted({d for s in series.values() for d, _ in s})
        if not all_dates:
            return []
        idx = {s: dict(series[s]) for s in syms}
        last = {s: None for s in syms}
        # Series use adjusted closes, so scale each back to today's unadjusted
        # price level; otherwise the latest point would not equal the valuation.
        scale = {}
        for s in syms:
            sec = self.security(s) or {}
            rate, _ = self.fx_rate(sec.get("currency") or "", base)
            adj_last = series[s][-1][1] if series[s] else None
            scale[s] = (sec["last_price"] * rate / adj_last
                        if adj_last and sec.get("last_price") else 1.0)
        out = []
        for d in all_dates:
            total, complete = cash, True
            for s in syms:            # carry each close across its own holidays
                if d in idx[s]:
                    last[s] = idx[s][d]
                if last[s] is None:
                    complete = False
                    break
                total += qty[s] * last[s] * scale[s]
            if complete:
                out.append((d, total))
        return out

    # -- fetch runs --------------------------------------------------------
    def start_run(self, reason: str, n: int) -> int:
        with self.db.tx() as c:
            return self.db.insert(c, "INSERT INTO fetch_runs (reason, started_at, symbols)"
                                     " VALUES (:r, :t, :n)",
                                  {"r": reason, "t": utcnow(), "n": n})

    def finish_run(self, run_id: int, ok: int, failed: int, added: int, pruned: int,
                   message: str) -> None:
        with self.db.tx() as c:
            self.db.run(c, "UPDATE fetch_runs SET finished_at = :t, ok = :ok,"
                           " failed = :f, rows_added = :a, rows_pruned = :p,"
                           " message = :m WHERE id = :id",
                        {"t": utcnow(), "ok": ok, "f": failed, "a": added, "p": pruned,
                         "m": message[:2000], "id": run_id})

    def runs(self, limit: int = 20) -> list[dict]:
        return self.db.query("SELECT * FROM fetch_runs ORDER BY id DESC LIMIT :n",
                             {"n": limit})

    def last_successful_run(self) -> dict | None:
        return self.db.one("SELECT * FROM fetch_runs WHERE finished_at IS NOT NULL"
                           " AND ok > 0 ORDER BY id DESC LIMIT 1")

    # -- portfolio-builder drafts -----------------------------------------------
    def save_draft(self, owner: str, filename: str, data: dict) -> int:
        with self.db.tx() as c:
            # a draft is scratch work: anything older than a week goes
            week_ago = (date.today() - timedelta(days=7)).isoformat()
            self.db.run(c, "DELETE FROM import_drafts WHERE created_at < :d", {"d": week_ago})
            return self.db.insert(c, "INSERT INTO import_drafts (owner, filename, created_at,"
                                     " data) VALUES (:o, :f, :t, :d)",
                                  {"o": owner, "f": filename[:200], "t": utcnow(),
                                   "d": json.dumps(data)})

    def draft(self, owner: str, did: int) -> dict:
        r = self.db.one("SELECT * FROM import_drafts WHERE id = :id AND owner = :o",
                        {"id": did, "o": owner})
        if r is None:
            raise NotFound(f"draft {did}")
        out = dict(_loads(r["data"]))
        out.update(id=r["id"], filename=r["filename"], created_at=r["created_at"])
        return out

    def update_draft(self, owner: str, did: int, data: dict) -> None:
        self.draft(owner, did)
        with self.db.tx() as c:
            self.db.run(c, "UPDATE import_drafts SET data = :d WHERE id = :id",
                        {"d": json.dumps(data), "id": did})

    def drafts(self, owner: str) -> list[dict]:
        return self.db.query("SELECT id, filename, created_at FROM import_drafts"
                             " WHERE owner = :o ORDER BY id DESC LIMIT 10", {"o": owner})

    def delete_draft(self, owner: str, did: int) -> None:
        with self.db.tx() as c:
            self.db.run(c, "DELETE FROM import_drafts WHERE id = :id AND owner = :o",
                        {"id": did, "o": owner})

    # -- saved projections -------------------------------------------------
    def save_projection(self, owner: str, pid: int, settings: dict, summary: dict,
                        result: dict, keep: int = 10) -> int:
        self.get(owner, pid)
        with self.db.tx() as c:
            new = self.db.insert(
                c, "INSERT INTO projections (portfolio_id, created_at, settings,"
                   " summary, result) VALUES (:p, :t, :s, :m, :r)",
                {"p": pid, "t": utcnow(), "s": json.dumps(settings),
                 "m": json.dumps(summary), "r": json.dumps(result)})
            keep_ids = [r[0] for r in self.db.run(
                c, "SELECT id FROM projections WHERE portfolio_id = :p"
                   " ORDER BY id DESC LIMIT :k", {"p": pid, "k": keep})]
            if keep_ids:
                names = {f"k{i}": v for i, v in enumerate(keep_ids)}
                self.db.run(c, "DELETE FROM projections WHERE portfolio_id = :p AND id"
                               f" NOT IN ({', '.join(':' + k for k in names)})",
                            dict(names, p=pid))
            return new

    def projections(self, owner: str, pid: int) -> list[dict]:
        self.get(owner, pid)
        rows = self.db.query("SELECT id, created_at, settings, summary FROM projections"
                             " WHERE portfolio_id = :p ORDER BY id DESC", {"p": pid})
        return [dict(id=r["id"], created_at=r["created_at"],
                     settings=_loads(r["settings"]), summary=_loads(r["summary"]))
                for r in rows]

    def projection(self, owner: str, pid: int, proj_id: int) -> dict:
        self.get(owner, pid)
        r = self.db.one("SELECT * FROM projections WHERE id = :id AND portfolio_id = :p",
                        {"id": proj_id, "p": pid})
        if r is None:
            raise NotFound(f"projection {proj_id}")
        return dict(id=r["id"], created_at=r["created_at"],
                    settings=_loads(r["settings"]), summary=_loads(r["summary"]),
                    result=_loads(r["result"]))

    def delete_projection(self, owner: str, pid: int, proj_id: int) -> None:
        self.get(owner, pid)
        with self.db.tx() as c:
            self.db.run(c, "DELETE FROM projections WHERE id = :id AND portfolio_id = :p",
                        {"id": proj_id, "p": pid})


def _account_value(row: dict) -> AccountValue:
    """An account row as an AccountValue; a debt is paid down to today."""
    a = AccountValue(id=row["id"], name=row["name"], type=row["type"],
                     owner_person=int(row["owner_person"] or 0),
                     institution=row["institution"] or "", notes=row["notes"] or "",
                     set_value=float(row["value"] or 0.0), as_of=row["as_of"],
                     rate=row["rate"], payment=row["payment"],
                     term_months=row["term_months"], position=int(row["position"] or 0))
    if a.kind in ("cash", "property"):
        a.value = a.set_value
    elif a.kind == "debt":
        months = 0
        if a.as_of:
            try:
                d0, d1 = date.fromisoformat(a.as_of[:10]), date.today()
                months = max(0, (d1.year - d0.year) * 12 + d1.month - d0.month
                             - (1 if d1.day < d0.day else 0))
            except ValueError:
                months = 0
        pay = a.payment
        if pay is None and a.term_months:
            pay = at.monthly_payment(a.set_value, a.rate or 0.0, a.term_months / 12)
        a.payment = pay
        a.value = at.amortised(a.set_value, a.rate or 0.0, pay or 0.0, months)
        if a.term_months:
            a.months_left = max(0, int(a.term_months) - months)
    return a


def normalise_symbol(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    return CASH_SYMBOL if s in ("$", "CASH", "$CASH", "USD CASH") else s


def retention_cutoff(days: int = PRICE_RETENTION_DAYS) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def _loads(text):
    if isinstance(text, (dict, list)):
        return text
    try:
        return json.loads(text or "{}")
    except ValueError:
        return {}
