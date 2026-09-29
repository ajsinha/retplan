"""Portfolio, holding, security and price persistence.

Everything the web layer reads or writes about portfolios goes through
:class:`PortfolioRepo`, so SQL lives in one module and every query that touches a
portfolio is scoped by its owner - one workspace can never read another's
portfolios or holdings. Securities and prices are deliberately shared (a price is
a fact about a symbol); the pages only show a workspace the symbols it holds.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

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
    account: str
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
class Valuation:
    positions: list[Position] = field(default_factory=list)
    total: float = 0.0
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
            " AS n_holdings FROM portfolios p WHERE p.owner = :o ORDER BY p.name",
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
            self.db.run(c, "DELETE FROM projections WHERE portfolio_id IN (SELECT id FROM"
                           " portfolios WHERE id = :id AND owner = :o)",
                        {"id": pid, "o": owner})
            self.db.run(c, "DELETE FROM portfolios WHERE id = :id AND owner = :o",
                        {"id": pid, "o": owner})

    def duplicate(self, owner: str, pid: int) -> int:
        src = self.get(owner, pid)
        new = self.create(owner, f"{src['name']} (copy)", src["currency"],
                          src["description"], src["settings"])
        for h in self.holdings(owner, pid):
            self.add_holding(owner, new, h["symbol"], h["quantity"], h["cost_basis"],
                             h["account"], h["asset_class"], h["notes"])
        return new

    def _touch(self, c, pid: int) -> None:
        self.db.run(c, "UPDATE portfolios SET updated_at = :t WHERE id = :id",
                    {"t": utcnow(), "id": pid})

    # -- holdings ----------------------------------------------------------
    def holdings(self, owner: str, pid: int) -> list[dict]:
        self.get(owner, pid)
        return self.db.query("SELECT * FROM holdings WHERE portfolio_id = :p"
                             " ORDER BY account, symbol", {"p": pid})

    def holding(self, owner: str, pid: int, hid: int) -> dict:
        self.get(owner, pid)
        row = self.db.one("SELECT * FROM holdings WHERE id = :h AND portfolio_id = :p",
                          {"h": hid, "p": pid})
        if row is None:
            raise NotFound(f"holding {hid}")
        return row

    def add_holding(self, owner: str, pid: int, symbol: str, quantity: float,
                    cost_basis: float | None = None, account: str = "",
                    asset_class: str = "", notes: str = "") -> int:
        self.get(owner, pid)
        symbol = normalise_symbol(symbol)
        if not symbol:
            raise ValueError("a holding needs a symbol")
        sec = self.ensure_security(symbol)
        if symbol == CASH_SYMBOL and cost_basis is None:
            cost_basis = quantity
        # blank = follow the security's class, which the first fetch fills in
        if asset_class not in CLASSES:
            asset_class = ""
        with self.db.tx() as c:
            hid = self.db.insert(
                c, "INSERT INTO holdings (portfolio_id, symbol, quantity, cost_basis,"
                   " account, asset_class, notes, added_at)"
                   " VALUES (:p, :s, :q, :cb, :a, :ac, :n, :t)",
                {"p": pid, "s": symbol, "q": float(quantity), "cb": cost_basis,
                 "a": (account or "").strip(), "ac": asset_class,
                 "n": (notes or "").strip(), "t": utcnow()})
            self._touch(c, pid)
            return hid

    def update_holding(self, owner: str, pid: int, hid: int, **fields) -> None:
        self.holding(owner, pid, hid)
        sets = {k: v for k, v in fields.items()
                if k in ("quantity", "cost_basis", "account", "asset_class", "notes")}
        if "asset_class" in sets and sets["asset_class"] not in CLASSES:
            sets["asset_class"] = ""
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
    def valuation(self, owner: str, pid: int) -> Valuation:
        base = self.get(owner, pid)["currency"]
        rows = self.db.query(
            "SELECT h.*, s.name, s.last_price, s.prev_close, s.last_price_date,"
            " s.currency, s.fetch_error, s.asset_class AS sec_class FROM holdings h"
            " LEFT JOIN securities s ON s.symbol = h.symbol"
            " WHERE h.portfolio_id = :p ORDER BY h.account, h.symbol", {"p": pid})
        v = Valuation()
        dates = []
        for r in rows:
            p = Position(id=r["id"], symbol=r["symbol"], name=r["name"] or "",
                         quantity=r["quantity"], cost_basis=r["cost_basis"],
                         account=r["account"],
                         asset_class=r["asset_class"] or r["sec_class"] or "other",
                         notes=r["notes"], price=r["last_price"],
                         prev_close=r["prev_close"], price_date=r["last_price_date"],
                         currency=r["currency"] or "", fetch_error=r["fetch_error"],
                         class_inherited=not r["asset_class"])
            if not p.is_cash:
                p.fx, p.fx_missing = self.fx_rate(p.currency, base)
            if p.price is not None:
                p.value = p.quantity * p.price * p.fx
                v.priced += 1
                if p.price_date and not p.is_cash:
                    dates.append(p.price_date)
                v.day_change += p.day_change or 0.0
            else:
                v.unpriced.append(p.symbol)
            v.total += p.value
            if p.cost_basis is not None:
                v.cost += p.cost_basis
                v.cost_value += p.value
            v.positions.append(p)
        for p in v.positions:
            p.weight = p.value / v.total if v.total else 0.0
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
