#!/usr/bin/env python3
"""Tests for the database, portfolios, prices, projections, wizard and web pages.

Plain asserts in the style of run_tests.py, and fully offline: Yahoo is replaced
by synthetic price histories, so the suite is deterministic and needs no network.

    python3 tests/test_portfolio.py                       # SQLite in memory
    python3 tests/test_portfolio.py --database URL        # e.g. a PostgreSQL URL
                                                          #   (must be an EMPTY database)

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import io
import math
import os
import re
import sys
import tempfile
import time
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np

from portfolio import yahoo
from portfolio.assets import CLASSES, classify
from portfolio.checks import rebalance, run_checks
from portfolio.db import SCHEMA_DIR, Database, declared_tables, split_sql
from portfolio.fx import major, pair
from portfolio.importer import parse
from portfolio.prices import PriceCollector, _range_for
from portfolio.projection import (AssetInput, CashFlow, Settings, assets_from_db,
                                  estimate, replay, simulate)
from portfolio.repository import NotFound, PortfolioRepo, retention_cutoff
from portfolio.stress import SCENARIOS, class_path

PASS, FAIL = [], []
DB_URL = "sqlite://"


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f"   {detail}" if detail and not cond else ""))


def close(a, b, tol=1e-9):
    return abs(a - b) <= tol * max(1.0, abs(b))


# ------------------------------------------------------------------ fakes
def synthetic(symbol, days=400, mu=0.08, sigma=0.16, seed=1, currency="USD",
              quote_type="ETF", name=None, start_price=100.0):
    """A yahoo.History with `days` calendar days of trading-day closes."""
    rng = np.random.default_rng(seed)
    bars, px = [], start_price
    d0 = date.today() - timedelta(days=days)
    for i in range(days + 1):
        d = d0 + timedelta(days=i)
        if d.weekday() >= 5:
            continue
        px *= math.exp(rng.normal(mu / 252 - 0.5 * sigma ** 2 / 252, sigma / math.sqrt(252)))
        bars.append(yahoo.Bar(d.isoformat(), px, px, 1000.0))
    return yahoo.History(symbol=symbol, name=name or f"{symbol} Total Market Index ETF",
                         quote_type=quote_type, currency=currency, exchange="TEST",
                         price=bars[-1].close, prev_close=bars[-2].close, bars=bars,
                         dividends=[(bars[-10].date, 1.0)])


class FakeYahoo:
    def __init__(self, table):
        self.table = table          # symbol -> History (or Exception)
        self.calls = []

    def fetch(self, symbol, range_="1y", interval="1d"):
        self.calls.append((symbol, range_))
        h = self.table.get(symbol)
        if h is None:
            raise yahoo.YahooError("No data found, symbol may be delisted")
        if isinstance(h, Exception):
            raise h
        return h

    @staticmethod
    def long_run(symbol):
        return {"lt_return": 0.09, "lt_vol": 0.15, "lt_years": 20.0}


def fresh_db():
    db = Database(DB_URL)
    if DB_URL != "sqlite://":
        # a shared server database: empty every table first, children first
        with db.tx() as c:
            for t in ("projections", "holdings", "prices", "portfolios", "plans",
                      "securities", "fetch_runs", "import_drafts", "snapshots", "app_settings"):
                Database.run(c, f"DELETE FROM {t}")
    return db


# ------------------------------------------------------------------ schema
def test_schema_files():
    def columns(path):
        text = open(path, encoding="utf-8").read()
        out = {}
        for stmt in split_sql(text):
            m = re.match(r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*)\)", stmt, re.S)
            if not m:
                continue
            cols = []
            for line in m.group(2).split("\n"):
                line = line.strip().rstrip(",")
                w = line.split()
                if w and w[0].upper() not in ("PRIMARY", "UNIQUE", "FOREIGN", "CHECK",
                                              "CONSTRAINT"):
                    cols.append(w[0].lower())
            out[m.group(1)] = cols
        return out

    lite = columns(os.path.join(SCHEMA_DIR, "sqlite.sql"))
    pg = columns(os.path.join(SCHEMA_DIR, "postgres.sql"))
    check("both schema files declare the same tables", sorted(lite) == sorted(pg),
          f"{sorted(lite)} vs {sorted(pg)}")
    for t in lite:
        check(f"schema column lists match: {t}", lite[t] == pg.get(t),
              f"{lite[t]} vs {pg.get(t)}")
    idx = lambda p: sorted(re.findall(r"CREATE (?:UNIQUE )?INDEX IF NOT EXISTS\s+(\w+)",  # noqa: E731
                                      open(os.path.join(SCHEMA_DIR, p)).read()))
    check("both schema files declare the same indexes", idx("sqlite.sql") == idx("postgres.sql"))
    db = fresh_db()
    from sqlalchemy import inspect
    live = set(inspect(db.engine).get_table_names())
    check("an empty database is built from its schema file",
          set(declared_tables(open(os.path.join(SCHEMA_DIR, "sqlite.sql")).read())) <= live)


def test_schema_mismatch_detected():
    if DB_URL != "sqlite://":
        return
    from portfolio.db import SchemaError
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "x.db")
        Database(f"sqlite:///{path}").dispose()
        import sqlite3
        con = sqlite3.connect(path)
        con.execute("DROP TABLE projections")
        con.commit()
        con.close()
        try:
            Database(f"sqlite:///{path}")
            ok = False
        except SchemaError as exc:
            ok = "projections" in str(exc)
        check("a database missing a declared table is refused, not migrated", ok)


# ------------------------------------------------------------------ repository
def test_repository():
    db = fresh_db()
    r = PortfolioRepo(db)
    pid = r.create("alice", "Core", "usd")
    check("portfolio currency is upper-cased", r.get("alice", pid)["currency"] == "USD")
    r.add_holding("alice", pid, "vti", 10, 3000, "Roth")
    r.add_holding("alice", pid, "$cash", 500)
    hs = r.holdings("alice", pid)
    check("symbols are normalised", sorted(h["symbol"] for h in hs) == ["CASH", "VTI"])
    check("cash cost basis defaults to its amount",
          [h["cost_basis"] for h in hs if h["symbol"] == "CASH"] == [500])
    try:
        r.get("bob", pid)
        iso = False
    except NotFound:
        iso = True
    check("another workspace cannot read the portfolio", iso)
    try:
        r.add_holding("bob", pid, "AAPL", 1)
        iso2 = False
    except NotFound:
        iso2 = True
    check("another workspace cannot add to it", iso2)
    check("another workspace sees no portfolios", r.list("bob") == [])
    r.update("alice", pid, settings={"targets": {"equity": 0.6}})
    check("settings round-trip as JSON", r.get("alice", pid)["settings"]["targets"]["equity"] == 0.6)
    new = r.duplicate("alice", pid)
    check("duplicate copies holdings", len(r.holdings("alice", new)) == 2)
    r.save_projection("alice", pid, {"a": 1}, {"b": 2}, {"c": 3})
    r.delete("alice", pid)
    check("delete removes holdings and projections",
          db.scalar("SELECT COUNT(*) FROM holdings WHERE portfolio_id = :p", {"p": pid}) == 0
          and db.scalar("SELECT COUNT(*) FROM projections WHERE portfolio_id = :p", {"p": pid}) == 0)
    check("the duplicate survives", len(r.holdings("alice", new)) == 2)
    for i in range(13):
        r.save_projection("alice", new, {"i": i}, {}, {})
    runs = r.projections("alice", new)
    check("only the last ten projections are kept", len(runs) == 10 and runs[0]["settings"]["i"] == 12)


def test_classify():
    cases = [("VTI", "Vanguard Total Stock Market ETF", "ETF", "equity"),
             ("BND", "Vanguard Total Bond Market ETF", "ETF", "bond"),
             ("VXUS", "Vanguard Total International Stock ETF", "ETF", "intl_equity"),
             ("VWO", "Vanguard FTSE Emerging Markets ETF", "ETF", "em_equity"),
             ("VNQ", "Vanguard Real Estate ETF", "ETF", "property"),
             ("GLD", "SPDR Gold Shares", "ETF", "commodity"),
             ("BTC-USD", "Bitcoin USD", "CRYPTOCURRENCY", "crypto"),
             ("VMFXX", "Vanguard Federal Money Market Fund", "MONEYMARKET", "cash"),
             ("AAPL", "Apple Inc.", "EQUITY", "equity")]
    for sym, name, qt, want in cases:
        check(f"classify {sym} as {want}", classify(sym, name, qt) == want,
              classify(sym, name, qt))


def test_fx_helpers():
    check("GBp is pence of GBP", major("GBp") == ("GBP", 0.01))
    check("same currency needs no pair", pair("USD", "usd") == (None, 1.0))
    check("pence into USD uses GBPUSD=X at 1/100", pair("GBp", "USD") == ("GBPUSD=X", 0.01))


# ------------------------------------------------------------------ prices
def test_prices_and_retention():
    db = fresh_db()
    r = PortfolioRepo(db)
    pid = r.create("alice", "Mixed", "USD")
    r.add_holding("alice", pid, "VTI", 10, 2000)
    r.add_holding("alice", pid, "VOD.L", 1000, 1200)
    r.add_holding("alice", pid, "NOPE", 5)
    r.add_holding("alice", pid, "CASH", 1000)
    vod = synthetic("VOD.L", mu=0.02, sigma=0.25, seed=2, currency="GBp",
                    quote_type="EQUITY", name="Vodafone Group Plc", start_price=120)
    fx = synthetic("GBPUSD=X", mu=0.0, sigma=0.08, seed=3, currency="USD",
                   quote_type="CURRENCY", name="GBP/USD", start_price=1.30)
    fake = FakeYahoo({"VTI": synthetic("VTI", seed=1), "VOD.L": vod, "GBPUSD=X": fx})
    col = PriceCollector(r, fetch=fake.fetch, long_run=fake.long_run, pause=0)
    res = col.collect(reason="test")
    check("collector prices every held symbol plus the FX pair it discovers",
          {s for s, _ in fake.calls} == {"VTI", "VOD.L", "NOPE", "GBPUSD=X"}, fake.calls)
    check("a failing symbol is recorded, not fatal", res["failed"] == 1 and res["ok"] == 3)
    check("the failure is kept on the security", bool(r.security("NOPE")["fetch_error"]))
    check("a first fetch asks for a year", all(rg == "1y" for _, rg in fake.calls))
    oldest = db.scalar("SELECT MIN(date) FROM prices")
    check("nothing older than the retention window is stored", oldest >= retention_cutoff(),
          f"{oldest} < {retention_cutoff()}")
    check("long-run statistics are kept as numbers", r.security("VTI")["lt_vol"] == 0.15)
    check("dividend yield is computed", (r.security("VTI")["dividend_yield"] or 0) > 0)
    fake.calls.clear()
    col.collect(reason="again")
    check("a later fetch asks only for the gap", all(rg == "5d" for s, rg in fake.calls if s != "NOPE"),
          fake.calls)
    # prune removes rows past retention
    with db.tx() as c:
        Database.run(c, "INSERT INTO prices (symbol, date, close, adj_close) VALUES "
                        "('VTI', '2000-01-03', 1, 1)")
    check("prune deletes closes past retention", r.prune() == 1)
    check("a longer retention fetches a longer first history",
          _range_for(None, 730) == "2y" and _range_for(None, 365) == "1y")
    check("gap ranges", _range_for(None) == "1y" and _range_for(date.today().isoformat()) == "5d"
          and _range_for((date.today() - timedelta(days=40)).isoformat()) == "3mo")

    v = r.valuation("alice", pid)
    by = {p.symbol: p for p in v.positions}
    rate = r.security("GBPUSD=X")["last_price"]
    check("a pence-quoted holding is converted at FX/100",
          close(by["VOD.L"].value, 1000 * vod.bars[-1].close * rate / 100, 1e-9))
    check("an unpriced holding counts as zero and is listed",
          by["NOPE"].value == 0 and "NOPE" in v.unpriced)
    check("weights sum to one", close(sum(p.weight for p in v.positions), 1.0))
    hist = r.value_history("alice", pid)
    check("the back-cast ends at today's valuation",
          close(hist[-1][1], v.total - by["NOPE"].value, 1e-9), f"{hist[-1][1]} vs {v.total}")
    checks = run_checks(v, {p.symbol: r.security(p.symbol) or {} for p in v.positions})
    check("unpriced holdings are flagged as a failure",
          any(c["severity"] == "bad" and "no price" in c["title"] for c in checks))
    check("a single company over 25% is flagged",
          any("Concentrated" in c["title"] for c in checks))


def test_config():
    from web.config import ROOT, load_config
    os.environ["RETPLAN_DATA"] = "somewhere/else"
    try:
        cfg = load_config()
    finally:
        del os.environ["RETPLAN_DATA"]
    check("a relative data dir is resolved from the project root",
          cfg.data_dir == os.path.join(ROOT, "somewhere/else"))
    if "RETPLAN_DATABASE_URL" not in os.environ:
        check("the default SQLite file moves with the data dir",
              cfg.database_url == "sqlite:///" + os.path.join(ROOT, "somewhere/else/retplan.db"),
              cfg.database_url)


def test_importer():
    rows = parse("symbol,shares,cost basis,account\nVTI,10,2000,Roth\nBND,5,,IRA\n")
    check("header columns are recognised", [(x.symbol, x.quantity, x.cost_basis, x.account)
                                            for x in rows] ==
          [("VTI", 10.0, 2000.0, "Roth"), ("BND", 5.0, None, "IRA")])
    rows = parse("aapl\t10\t1,500.50\tBrokerage\tEquity\nmsft;x")
    check("tab separated without header", rows[0].symbol == "AAPL" and rows[0].cost_basis == 1500.5
          and rows[0].asset_class == "equity")
    rows = parse("VTI, 10\nBAD\n, 5\nX, abc")
    check("bad lines carry a reason", [bool(x.error) for x in rows] == [False, True, True, True],
          [(x.symbol, x.error) for x in rows])
    rows = parse("Account Name,Ticker Symbol,Qty held,Total cost\nRoth,VTI,12,3000")
    check("loose broker headers are recognised",
          [(x.symbol, x.quantity, x.cost_basis, x.account) for x in rows] == [("VTI", 12.0, 3000.0, "Roth")],
          [(x.symbol, x.quantity, x.cost_basis, x.account, x.error) for x in rows])
    rows = parse("Ticker;Quantity\nVOD.L;1000")
    check("semicolons with a header", rows[0].symbol == "VOD.L" and rows[0].quantity == 1000)


# ------------------------------------------------------------------ projection
def _asset(sym, value, cls="equity", mu=None, sigma=None, seed=1, days=400):
    h = synthetic(sym, days=days, seed=seed)
    return AssetInput(sym, sym, cls, value, [(b.date, b.adj_close) for b in h.bars],
                      mu, sigma, 20.0 if mu is not None else None)


def test_projection_closed_forms():
    # cash only, no volatility: grows exactly at its assumption
    s = Settings(years=10, trials=200, rebalance="none", overrides={"CASH": {"sigma": 1e-9}})
    r = simulate([AssetInput("CASH", "Cash", "cash", 1000.0)], s)
    want = 1000 * (1 + CLASSES["cash"]["mu"]) ** 10
    check("cash compounds at its assumption", close(r["summary"]["end_nominal"]["p50"], want, 1e-6),
          f"{r['summary']['end_nominal']['p50']} vs {want}")
    check("the expected path agrees", close(r["expected"][-1], want, 1e-6))
    check("real value deflates by inflation",
          close(r["summary"]["end_real"]["p50"], want / 1.025 ** 10, 1e-6))
    # contributions with zero volatility: an exact annuity on a quarterly clock
    s = Settings(years=5, trials=200, rebalance="none", inflation=0.0,
                 flows=[CashFlow("contribution", 4000, 1, 5, indexed=False)],
                 overrides={"CASH": {"mu": 0.0, "sigma": 1e-9}})
    r = simulate([AssetInput("CASH", "Cash", "cash", 1000.0)], s)
    check("contributions add up exactly at zero return",
          close(r["summary"]["end_nominal"]["p50"], 21000.0, 1e-6))
    check("the yearly table records contributions", close(r["periods"][0]["contrib"], 4000.0))
    # withdrawals: 1000 at 0% with 300/yr runs out in year 4
    s = Settings(years=6, trials=200, rebalance="none", inflation=0.0,
                 flows=[CashFlow("withdrawal", 300, 1, 6, indexed=False)],
                 overrides={"CASH": {"mu": 0.0, "sigma": 1e-9}})
    r = simulate([AssetInput("CASH", "Cash", "cash", 1000.0)], s)
    dep = [p["p_depleted"] for p in r["periods"]]
    check("withdrawals exhaust the portfolio when they should",
          dep[:3] == [0.0, 0.0, 0.0] and dep[3] == 1.0 and r["summary"]["p_depleted"] == 1.0, dep)
    check("a depleted portfolio ends at zero", r["summary"]["end_nominal"]["p50"] == 0.0)
    # a percentage withdrawal at zero return
    s = Settings(years=2, trials=200, rebalance="none", inflation=0.0, withdrawal_rate=0.04,
                 overrides={"CASH": {"mu": 0.0, "sigma": 1e-9}})
    r = simulate([AssetInput("CASH", "Cash", "cash", 1000.0)], s)
    check("a % withdrawal compounds quarterly", close(r["summary"]["end_nominal"]["p50"],
                                                      1000 * 0.99 ** 8, 1e-9))
    # fee drag
    s = Settings(years=10, trials=200, rebalance="none", fee=0.01,
                 overrides={"CASH": {"mu": 0.0, "sigma": 1e-9}})
    r = simulate([AssetInput("CASH", "Cash", "cash", 1000.0)], s)
    check("a 1% fee takes 1% a year", close(r["summary"]["end_nominal"]["p50"], 1000 * 0.99 ** 10, 1e-9))


def test_projection_statistics():
    a = [_asset("EQ", 100000.0, "equity", 0.07, 0.17)]
    ov = {"EQ": {"mu": 0.07, "sigma": 0.17}}
    means, medians = {}, {}
    for m in ("parametric", "fat_tails", "bootstrap"):
        r = simulate(a, Settings(years=20, trials=20000, method=m, overrides=ov, seed=11))
        means[m] = r["summary"]["end_mean"]
        medians[m] = r["summary"]["end_nominal"]["p50"]
        p = r["periods"][-1]["nominal"]
        check(f"{m}: percentiles are ordered",
              p["p5"] <= p["p10"] <= p["p25"] <= p["p50"] <= p["p75"] <= p["p90"] <= p["p95"])
    want = 100000 * 1.07 ** 20
    for m in means:
        check(f"{m}: mean ending value matches (1+mu)^T within 4%",
              abs(means[m] / want - 1) < 0.04, f"{means[m]:.0f} vs {want:.0f}")
    s2 = math.log1p(0.17 ** 2 / 1.07 ** 2)
    med = 100000 * math.exp(20 * (math.log(1.07) - 0.5 * s2))
    check("parametric median matches the lognormal closed form within 2%",
          abs(medians["parametric"] / med - 1) < 0.02, f"{medians['parametric']:.0f} vs {med:.0f}")
    check("the three models agree on the median within 5%",
          max(medians.values()) / min(medians.values()) < 1.05, medians)
    # realised volatility of annual returns matches the input
    r = simulate(a, Settings(years=30, trials=4000, overrides=ov, seed=5))
    rets = [p["ret"] for p in r["periods"]]
    check("annual returns centre near the assumption",
          abs(np.mean([x["p50"] for x in rets]) - (math.exp(math.log(1.07) - 0.5 * s2) - 1)) < 0.01)


def test_projection_structure():
    a = [_asset("EQ", 60000.0, "equity", 0.09, 0.15, seed=1),
         _asset("BD", 40000.0, "bond", 0.035, 0.05, seed=2)]
    r = simulate(a, Settings(years=3, frequency="quarterly", trials=500, target=150000))
    check("quarterly reporting gives four rows a year", len(r["periods"]) == 12)
    check("quarter labels carry the quarter", r["periods"][0]["label"].endswith(("Q1", "Q2", "Q3", "Q4")))
    check("goal probability is non-decreasing over time",
          all(x["p_target"] <= y["p_target"] + 1e-12 for x, y in zip(r["periods"], r["periods"][1:])))
    check("three representative futures are kept",
          set(r["representative"]) == {"p10", "p50", "p90"} and len(r["representative"]["p50"]) == 12)
    check("risk shares sum to one", close(sum(x["risk_share"] for x in r["assets"]), 1.0, 1e-9))
    models, corr, _ = estimate(a, Settings())
    check("the correlation matrix is symmetric with a unit diagonal",
          np.allclose(corr, corr.T) and np.allclose(np.diag(corr), 1.0))
    check("the blend puts half weight on 20 years of history",
          close(models[0].mu, 0.5 * CLASSES["equity"]["mu"] + 0.5 * 0.09))
    r1 = simulate(a, Settings(years=10, trials=1000, seed=3))
    r2 = simulate(a, Settings(years=10, trials=1000, seed=3))
    check("the same seed gives the same answer",
          r1["summary"]["end_nominal"] == r2["summary"]["end_nominal"])
    try:
        simulate([AssetInput("X", "x", "equity", 0.0)], Settings())
        refused = False
    except ValueError:
        refused = True
    check("a portfolio with no value is refused with a reason", refused)


def test_stress():
    a = [AssetInput("EQ", "EQ", "equity", 100.0)]
    rep = replay(a, "gfc", Settings(rebalance="none"))
    want = float(np.prod([1 + x for x in SCENARIOS["gfc"]["returns"]["equity"]]))
    check("a 100% equity replay compounds the index path",
          close(rep["end_of_crisis"] / 100.0, want, 1e-9))
    check("the drawdown is the worst point",
          close(rep["drawdown"], min(rep["path"]) / 100 - 1))
    em = class_path("gfc", "em_equity")
    check("a beta above one deepens the fall",
          min(em) < min(SCENARIOS["gfc"]["returns"]["equity"]))
    r = simulate(a, Settings(years=3, frequency="quarterly", trials=300, stress="gfc",
                             overrides={"EQ": {"sigma": 0.17}}))
    q = SCENARIOS["gfc"]["returns"]["equity"]
    check("a stressed projection opens with the crisis in every trial",
          close(r["periods"][0]["nominal"]["p10"], r["periods"][0]["nominal"]["p90"], 1e-9)
          and close(r["periods"][0]["ret"]["p50"], q[0], 1e-9))


def test_rebalance():
    from portfolio.repository import Position, Valuation
    def pos(sym, cls, value):
        p = Position(1, sym, sym, 1, None, "", cls, "", 1.0, 1.0, None, "USD", None)
        p.value = value
        return p
    v = Valuation(positions=[pos("A", "equity", 70.0), pos("B", "bond", 30.0)], total=100.0)
    rb = rebalance(v, {"equity": 0.6, "bond": 0.4}, new_money=10.0)
    trades = {x["key"]: x["trade"] for x in rb["rows"]}
    check("rebalancing trades sum to the new money", close(sum(trades.values()), 10.0))
    check("rebalancing reaches the target", close(trades["equity"], -4.0) and close(trades["bond"], 14.0))
    cf = {x["key"]: x["cashflow_trade"] for x in rb["rows"]}
    check("new-money-only never sells", all(x >= 0 for x in cf.values()) and close(sum(cf.values()), 10.0))


# ------------------------------------------------------------------ plans, wizard
def test_plan_store_and_wizard():
    from retplan.engine import Projection
    from web import wizard
    from web.store import PlanStore
    db = fresh_db()
    with tempfile.TemporaryDirectory() as d:
        from retplan.plan import save_plan
        from retplan.samples import sample_plan
        legacy = sample_plan()
        legacy.label = "Old file"
        save_plan(legacy, os.path.join(d, "abc123.json"))
        s = PlanStore(db, legacy_dir=d)
        check("a legacy JSON plan is imported on first sight", s.get("abc123").label == "Old file")
    s = PlanStore(db)
    first = s.active_id("w")
    s.duplicate("w", first, "Copy")
    check("duplicating activates the copy", s.get("w").label == "Copy" and s.active_id("w") != first)
    s.activate("w", first)
    check("activate switches back", s.active_id("w") == first)
    s.set_results("w", {"x": 1})
    p = s.get("w")
    s.put("w", p)
    check("editing a plan drops its cached results", s.results("w") is None)
    s.delete("w", first)
    check("deleting the active plan activates another", len(s.scenarios("w")) == 1)
    try:
        s.delete("w", s.active_id("w"))
        kept = False
    except ValueError:
        kept = True
    check("the last plan cannot be deleted", kept)
    a = dict(wizard.DEFAULTS, partner="1", mortgage="100000", risk="growth", tax="flat",
             flat_rate="25")
    for step, *_ in wizard.STEPS:
        check(f"wizard defaults validate: {step}", wizard.validate(step, a) == [])
    bad = dict(a, age="70", retire_age="60")
    check("wizard refuses retirement before today", wizard.validate("you", bad) != [])
    plan = wizard.build_plan(a)
    check("the wizard's plan has two people and a loan", len(plan.persons) == 2 and len(plan.loans) == 1)
    check("every account's allocation sums to one",
          all(close(sum(l.weights), 1.0) for l in plan.ledgers))
    check("flat tax becomes one band", plan.tax.ordinary.rates == [0.25])
    spend_now = sum(e.amount for e in plan.expenses if e.start_age < plan.persons[0].retire_age)
    check("working-years spending equals the answer", close(spend_now, float(a["spend"])))
    res = Projection(plan).run(200, seed=1)
    check("the wizard's plan runs", np.isfinite(res.net_worth).all())


def test_plan_dialogs():
    """The card view and the step-by-step dialog: add, edit, copy, pause, remove."""
    from fastapi.testclient import TestClient
    from web.config import Config
    from web.retplan_webapp import RetPlanWebApp
    with tempfile.TemporaryDirectory() as d:
        cfg = Config(data_dir=d, database_url=DB_URL if DB_URL != "sqlite://"
                     else f"sqlite:///{d}/web.db", prices_enabled=False)
        wa = RetPlanWebApp(config=cfg, start_scheduler=False)
        if DB_URL != "sqlite://":
            fresh_db()
        c = TestClient(wa.app, raise_server_exceptions=False)
        sections = ("income", "expenses", "debt", "accounts", "care", "conversions")
        bad = []
        for s in sections:
            for u in (f"/plan/{s}", f"/plan/{s}?view=table", f"/plan/{s}/dialog",
                      f"/plan/{s}/dialog?partial=1", f"/plan/{s}/dialog?i=0&partial=1"):
                if c.get(u).status_code != 200:
                    bad.append(u)
        check("every card view, table view and dialog renders", not bad, bad)
        page = c.get("/plan/income").text
        check("income shows as cards with an Add button", "item-card" in page
              and "data-dialog" in page and 'id="rp-dialog"' in page)
        kinds = c.get("/plan/income/dialog?partial=1").text
        check("adding starts by asking what kind", "What would you like to add?" in kinds
              and "A public pension" in kinds and "<html" not in kinds)
        form = c.get("/plan/income/dialog?kind=public&partial=1").text
        check("a kind opens its steps, pre-filled", "data-stepper" in form
              and 'value="Public pension"' in form and "More options" in form)
        check("the dialog also works as a page without script",
              "<html" in c.get("/plan/income/dialog?kind=public").text)

        n0 = len(c.get("/plan/income").text.split('class="item-card')) - 1
        r = c.post("/plan/income/item", data={"i": "-1", "kind": "public", "label": "My pension",
                                              "amount": "12000", "start_age": "67",
                                              "end_age_life": "1"}, follow_redirects=False)
        check("saving a new item redirects to the list", r.status_code == 303)
        page = c.get("/plan/income").text
        n1 = len(page.split('class="item-card')) - 1
        check("the new income appears as a card", n1 == n0 + 1 and "My pension" in page
              and "12,000 a year" in page and "for life" in page)
        check("its preset category is kept", "public pension" in page)
        i = n1 - 1
        c.post("/plan/income/item", data={"i": str(i), "label": "My pension", "amount": "15000",
                                          "start_age": "68", "end_age": "90",
                                          "taxable_fraction": "50"})
        page = c.get("/plan/income").text
        check("editing changes only that item", "15,000 a year" in page and "age 68 to 90" in page
              and len(page.split('class="item-card')) - 1 == n1)
        r = c.post("/plan/income/item", data={"i": str(i), "start_age": "70", "end_age": "60"},
                   follow_redirects=True)
        check("an end before the start is refused", "Nothing was saved" in r.text
              and "age 68 to 90" in r.text)
        c.post(f"/plan/income/item/{i}/copy")
        check("duplicate adds a copy", "My pension (copy)" in c.get("/plan/income").text)
        c.post(f"/plan/income/item/{i}/toggle")
        page = c.get("/plan/income").text
        check("pause marks the item paused", "item-card paused" in page)
        c.post(f"/plan/income/item/{i + 1}/delete")
        c.post(f"/plan/income/item/{i}/delete")
        page = c.get("/plan/income").text
        check("remove deletes it", "My pension" not in page)

        # a one-off spending item is a one-year stream at the age given
        c.post("/plan/expenses/item", data={"i": "-1", "kind": "oneoff", "label": "Wedding",
                                            "amount": "30000", "essential": "0",
                                            "start_age": "50", "once": "1"})
        page = c.get("/plan/expenses?view=table").text
        check("a one-off is saved for one year", 'value="Wedding"' in page)
        cards = c.get("/plan/expenses").text
        check("its card says it can be trimmed", "Wedding" in cards and "could be cut" in cards)

        # accounts: a named mix sets the weights
        c.post("/plan/accounts/item", data={"i": "-1", "kind": "w1", "label": "New pension",
                                            "opening": "1000", "mix": "growth"})
        cards = c.get("/plan/accounts").text
        check("an account added with a mix shows its share of shares",
              "New pension" in cards and "85% shares" in cards)
        n_acc = len(cards.split('class="item-card')) - 1
        c.post(f"/plan/accounts/item/{n_acc - 1}/delete")
        check("removing an account", "New pension" not in c.get("/plan/accounts").text)

        # conversions refuse the same account at both ends
        r = c.post("/plan/conversions/item", data={"i": "-1", "label": "X", "from_ledger": "0",
                                                   "to_ledger": "0", "amount": "1000",
                                                   "start_age": "60", "end_age": "65"},
                   follow_redirects=True)
        check("a conversion needs two accounts", "two different accounts" in r.text)
        r = c.post("/plan/nonsense/item", data={}, follow_redirects=False)
        check("an unknown section is refused", r.status_code == 303)


def test_accounts_and_draw_rate():
    """Accounts by type in the quick start, and the suggested draw rate."""
    from web import drawrate, wizard
    from retplan.engine import Projection
    a = dict(wizard.DEFAULTS, partner="1", has_ira="1", ira_p2="40000", ira_save_p2="3000",
             has_roth401k="1", roth401k="10000", roth401k_save="5", roth401k_match="2",
             has_hsa="1", hsa="6000", hsa_save="2000")
    plan = wizard.build_plan(a)
    by = {lg.label: lg for lg in plan.ledgers}
    wr = lambda lg: plan.wrappers[lg.wrapper]
    check("each ticked type becomes an account, per owner where personal",
          {"Your 401(k) / 403(b)", "Partner's Traditional IRA", "Your Roth 401(k)", "HSA",
           "Brokerage", "Savings and CDs", "Your Roth IRA"} <= set(by), sorted(by))
    k401, ira, roth = by["Your 401(k) / 403(b)"], by["Partner's Traditional IRA"], by["Your Roth IRA"]
    check("a 401(k) is deductible, taxed out, with required withdrawals and a penalty",
          wr(k401).contribution_deductible == 1 and wr(k401).withdrawal_taxable_fraction == 1
          and wr(k401).mrd_divisors and wr(k401).early_age == 59.5)
    check("a Roth is tax-free out with no required withdrawals",
          wr(roth).withdrawal_taxable_fraction == 0 and not wr(roth).mrd_divisors)
    check("the partner's IRA is theirs and saves a fixed amount",
          ira.owner == 1 and ira.contribution == 3000 and ira.contribution_pct_income == 0)
    check("a 401(k) saves a share of pay with the employer's match",
          k401.contribution_pct_income == 0.08 and k401.employer_match_cap_pct == 0.04)
    check("unspent income is swept into the brokerage account",
          plan.ledgers[plan.policy.sweep_ledger].label == "Brokerage")
    check("US tax: brackets over a joint standard deduction",
          plan.tax.ordinary.lowers[1] == 32200 and plan.tax.ordinary.rates[1] == 0.10)
    check("Social Security is 85% taxable under US tax",
          all(r.taxable_fraction == 0.85 for r in plan.income if r.category == "state_pension"))
    check("wizard savings validate", wizard.validate("savings", a) == [])
    check("a saving rate over 100% of pay is refused",
          wizard.validate("savings", dict(a, k401_save="120")) != [])
    alone = wizard.build_plan(dict(wizard.DEFAULTS, has_brokerage="", brokerage="0",
                                   brokerage_save="0"))
    check("without a brokerage account one is made for unspent income",
          any(lg.label.startswith("Brokerage") for lg in alone.ledgers))

    # a spending row handed over at retirement is not counted twice that year
    one = wizard.build_plan(wizard.DEFAULTS)
    proj = Projection(one)
    k = int(one.persons[0].retire_age - one.persons[0].age)
    spend = proj.ess_real + proj.disc_real
    check("the retirement year's spending is the retirement level, not both",
          abs(spend[k] - 40000 * 0.8) < 1 and abs(spend[k - 1] - 40000) < 1,
          f"{spend[k - 1]:.0f}, {spend[k]:.0f}")

    d = drawrate.suggest(one, trials=500)
    c, s_, b = d["cautious"], d["suggested"], d["bold"]
    check("the draw rate is found for the first year without pay",
          d["age"] == one.persons[0].retire_age + 1 and d["savings"] > 0, d["age"])
    check("cautious <= suggested <= bold", c and s_ and b and c["rate"] <= s_["rate"] <= b["rate"],
          (c and c["rate"], s_ and s_["rate"], b and b["rate"]))
    check("a plan below its target is told to draw less",
          d["now"]["success"] < d["target"] and s_["rate"] < d["now"]["rate"])
    q = drawrate.scale_retirement(one, 0.5, d["age"])
    pq = Projection(q)
    sq = pq.ess_real + pq.disc_real
    check("scaling retirement spending leaves the working years alone",
          abs(sq[k - 1] - spend[k - 1]) < 1e-6 and abs(sq[k + 1] - 0.5 * spend[k + 1]) < 1e-6)
    import time as _t
    t0 = _t.time()
    drawrate.suggest(one)
    check("the suggestion takes a few seconds at most", _t.time() - t0 < 8, _t.time() - t0)


def test_draw_rate_web():
    """The savings step by account type; the draw rate after a simulation."""
    from fastapi.testclient import TestClient
    from web.config import Config
    from web.retplan_webapp import RetPlanWebApp
    with tempfile.TemporaryDirectory() as d:
        cfg = Config(data_dir=d, database_url=DB_URL if DB_URL != "sqlite://"
                     else f"sqlite:///{d}/web.db", prices_enabled=False)
        wa = RetPlanWebApp(config=cfg, start_scheduler=False)
        if DB_URL != "sqlite://":
            fresh_db()
        c = TestClient(wa.app, raise_server_exceptions=False)
        page = c.get("/start?step=savings").text
        check("the savings step asks by account type",
              all(x in page for x in ("401(k) / 403(b)", "Roth IRA", "Roth 401(k)", "HSA",
                                      'name="has_k401"', 'data-reveal="acct-k401"')))
        # with script, an unticked type's inputs are disabled and so not posted
        c.post("/start/savings", data={"has_k401": "1", "k401": "90000", "k401_save": "6",
                                       "k401_match": "3", "has_ira": "1", "ira": "25000",
                                       "ira_save": "7000", "go": "next"})
        review = c.get("/start?step=review").text
        check("ticked accounts reach the review", "Traditional IRA" in review
              and "25,000" in review and "401(k)" in review)
        check("unticked accounts are cleared", "Roth IRA" not in review and "Brokerage" not in review)
        # without script, typed figures count even when not ticked
        c.post("/start/savings", data={"k401": "90000", "roth_ira": "5000", "go": "next"})
        check("typed figures count without a tick", "Roth IRA" in c.get("/start?step=review").text)

        r = c.post("/api/simulate", json={"trials": 300})
        check("the simulation answers with a draw rate", r.status_code == 200
              and r.json().get("draw_rate") is not None, r.text[:200])
        dash = c.get("/dashboard").text
        check("the dashboard shows the suggested draw rate", "Suggested draw rate" in dash
              and "dr-scale" in dash and "Try " in dash)
        r = c.post("/drawrate/try", follow_redirects=True)
        check("trying the rate makes a scenario and switches to it",
              "draw rate" in r.text and "Saved and switched" in r.text)


# ------------------------------------------------------------------ web
def test_web():
    from fastapi.testclient import TestClient
    from web.config import Config
    from web.retplan_webapp import RetPlanWebApp
    with tempfile.TemporaryDirectory() as d:
        cfg = Config(data_dir=d, database_url=DB_URL if DB_URL != "sqlite://"
                     else f"sqlite:///{d}/web.db", prices_enabled=False)
        wa = RetPlanWebApp(config=cfg, start_scheduler=False)
        if DB_URL != "sqlite://":
            fresh_db()
        fake = FakeYahoo({"VTI": synthetic("VTI", seed=1),
                          "BND": synthetic("BND", mu=0.03, sigma=0.05, seed=2,
                                           name="Vanguard Total Bond Market ETF")})
        wa.collector._fetch, wa.collector._long_run, wa.collector._pause = \
            fake.fetch, fake.long_run, 0
        c = TestClient(wa.app, raise_server_exceptions=False)
        pages = ["/", "/about", "/method", "/help", "/dashboard", "/plan/household",
                 "/plan/income", "/plan/accounts", "/plan/markets", "/reports/cashflow",
                 "/audit", "/start", "/start?step=review", "/scenarios", "/compare",
                 "/portfolios", "/portfolios/new", "/prices", "/system", "/search?q=tax",
                 "/healthz"]
        bad = [(u, c.get(u).status_code) for u in pages]
        bad = [x for x in bad if x[1] != 200]
        check("every top-level page renders", not bad, bad)
        r = c.post("/portfolios/new", data={"name": "T", "currency": "USD",
                                            "holdings": "VTI, 10, 2000\nBND, 20\nCASH, 500"},
                   follow_redirects=False)
        pid = int(r.headers["location"].rsplit("/", 1)[-1])
        time.sleep(0.5)                     # the background fetch for new symbols
        wa.collector.collect(reason="test")
        pages = [f"/portfolios/{pid}", f"/portfolios/{pid}/project", f"/portfolios/{pid}/stress",
                 "/securities/VTI"]
        bad = [(u, c.get(u).status_code) for u in pages]
        check("portfolio pages render", all(s == 200 for _, s in bad), bad)
        r = c.post(f"/portfolios/{pid}/project", data={
            "years": "12", "frequency": "annual", "method": "fat_tails", "trials": "1000",
            "target": "5000", "flow-0-kind": "contribution", "flow-0-amount": "1200",
            "flow-0-start": "1", "flow-0-end": "12", "flow-0-indexed": "1",
            "inflation": "2.5", "fee": "0.1", "rebalance": "annual"}, follow_redirects=True)
        check("a projection runs from the form", r.status_code == 200 and "Year by year" in r.text)
        rid = int(re.search(r"run=(\d+)", str(r.url)).group(1))
        csv = c.get(f"/portfolios/{pid}/projections/{rid}.csv")
        check("the projection table downloads as CSV",
              csv.status_code == 200 and len(csv.text.strip().splitlines()) == 13)
        other = TestClient(wa.app, raise_server_exceptions=False)
        check("another browser cannot open the portfolio",
              other.get(f"/portfolios/{pid}").status_code == 404)
        r = c.post("/start/finish", data={"mode": "new"}, follow_redirects=True)
        check("the wizard builds a plan from defaults", r.status_code == 200)
        check("the new plan is a second scenario", len(wa.store.scenarios(
            next(iter({x["owner"] for x in wa.db.query("SELECT owner FROM plans")})))) >= 1)
        wa.db.dispose()


# ------------------------------------------------------------------ builder
def _fake_resolver():
    from portfolio import builder
    book = {"AAPL": ("Apple Inc.", "EQUITY", 200.0, "USD"),
            "MSFT": ("Microsoft Corporation", "EQUITY", 400.0, "USD"),
            "BND": ("Vanguard Total Bond Market Index Fund ETF", "ETF", 70.0, "USD"),
            "IVV": ("iShares Core S&P 500 ETF", "ETF", 700.0, "USD"),
            "VOD.L": ("Vodafone Group Plc", "EQUITY", 120.0, "GBp")}
    def fetch(sym, range_="5d", interval="1d"):
        if sym not in book:
            raise yahoo.YahooError("not found")
        n, t, px, cur = book[sym]
        return yahoo.History(symbol=sym, name=n, quote_type=t, currency=cur, price=px,
                             bars=[yahoo.Bar(date.today().isoformat(), px, px)])
    def search(q, limit=6):
        q = q.lower()
        if q == "us9219378356":
            return [{"symbol": "BND", "name": book["BND"][0], "type": "ETF", "exchange": "NGM"}]
        if "s&p 500" in q:
            return [{"symbol": "IVV", "name": book["IVV"][0], "type": "ETF", "exchange": "PCX"},
                    {"symbol": "SPY", "name": "SPDR S&P 500 ETF", "type": "ETF", "exchange": "PCX"}]
        return []
    return builder.Resolver(fetch=fetch, search=search)


def test_builder():
    import openpyxl
    from portfolio import builder
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Brokerage"
    ws.append(["Positions report"]); ws.append(["As of today"]); ws.append([])
    ws.append(["Ticker Symbol", "Security Description", "Qty held", "Last Price",
               "Market Value (USD)", "Avg Cost", "Asset Type"])
    ws.append(["NASDAQ:AAPL", "Apple Inc", 50, 200, 10000, 120, "Equity"])
    ws.append(["MSFT US Equity", "Microsoft Corp", 20, None, None, 300, "Equity"])
    ws.append(["", "iShares Core S&P 500 ETF", None, None, 7000, None, "Equity"])
    ws.append(["US9219378356", "Vanguard Total Bond Market ETF", 100, 70, 7000, 72, "Fixed Income"])
    ws.append(["SPAXX", "Fidelity Government Money Market", None, None, 4200, None, "Cash"])
    ws.append(["AAPL", "Apple Inc", 10, 200, 2000, 150, "Equity"])
    ws.append(["VOD.L", "Vodafone", 1000, 120, 120000, None, "Equity"])   # pence typed as pounds
    ws.append(["Subtotal", "", None, None, 31400, None, ""])
    ws2 = wb.create_sheet("Roth IRA")
    ws2.append(["Symbol", "Name", "Quantity", "Value", "Cost Basis"])
    ws2.append(["BND", "Vanguard Total Bond", 10, 700, 400])
    ws2.append(["ZZZZ", "Imaginary Holdings", 5, 500, 400])
    buf = io.BytesIO()
    wb.save(buf)
    d = builder.analyse(buf.getvalue(), "positions.xlsx", resolver=_fake_resolver())
    by = {(x["symbol"], x["account"]): x for x in d["lines"]}
    check("the header is found below a preamble", "row 4" in d["messages"][0], d["messages"])
    check("an exchange-prefixed symbol resolves", by[("AAPL", "Brokerage")]["confidence"] == "high")
    check("repeated lines merge", by[("AAPL", "Brokerage")]["quantity"] == 60
          and by[("AAPL", "Brokerage")]["merged"] == 2)
    check("per-share cost becomes a total",
          close(by[("AAPL", "Brokerage")]["cost"], 50 * 120 + 10 * 150))
    check("a Bloomberg-style ticker resolves", ("MSFT", "Brokerage") in by)
    ivv = by[("IVV", "Brokerage")]
    check("a name-only line is found by search", ivv["how"] == "name search"
          and len(ivv["alternatives"]) == 2)
    check("a missing quantity comes from value / price", close(ivv["quantity"], 10.0))
    check("an ISIN resolves", by[("BND", "Brokerage")]["how"] == "identifier")
    check("a money-market line becomes cash",
          by[("CASH", "Brokerage")]["quantity"] == 4200 and by[("CASH", "Brokerage")]["confidence"] == "cash")
    vod = by[("VOD.L", "Brokerage")]
    check("a pounds-versus-pence price is flagged",
          any("100×" in n for n in vod["notes"]) and vod["confidence"] != "high", vod["notes"])
    check("the sheet name becomes the account", ("BND", "Roth IRA") in by)
    check("a total-cost column sized like the position stays a total",
          by[("ZZZZ", "Roth IRA")]["cost"] == 400)
    z = by[("ZZZZ", "Roth IRA")]
    check("an unknown security is left unticked", z["confidence"] == "none" and not z["include"])
    check("subtotals are skipped", not any(x["raw_symbol"].lower() == "subtotal"
                                           for x in d["lines"]))
    # CSV without a header
    d = builder.analyse(b"AAPL,10,1500\nMSFT,5,1000\n", "x.csv", resolver=_fake_resolver())
    check("a headerless CSV is read as symbol, quantity, cost",
          [(x["symbol"], x["quantity"], x["cost"]) for x in d["lines"]] ==
          [("AAPL", 10.0, 1500.0), ("MSFT", 5.0, 1000.0)])
    d = builder.analyse(b"hello\nworld\n", "x.csv", resolver=_fake_resolver())
    check("a file with no positions says so", d["lines"] == [] and d["messages"])
    try:
        builder.read_sheets(b"\xd0\xcf\x11\xe0", "old.xls")
        refused = False
    except ValueError:
        refused = True
    check("old .xls files are refused with advice", refused)


def test_security_admin():
    from routes.security_routes import parse_prices
    db = fresh_db()
    r = PortfolioRepo(db)
    r.create_security("myfund", name="Private fund", currency="USD", asset_class="property",
                      source="manual")
    old = (date.today() - timedelta(days=500)).isoformat()
    got = r.put_prices("MYFUND", [(old, 50.0, None),
                                  ((date.today() - timedelta(days=10)).isoformat(), 100.0, None),
                                  (date.today().isoformat(), 104.0, None)])
    sec = r.security("MYFUND")
    check("typed prices set the latest price", sec["last_price"] == 104.0 and sec["prev_close"] == 100.0)
    check("typed prices past retention are skipped", got["too_old"] == 1 and got["stored"] == 2)
    r.delete_prices("MYFUND", [date.today().isoformat()])
    check("deleting the latest close rolls the price back", r.security("MYFUND")["last_price"] == 100.0)
    pid = r.create("w", "P")
    r.add_holding("w", pid, "MYFUND", 3)
    check("a manual security is never fetched", "MYFUND" not in r.tracked_symbols())
    try:
        r.delete_security("MYFUND")
        blocked = False
    except ValueError:
        blocked = True
    check("a held security cannot be deleted", blocked)
    r.delete("w", pid)
    r.delete_security("MYFUND")
    check("an unheld security is deleted with its prices",
          r.security("MYFUND") is None and r.price_stats_for("MYFUND") == 0)
    try:
        r.create_security("BAD SYMBOL!")
        rejected = False
    except ValueError:
        rejected = True
    check("an invalid symbol is rejected", rejected)
    rows, bad = parse_prices("date,close\n2026-01-02\t1,234.5\n2026-01-03\t12\t11.5\nnope,3\n2026-01-04,-1")
    check("price paste parses dates, thousands and tabs",
          rows == [("2026-01-02", 1234.5, None), ("2026-01-03", 12.0, 11.5)] and len(bad) == 2, (rows, bad))


def test_admin_gate():
    from fastapi.testclient import TestClient
    from web.admin import hash_password, verify_hash
    from web.config import Config
    from web.retplan_webapp import RetPlanWebApp
    check("password hashes verify and differ per salt",
          verify_hash("x" * 12, hash_password("x" * 12))
          and not verify_hash("y" * 12, hash_password("x" * 12))
          and hash_password("x" * 12) != hash_password("x" * 12))
    with tempfile.TemporaryDirectory() as d:
        wa = RetPlanWebApp(config=Config(data_dir=d, database_url=f"sqlite:///{d}/a.db",
                                         prices_enabled=False), start_scheduler=False)
        c = TestClient(wa.app, raise_server_exceptions=False)
        c.post("/securities/new", data={"symbol": "XYZ", "source": "manual"})
        check("a visitor cannot add a security", wa.portfolios.security("XYZ") is None)
        c.post("/admin/login", data={"username": "admin", "password": "wrong"})
        c.post("/admin/login", data={"username": "root", "password": "retplan-dev-admin"})
        c.post("/securities/new", data={"symbol": "XYZ", "source": "manual"})
        check("a wrong password or user name does not sign in",
              wa.portfolios.security("XYZ") is None)
        c.post("/admin/login", data={"username": "admin", "password": "retplan-dev-admin"})
        page = c.get("/securities").text
        check("the default admin can sign in", "administrator" in page)
        check("the default password is warned about on every page",
              "still uses the default password" in page
              and "still uses the default password" in c.get("/dashboard").text)
        c.post("/securities/new", data={"symbol": "XYZ", "source": "manual",
                                        "prices": f"{date.today().isoformat()},10"})
        check("an admin can add a manual security with prices",
              (wa.portfolios.security("XYZ") or {}).get("last_price") == 10.0)
        other = TestClient(wa.app, raise_server_exceptions=False)
        check("another browser is not admin, and sees no warning",
              "XYZ" not in other.get("/securities").text
              and "default password" not in other.get("/dashboard").text)
        c.post("/admin/password", data={"current": "wrong", "new": "a-much-better-one",
                                        "again": "a-much-better-one"})
        check("a password change needs the current password",
              wa.db.get_setting("admin.password_hash") is None)
        c.post("/admin/password", data={"current": "retplan-dev-admin", "new": "short",
                                        "again": "short"})
        check("a short password is refused", wa.db.get_setting("admin.password_hash") is None)
        c.post("/admin/password", data={"current": "retplan-dev-admin",
                                        "new": "a-much-better-one", "again": "a-much-better-one"})
        check("the new password is stored as a hash",
              str(wa.db.get_setting("admin.password_hash") or "").startswith("pbkdf2_sha256$"))
        check("the warning goes once it is changed",
              "default password" not in c.get("/dashboard").text)
        c.post("/admin/logout")
        c.post("/securities/XYZ/delete")
        check("after signing out, delete is refused", wa.portfolios.security("XYZ") is not None)
        c.post("/admin/login", data={"username": "admin", "password": "retplan-dev-admin"})
        c.post("/securities/XYZ/delete")
        check("the old default no longer signs in", wa.portfolios.security("XYZ") is not None)
        c.post("/admin/login", data={"username": "admin", "password": "a-much-better-one"})
        c.post("/securities/XYZ/delete")
        check("the new password signs in", wa.portfolios.security("XYZ") is None)
        wa.db.dispose()

def test_tools():
    from fastapi.testclient import TestClient
    from web import levers
    from web.config import Config
    from web.retplan_webapp import RetPlanWebApp
    from retplan.samples import sample_plan
    p = sample_plan()
    q = levers.apply(p, levers.Adjust(retire=2))
    check("retiring later moves the salaries that stopped at retirement",
          all(r.end_age == 67 for r in q.income if r.category == "employment"))
    q = levers.apply(p, levers.Adjust(claim=2))
    sp = [r for r in q.income if r.category == "state_pension"]
    check("claiming two years later raises the pension by 16%",
          all(close(r.amount, 11500 * 1.16) and r.start_age == 69 for r in sp))
    q = levers.apply(p, levers.Adjust(equity=0.1))
    check("more in shares keeps every allocation at 100%",
          all(close(sum(l.weights), 1.0) for l in q.ledgers))
    check("adjustments never touch the original plan", p.persons[0].retire_age == 65)
    with tempfile.TemporaryDirectory() as d:
        wa = RetPlanWebApp(config=Config(data_dir=d, database_url=f"sqlite:///{d}/t.db",
                                         prices_enabled=False), start_scheduler=False)
        c = TestClient(wa.app, raise_server_exceptions=False)
        c.get("/dashboard")
        r = c.post("/api/whatif", json={"spend": -0.1}).json()
        check("the what-if endpoint answers with base and adjusted odds",
              r["ok"] and r["adjusted"]["success"] >= r["base"]["success"] - 0.02
              and "spend 10% less" in r["describe"])
        r2 = c.post("/api/whatif", json={}).json()
        check("no adjustment gives the base answer", r2["adjusted"] == r2["base"])
        before = len(wa.store.scenarios(next(iter({x["owner"] for x in wa.db.query("SELECT owner FROM plans")}))))
        c.post("/api/whatif/save", json={"retire": 1})
        sid = next(iter({x["owner"] for x in wa.db.query("SELECT owner FROM plans")}))
        check("saving a what-if creates and opens a scenario",
              len(wa.store.scenarios(sid)) == before + 1 and "retire 1 year later" in wa.store.get(sid).label)
        L = c.post("/api/levers").json()
        check("the levers are ranked best first",
              L["ok"] and L["rows"] and all(a["delta"] >= b["delta"] for a, b in zip(L["rows"], L["rows"][1:])))
        pages = [c.get(u).status_code for u in ("/tools/claiming", "/tools/conversions",
                                                "/plan/conversions", "/help/tools")]
        check("the tool pages render", pages == [200] * 4, pages)
        idx = [i for i, r in enumerate(wa.store.get(sid).income) if r.category == "state_pension"][0]
        r = c.post("/tools/claiming", data={"row": idx, "from_age": 66, "to_age": 68,
                                            "early": 6.67, "late": 8})
        check("the claiming explorer compares each age", r.status_code == 200 and "Every age" in r.text)
        r = c.post("/tools/conversions", data={"src": 1, "dst": 3, "start": 65, "end": 70,
                                               "amounts": "10000", "fill": "", "heir": 25})
        check("the conversion explorer compares strategies",
              r.status_code == 200 and "Convert 10,000 a year" in r.text)
        c.post("/tools/conversions/add", data={"label": "Convert 10,000 a year", "src": 1, "dst": 3,
                                               "mode": "amount", "value": 10000, "start": 65, "end": 70})
        convs = wa.store.get(sid).conversions
        check("a chosen conversion is added to the plan",
              len(convs) == 1 and convs[0].amount == 10000 and convs[0].to_ledger == 3)
        check("the plan with a conversion still reconciles",
              "Balance roll-forward ties every year" in c.get("/audit").text
              and c.get("/dashboard").status_code == 200)
        wa.db.dispose()


def test_conventions():
    """MAYA's house rules, enforced: no inline script, every page's links resolve."""
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web", "templates")
    bad = []
    for dirpath, _, files in os.walk(root):
        for f in files:
            if not f.endswith(".html"):
                continue
            text = open(os.path.join(dirpath, f), encoding="utf-8").read()
            if re.search(r"<script(?![^>]*\bsrc=)[^>]*>", text) or \
                    re.search(r"\son(click|change|submit|input|load|keyup|keydown)=", text) or \
                    "javascript:" in text:
                bad.append(f)
    check("no inline script or event handler in any template", not bad, bad)
    from web.help_catalog import GUIDES, TOPICS
    missing = [s for s in TOPICS if not os.path.exists(os.path.join(root, "help", f"{s}.html"))]
    check("every help topic has a page", not missing, missing)
    gdir = os.path.join(root, "..", "guides")
    check("every guide has its Markdown file",
          all(os.path.exists(os.path.join(gdir, f"{g['slug']}.md")) for g in GUIDES))


def test_help_and_about():
    from fastapi.testclient import TestClient
    from web import cases
    from web.config import Config
    from web.help_catalog import GUIDES, TOPICS
    from web.retplan_webapp import RetPlanWebApp
    with tempfile.TemporaryDirectory() as d:
        wa = RetPlanWebApp(config=Config(data_dir=d, database_url=f"sqlite:///{d}/h.db",
                                         prices_enabled=False), start_scheduler=False)
        c = TestClient(wa.app, raise_server_exceptions=False)
        urls = (["/help", "/help/guides", "/help/case-studies", "/about", "/about/compare", "/"]
                + [f"/help/{s}" for s in TOPICS] + [f"/help/guides/{g['slug']}" for g in GUIDES]
                + [f"/help/case-studies/{x['slug']}" for x in cases.CASES])
        bad = [(u, c.get(u).status_code) for u in urls]
        bad = [b for b in bad if b[1] != 200]
        check(f"all {len(urls)} help, guide, case and about pages render", not bad, bad)
        check("the about page lists this release's highlights",
              "In this release" in c.get("/about").text and "Version 2.0.0" in c.get("/about").text)
        r = c.post("/help/case-studies/early-retirement/open", follow_redirects=True)
        check("a case study opens as the active scenario",
              r.status_code == 200 and "Case: retire at 60" in r.text)
        page = c.get("/").text
        check("the landing page carries its three figures",
              all(f'id="{i}"' in page for i in ("lpFutures", "lpSequence", "lpLedger")))
        wa.db.dispose()


def test_new_tools():
    from fastapi.testclient import TestClient
    from retplan.engine import Projection
    from retplan.plan import CareRisk
    from retplan.samples import sample_plan
    from web import levers
    from web.config import Config
    from web.retplan_webapp import RetPlanWebApp
    import copy
    # care risk: simulated future by future, expected on the fixed path
    p = sample_plan()
    q = copy.deepcopy(p)
    q.care = [CareRisk("LTC", 0, 0.5, 82, 88, 3, 90000, 0.0)]
    a, b = Projection(p).run(4000, seed=3), Projection(q).run(4000, seed=3)
    extra = (b.spend - a.spend).sum(axis=1)
    check("care happens in about its probability of futures", abs((extra > 1).mean() - 0.5) < 0.03)
    check("care costs its full amount where it happens", abs(extra.mean() - 135000) / 135000 < 0.05)
    f, g = copy.deepcopy(q), copy.deepcopy(p)
    for x in (f, g):
        x.market.mode, x.market.inflation.mode = "fixed", "fixed"
    check("the fixed-return path carries care's expected cost",
          close((Projection(f).run(1).spend - Projection(g).run(1).spend).sum(), 135000, 1e-6))
    check("a plan with care still reconciles", reconcile_ok(b))
    # spending check
    s = levers.spending_check(p)
    check("the spending check answers raise, hold or trim",
          s["verdict"] in ("raise", "hold", "trim") and s["rows"])
    check("success falls as spending rises",
          all(x["success"] >= y["success"] - 0.02 for x, y in zip(s["rows"], s["rows"][1:])))
    from web import cases
    retired = cases.plan_for(cases.get("drawdown-crash"))
    low = levers.spending_check(retired, savings=500000)
    check("for a retiree, a large fall in savings says trim",
          low["verdict"] == "trim" and low["change"] < 0, (low["verdict"], low["success"]))
    # draw order
    d = levers.draw_orders(p)
    check("every draw order of the plan's wrappers is screened", d["screened"] == 24)
    check("the current order is always a finalist", any(r["current"] for r in d["rows"]))
    q2 = levers.apply_draw_order(p, d["best"]["order"])
    liquid = [lg for lg in q2.ledgers if q2.wrappers[lg.wrapper].liquid]
    firsts = sorted(liquid, key=lambda lg: lg.withdraw_priority)
    check("applying an order puts its first wrapper first", firsts[0].wrapper == d["best"]["order"][0])
    # the pages, and net worth
    with tempfile.TemporaryDirectory() as dd:
        wa = RetPlanWebApp(config=Config(data_dir=dd, database_url=f"sqlite:///{dd}/n.db",
                                         prices_enabled=False), start_scheduler=False)
        c = TestClient(wa.app, raise_server_exceptions=False)
        pages = [c.get(u).status_code for u in ("/tools/spending", "/tools/draw-order",
                                                "/tools/health", "/networth", "/plan/care")]
        check("the new tool pages render", pages == [200] * 5, pages)
        r = c.post("/tools/spending", data={"savings": "745000", "lower": "70", "target": "85",
                                            "upper": "95"})
        check("the spending check page gives a verdict", r.status_code == 200 and "verdict" in r.text)
        r = c.post("/tools/draw-order", data={"heir": "25"})
        check("the draw-order page lists finalists", r.status_code == 200 and "finalists" in r.text)
        r = c.post("/tools/health", data={"bridge": "12000", "bridge_to": "65", "later": "4000",
                                          "later_from": "75", "growth": "2", "care_prob": "50",
                                          "care_from": "80", "care_to": "90", "care_years": "3",
                                          "care_cost": "80000", "care_all": "1"})
        check("the health test compares before and after", r.status_code == 200 and "was " in r.text)
        c.post("/tools/health/add", data={"care_prob": "40", "care_from": "80", "care_to": "90",
                                          "care_years": "2", "care_cost": "70000", "later": "3000",
                                          "later_from": "75", "growth": "2", "care_all": "1"})
        sid = wa.db.query("SELECT owner FROM plans LIMIT 1")[0]["owner"]
        plan = wa.store.get(sid)
        check("health costs and care risks are added to the plan",
              len(plan.care) == 2 and any("later life" in e.label for e in plan.expenses))
        today = date.today()
        c.post("/networth/snapshot", data={"taken_on": (today - timedelta(days=90)).isoformat(),
                                           "it-0-name": "Home", "it-0-kind": "asset", "it-0-value": "400000",
                                           "it-1-name": "Mortgage", "it-1-kind": "debt", "it-1-value": "150000"})
        c.post("/networth/snapshot", data={"taken_on": today.isoformat(),
                                           "it-0-name": "Joint brokerage", "it-0-kind": "account",
                                           "it-0-value": "130000", "it-0-ref": "0",
                                           "it-1-name": "Mortgage", "it-1-kind": "debt", "it-1-value": "140000",
                                           "it-1-ref": "0"})
        snaps = wa.networth.manual(sid)
        check("snapshots record assets, debts and net worth",
              len(snaps) == 2 and snaps[0]["net"] == 250000 and snaps[1]["net"] == -10000)
        c.post("/networth/snapshot", data={"taken_on": today.isoformat(),
                                           "it-0-name": "Home", "it-0-kind": "asset", "it-0-value": "410000"})
        check("a second snapshot on the same day replaces the first", len(wa.networth.manual(sid)) == 2)
        c.post(f"/networth/{snaps[1]['id']}/delete")
        c.post("/networth/snapshot", data={"taken_on": today.isoformat(),
                                           "it-0-name": "Joint brokerage", "it-0-kind": "account",
                                           "it-0-value": "130000", "it-0-ref": "0",
                                           "it-1-name": "Mortgage", "it-1-kind": "debt", "it-1-value": "140000",
                                           "it-1-ref": "0"})
        last = wa.networth.manual(sid)[-1]
        c.post(f"/networth/{last['id']}/to-plan")
        plan = wa.store.get(sid)
        check("a snapshot brings the plan's balances up to date",
              plan.ledgers[0].opening == 130000 and plan.loans[0].balance == 140000)
        check("the net-worth page shows the chart", "Net worth over time" in c.get("/networth").text)
        # portfolio values are recorded after a price run and kept
        fake = FakeYahoo({"VTI": synthetic("VTI", seed=1)})
        wa.collector._fetch, wa.collector._long_run, wa.collector._pause = fake.fetch, fake.long_run, 0
        pid = wa.portfolios.create(sid, "P")
        wa.portfolios.add_holding(sid, pid, "VTI", 10)
        wa.collector.collect(reason="test")
        check("each portfolio's value is recorded after a price run",
              str(pid) in wa.networth.portfolio_series(sid))
        wa.db.dispose()


def reconcile_ok(res):
    from retplan.metrics import reconcile
    return reconcile(res)["pass"]


def main():
    global DB_URL
    if "--database" in sys.argv:
        DB_URL = sys.argv[sys.argv.index("--database") + 1]
    t0 = time.time()
    print(f"database: {DB_URL}")
    test_schema_files(); test_schema_mismatch_detected()
    test_repository(); test_classify(); test_fx_helpers()
    test_prices_and_retention(); test_importer(); test_config()
    test_projection_closed_forms(); test_projection_statistics()
    test_projection_structure(); test_stress(); test_rebalance()
    test_plan_store_and_wizard(); test_builder(); test_security_admin()
    test_admin_gate(); test_tools(); test_conventions(); test_help_and_about()
    test_new_tools(); test_plan_dialogs(); test_accounts_and_draw_rate(); test_draw_rate_web(); test_web()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed in {time.time() - t0:.1f}s")
    for f in FAIL:
        print("  FAILED:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
