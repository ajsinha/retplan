"""Portfolios: selections of accounts, and of other portfolios.

    /portfolios                               list and create
    /portfolios/{pid}                         net worth, accounts, allocation, history
    /portfolios/{pid}/members                 choose its accounts and sub-portfolios
    /portfolios/{pid}/project                 Monte Carlo projection of investable assets
    /portfolios/{pid}/stress                  historical crisis replays on the current mix
    /securities/{symbol}                      one security: a year of prices, statistics
    /prices                                   the collector: status, securities, run log
    /api/tickers?q=                           symbol autocomplete
    /api/portfolios/{pid}                     valuation as JSON

Accounts are the workspace's (routes/account_routes.py); a portfolio holds
references to some of them, and may include other portfolios, whose accounts it
then includes too - each account counted once. Reading a portfolio reads its
accounts as they are now, so it is always current.
Everything is scoped to the browser's workspace; another workspace's portfolio
is a 404, never a 403, so ids reveal nothing.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import logging
import time
from datetime import date

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from portfolio import account_types as at
from portfolio import yahoo
from portfolio.assets import CASH_SYMBOL, CLASS_OPTIONS, CLASSES
from portfolio.checks import rebalance, run_checks
from portfolio.prices import collect_in_background
from portfolio.projection import (METHODS, REBALANCE, RETURN_SOURCES, CashFlow,
                                  Settings, assets_from_db, replay, simulate)
from portfolio.repository import NotFound, normalise_symbol
from portfolio.stress import SCENARIO_OPTIONS, SCENARIOS
from web import charts
from web.fastapi_compat import flash, flash_error_and_log, redirect_to, render
from web.portfolio_view import projection_csv, projection_view
from web.store import session_id

logger = logging.getLogger(__name__)
CURRENCIES = ["USD", "EUR", "GBP", "CAD", "AUD", "CHF", "JPY", "INR", "SGD", "HKD",
              "NZD", "SEK", "NOK", "DKK", "ZAR"]
_SEARCH_CACHE: dict[str, tuple[float, list]] = {}


def _f(form, key, default=None):
    raw = (form.get(key) or "").strip().replace(",", "").replace("%", "")
    if raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


class PortfolioRoutes:
    def __init__(self, app: FastAPI, store):
        self.app = app
        self.store = store
        self._register_routes()

    @property
    def repo(self):
        return self.app.state.portfolios

    def _register_routes(self) -> None:
        add = self.app.add_api_route
        r = dict(include_in_schema=False)
        add("/portfolios", self.index, methods=["GET"], name="portfolios", **r)
        add("/portfolios/new", self.new_form, methods=["GET"], name="portfolio_new", **r)
        add("/portfolios/new", self.create, methods=["POST"], name="portfolio_create", **r)
        add("/portfolios/{pid}", self.view, methods=["GET"], name="portfolio_view", **r)
        add("/portfolios/{pid}/edit", self.edit, methods=["POST"], name="portfolio_edit", **r)
        add("/portfolios/{pid}/delete", self.delete, methods=["POST"],
            name="portfolio_delete", **r)
        add("/portfolios/{pid}/duplicate", self.duplicate, methods=["POST"],
            name="portfolio_duplicate", **r)
        add("/portfolios/{pid}/record", self.record, methods=["POST"],
            name="portfolio_record", **r)
        add("/portfolios/{pid}/members", self.members, methods=["GET"],
            name="portfolio_members", **r)
        add("/portfolios/{pid}/members", self.save_members, methods=["POST"],
            name="portfolio_members_save", **r)
        add("/portfolios/{pid}/accounts/{aid}/remove", self.remove_account, methods=["POST"],
            name="portfolio_remove_account", **r)
        add("/portfolios/{pid}/parts/{cid}/remove", self.remove_part, methods=["POST"],
            name="portfolio_remove_part", **r)
        add("/portfolios/{pid}/refresh", self.refresh, methods=["POST"],
            name="portfolio_refresh", **r)
        add("/portfolios/{pid}/targets", self.save_targets, methods=["POST"],
            name="portfolio_targets", **r)
        add("/portfolios/{pid}/project", self.project, methods=["GET"],
            name="portfolio_project", **r)
        add("/portfolios/{pid}/project", self.run_projection, methods=["POST"],
            name="portfolio_project_run", **r)
        add("/portfolios/{pid}/projections/{rid}.csv", self.projection_csv,
            methods=["GET"], name="projection_csv", **r)
        add("/portfolios/{pid}/projections/{rid}/delete", self.delete_projection,
            methods=["POST"], name="projection_delete", **r)
        add("/portfolios/{pid}/stress", self.stress, methods=["GET"],
            name="portfolio_stress", **r)
        add("/prices", self.prices, methods=["GET"], name="prices", **r)
        add("/prices/run", self.prices_run, methods=["POST"], name="prices_run", **r)
        add("/api/tickers", self.api_tickers, methods=["GET"], name="api_tickers")
        add("/api/portfolios/{pid}", self.api_portfolio, methods=["GET"],
            name="api_portfolio")

    def _get(self, request, pid):
        """(workspace id, portfolio) or raise NotFound."""
        sid = session_id(request)
        return sid, self.repo.get(sid, int(pid))

    def _missing(self, request):
        return render(request, "error.html", status_code=404, code=404,
                      message="That portfolio does not exist in this workspace.")

    def _choices(self, sid, pid=None):
        """Every account, grouped by kind, and the portfolios that may be included
        in ``pid`` (none that would make it contain itself)."""
        accts = self.repo.accounts(sid)
        groups = [(key, label, icon, [a for a in accts if at.get(a["type"])["kind"] == key])
                  for key, label, icon, _ in at.KINDS]
        parts = [p for p in self.repo.list(sid)
                 if pid is None or self.repo.can_include(sid, pid, p["id"])]
        return groups, parts

    # -- list / create -----------------------------------------------------
    async def index(self, request: Request):
        sid = session_id(request)
        cards = []
        for p in self.repo.list(sid):
            v = self.repo.valuation(sid, p["id"])
            cards.append(dict(p, val=v, by_class=v.by("asset_class"),
                              parts=self.repo.children(sid, p["id"])))
        everything = self.repo.all_valuation(sid)
        return render(request, "portfolio/index.html", cards=cards, everything=everything,
                      n_accounts=len(everything.accounts),
                      scheduler=self.app.state.scheduler.status(),
                      last_run=self.repo.last_successful_run())

    async def new_form(self, request: Request):
        sid = session_id(request)
        groups, parts = self._choices(sid)
        return render(request, "portfolio/new.html", currencies=CURRENCIES, groups=groups,
                      parts=parts, home=self.repo.home_currency(sid))

    async def create(self, request: Request):
        sid = session_id(request)
        form = await request.form()
        try:
            pid = self.repo.create(sid, form.get("name") or "My portfolio",
                                   form.get("currency") or "USD",
                                   form.get("description") or "",
                                   accounts=[int(a) for a in form.getlist("accounts")
                                             if str(a).isdigit()])
            self.repo.set_children(sid, pid, [int(c) for c in form.getlist("parts")
                                              if str(c).isdigit()])
        except (NotFound, ValueError) as exc:
            flash(request, f"Could not create the portfolio: {exc}", "error")
            return redirect_to(request, "portfolio_new")
        collect_in_background(self.app.state.collector, self.repo.missing_fx_pairs(), "fx")
        return redirect_to(request, "portfolio_view", pid=pid, flash_message="Portfolio created.")

    # -- overview ----------------------------------------------------------
    async def view(self, request: Request, pid: int):
        try:
            sid, pf = self._get(request, pid)
        except NotFound:
            return self._missing(request)
        v = self.repo.valuation(sid, pid)
        direct = {a["id"] for a in self.repo.direct_accounts(sid, pid)}
        parts = self.repo.children(sid, pid)
        via = {}
        for ch in parts:
            for a in self.repo.accounts_in(sid, ch["id"]):
                via.setdefault(a["id"], ch["name"])
        secs = {p.symbol: (self.repo.security(p.symbol) or {}) for p in v.positions
                if not p.synthetic}
        hist = self.repo.value_history(sid, pid)
        chart_hist = charts.date_line(
            [d for d, _ in hist], [("Investable assets", [x for _, x in hist])],
            title="A year of value", desc="today's holdings and cash priced on each past day",
            y_fmt=charts._fmt_compact)
        change_1y = (hist[-1][1] / hist[0][1] - 1) if len(hist) > 1 and hist[0][1] else None
        nw_hist = self.app.state.networth.history(sid, pid)
        chart_nw = ""
        if len(nw_hist) >= 2:
            chart_nw = charts.date_line(
                [h["taken_on"] for h in nw_hist],
                [("Net worth", [h["net"] for h in nw_hist]),
                 ("Assets", [h["assets"] for h in nw_hist]),
                 ("Debts", [h["liabilities"] for h in nw_hist])],
                title="Net worth over time", desc="recorded every day prices are collected",
                y_fmt=charts._fmt_compact)
        targets = (pf["settings"] or {}).get("targets") or {}
        rb = rebalance(v, targets, _f(request.query_params, "new_money", 0.0) or 0.0) \
            if targets else None
        return render(request, "portfolio/view.html", pf=pf, v=v, secs=secs,
                      direct=direct, via=via, parts=parts,
                      parents=self.repo.parents(sid, pid),
                      chart_hist=chart_hist, hist=hist, change_1y=change_1y,
                      chart_nw=chart_nw, nw_hist=nw_hist,
                      by_class=v.by("asset_class"), by_account=v.by("account"),
                      by_tax=v.by_tax(), by_owner=v.by_owner(),
                      checks=run_checks(v, secs), classes=CLASS_OPTIONS,
                      class_info=CLASSES, targets=targets, rb=rb, kinds=at.KINDS,
                      currencies=CURRENCIES,
                      running=self.app.state.collector.running,
                      linked_plans=self._linked_plans(sid, pid),
                      plan_name=self.store.get(sid).label,
                      projections=self.repo.projections(sid, pid)[:3])

    def _linked_plans(self, sid, pid):
        out = []
        for sc in self.store.scenarios(sid):
            try:
                plan = self.store.get_by_id(sid, sc["id"])
            except LookupError:
                continue
            if plan.portfolio_id == pid:
                out.append(dict(sc, label=plan.label))
        return out

    async def edit(self, request: Request, pid: int):
        form = await request.form()
        try:
            sid, _ = self._get(request, pid)
            self.repo.update(sid, pid, name=(form.get("name") or "").strip() or "Portfolio",
                             currency=(form.get("currency") or "USD").upper(),
                             description=form.get("description") or "")
        except NotFound:
            return self._missing(request)
        collect_in_background(self.app.state.collector, self.repo.missing_fx_pairs(), "fx")
        return redirect_to(request, "portfolio_view", pid=pid, flash_message="Saved.")

    async def delete(self, request: Request, pid: int):
        try:
            sid, pf = self._get(request, pid)
        except NotFound:
            return self._missing(request)
        self.repo.delete(sid, pid)
        self.app.state.networth.forget(sid, pid)
        return redirect_to(request, "portfolios", flash_message=
                           f"Deleted '{pf['name']}'. Its accounts are untouched - they are "
                           "under Accounts, and in any other portfolio that has them.")

    async def duplicate(self, request: Request, pid: int):
        try:
            sid, _ = self._get(request, pid)
        except NotFound:
            return self._missing(request)
        new = self.repo.duplicate(sid, pid)
        return redirect_to(request, "portfolio_view", pid=new, flash_message=
                           "Copied: a new portfolio of the same accounts. Change its selection "
                           "freely - the accounts themselves are shared.")

    async def record(self, request: Request, pid: int):
        """Record today's net worth now, rather than waiting for the next price run."""
        from portfolio.networth import record_one
        try:
            sid, _ = self._get(request, pid)
        except NotFound:
            return self._missing(request)
        ok = record_one(self.repo, self.app.state.networth, sid, pid)
        record_one(self.repo, self.app.state.networth, sid)
        if ok:
            flash(request, "Today's net worth recorded.", "success")
        else:
            flash(request, "Nothing recorded: some holdings are not priced yet, or the "
                           "portfolio is empty.", "warning")
        return redirect_to(request, "portfolio_view", pid=pid)

    # -- what it is made of ------------------------------------------------
    async def members(self, request: Request, pid: int):
        try:
            sid, pf = self._get(request, pid)
        except NotFound:
            return self._missing(request)
        groups, parts = self._choices(sid, pid)
        return render(request, "portfolio/members.html", pf=pf, groups=groups, parts=parts,
                      partial=request.query_params.get("partial") == "1",
                      direct={a["id"] for a in self.repo.direct_accounts(sid, pid)},
                      children={c["id"] for c in self.repo.children(sid, pid)},
                      heading=pf["name"])

    async def save_members(self, request: Request, pid: int):
        form = await request.form()
        try:
            sid, pf = self._get(request, pid)
            self.repo.set_members(sid, pid, [int(a) for a in form.getlist("accounts")
                                             if str(a).isdigit()])
            self.repo.set_children(sid, pid, [int(c) for c in form.getlist("parts")
                                              if str(c).isdigit()])
        except NotFound:
            return self._missing(request)
        except ValueError as exc:
            flash(request, str(exc).capitalize() + ".", "error")
            return redirect_to(request, "portfolio_view", pid=pid)
        collect_in_background(self.app.state.collector, self.repo.missing_fx_pairs(), "fx")
        n = len(self.repo.accounts_in(sid, pid))
        return redirect_to(request, "portfolio_view", pid=pid, flash_message=
                           f"'{pf['name']}' is now {n} account{'' if n == 1 else 's'}.")

    async def remove_account(self, request: Request, pid: int, aid: int):
        try:
            sid, pf = self._get(request, pid)
        except NotFound:
            return self._missing(request)
        self.repo.remove_from_portfolio(sid, pid, aid)
        return redirect_to(request, "portfolio_view", pid=pid, flash_message=
                           f"Taken out of '{pf['name']}'. The account itself is untouched.")

    async def remove_part(self, request: Request, pid: int, cid: int):
        try:
            sid, pf = self._get(request, pid)
        except NotFound:
            return self._missing(request)
        self.repo.remove_child(sid, pid, cid)
        return redirect_to(request, "portfolio_view", pid=pid, flash_message=
                           f"No longer part of '{pf['name']}'.")

    async def refresh(self, request: Request, pid: int):
        try:
            sid, _ = self._get(request, pid)
        except NotFound:
            return self._missing(request)
        syms = sorted({h["symbol"] for h in self.repo.holdings_in(sid, pid)
                       if h["symbol"] != CASH_SYMBOL})
        syms = sorted(set(syms) | set(self.repo.fx_pairs_needed()))
        if not syms:
            flash(request, "Nothing to price - no securities are held.", "info")
        elif len(syms) <= 8:
            res = self.app.state.collector.collect(syms, reason="manual")
            flash(request, f"Prices refreshed: {res['ok']} updated"
                           + (f", {res['failed']} failed ({'; '.join(res['errors'][:3])})"
                              if res["failed"] else "") + ".",
                  "success" if not res["failed"] else "warning")
        else:
            collect_in_background(self.app.state.collector, syms, "manual")
            flash(request, f"Refreshing {len(syms)} symbols in the background; reload in "
                           "a moment.", "info")
        return redirect_to(request, "portfolio_view", pid=pid)

    async def save_targets(self, request: Request, pid: int):
        form = await request.form()
        try:
            sid, pf = self._get(request, pid)
        except NotFound:
            return self._missing(request)
        targets = {}
        for k in CLASSES:
            v = _f(form, f"t-{k}")
            if v:
                targets[k] = v / 100.0
        settings = dict(pf["settings"] or {})
        settings["targets"] = targets
        self.repo.update(sid, pid, settings=settings)
        total = sum(targets.values())
        msg = "Targets saved." if abs(total - 1) < 0.005 or not targets else \
            f"Targets saved (they add up to {total:.0%}; RetPlan scales them to 100%)."
        return redirect_to(request, "portfolio_view", pid=pid, flash_message=msg)

    # -- projection --------------------------------------------------------
    def _settings_from_form(self, form, current: Settings) -> Settings:
        s = Settings.from_dict(current.to_dict())
        s.years = int(_f(form, "years", s.years))
        s.frequency = form.get("frequency") or s.frequency
        s.trials = int(_f(form, "trials", s.trials))
        s.method = form.get("method") or s.method
        s.return_source = form.get("return_source") or s.return_source
        s.inflation = _f(form, "inflation", s.inflation * 100) / 100
        s.fee = _f(form, "fee", s.fee * 100) / 100
        s.rebalance = form.get("rebalance") or s.rebalance
        s.target = _f(form, "target", 0.0) or 0.0
        s.withdrawal_rate = (_f(form, "withdrawal_rate", 0.0) or 0.0) / 100
        s.stress = form.get("stress") or ""
        s.seed = int(_f(form, "seed", s.seed))
        flows = []
        keys = sorted({k.split("-")[1] for k in form.keys() if k.startswith("flow-")})
        for i in keys:
            amt = _f(form, f"flow-{i}-amount")
            if not amt:
                continue
            flows.append(CashFlow(
                kind=form.get(f"flow-{i}-kind") or "contribution", amount=abs(amt),
                start_year=int(_f(form, f"flow-{i}-start", 1)),
                end_year=int(_f(form, f"flow-{i}-end", s.years)),
                indexed=bool(form.get(f"flow-{i}-indexed")),
                growth=(_f(form, f"flow-{i}-growth", 0.0) or 0.0) / 100,
                label=(form.get(f"flow-{i}-label") or "").strip()))
        s.flows = flows
        overrides = {}
        for k in form.keys():
            if k.startswith("ov-mu-") or k.startswith("ov-sigma-"):
                kind, sym = k[3:].split("-", 1)
                val = _f(form, k)
                if val is not None:
                    overrides.setdefault(sym, {})[kind] = val / 100
        s.overrides = overrides
        return s.clamped()

    async def project(self, request: Request, pid: int):
        try:
            sid, pf = self._get(request, pid)
        except NotFound:
            return self._missing(request)
        settings = Settings.from_dict((pf["settings"] or {}).get("projection"))
        runs = self.repo.projections(sid, pid)
        run = None
        rid = request.query_params.get("run")
        try:
            if rid:
                run = self.repo.projection(sid, pid, int(rid))
            elif runs:
                run = self.repo.projection(sid, pid, runs[0]["id"])
        except (NotFound, ValueError):
            run = None
        basis = request.query_params.get("basis") or "real"
        view = projection_view(run["result"], basis) if run else None
        v = self.repo.valuation(sid, pid)
        return render(request, "portfolio/project.html", pf=pf, s=settings, run=run,
                      view=view, runs=runs, v=v, methods=METHODS, sources=RETURN_SOURCES,
                      rebalances=REBALANCE, stresses=SCENARIO_OPTIONS, basis=basis,
                      symbols=sorted({p.symbol for p in v.positions if p.value > 0}))

    async def run_projection(self, request: Request, pid: int):
        form = await request.form()
        try:
            sid, pf = self._get(request, pid)
        except NotFound:
            return self._missing(request)
        current = Settings.from_dict((pf["settings"] or {}).get("projection"))
        s = self._settings_from_form(form, current)
        settings = dict(pf["settings"] or {})
        settings["projection"] = s.to_dict()
        self.repo.update(sid, pid, settings=settings)
        t0 = time.time()
        try:
            assets = assets_from_db(self.repo, sid, pid)
            result = simulate(assets, s)
        except ValueError as exc:
            flash(request, str(exc).capitalize() + ".", "error")
            return redirect_to(request, "portfolio_project", pid=pid)
        except Exception as exc:  # noqa: BLE001
            flash_error_and_log(request, "The projection failed", exc)
            return redirect_to(request, "portfolio_project", pid=pid)
        result["seconds"] = round(time.time() - t0, 2)
        summary = dict(result["summary"], seconds=result["seconds"],
                       label=(form.get("label") or "").strip())
        rid = self.repo.save_projection(sid, pid, s.to_dict(), summary, result)
        return redirect_to(request, "portfolio_project", pid=pid, run=rid,
                           flash_message=f"{s.trials:,} trials over {s.years} years in "
                                         f"{result['seconds']}s.")

    async def projection_csv(self, request: Request, pid: int, rid: int):
        try:
            sid, pf = self._get(request, pid)
            run = self.repo.projection(sid, pid, rid)
        except NotFound:
            return self._missing(request)
        name = f"{pf['name']}-projection-{run['id']}".replace(" ", "-").lower()
        return Response(projection_csv(run["result"]), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})

    async def delete_projection(self, request: Request, pid: int, rid: int):
        try:
            sid, _ = self._get(request, pid)
        except NotFound:
            return self._missing(request)
        self.repo.delete_projection(sid, pid, rid)
        return redirect_to(request, "portfolio_project", pid=pid,
                           flash_message="Run deleted.")

    async def stress(self, request: Request, pid: int):
        try:
            sid, pf = self._get(request, pid)
        except NotFound:
            return self._missing(request)
        assets = assets_from_db(self.repo, sid, pid)
        settings = Settings.from_dict((pf["settings"] or {}).get("projection"))
        rows = []
        if assets:
            for key in SCENARIOS:
                r = replay(assets, key, settings)
                r["chart"] = charts.quarter_path(
                    r["path"], crisis_quarters=r["crisis_quarters"],
                    title=r["label"], desc="portfolio value by quarter; crisis shaded, "
                                           "then expected returns until it recovers")
                rows.append(r)
        return render(request, "portfolio/stress.html", pf=pf, rows=rows,
                      v=self.repo.valuation(sid, pid))

    # -- prices ------------------------------------------------------------
    async def prices(self, request: Request):
        """This workspace's symbols (and the FX pairs they need) - prices are
        shared, but what other workspaces hold is theirs."""
        sid = session_id(request)
        mine = {h["symbol"] for h in self.repo.all_holdings(sid)}
        secs = [s for s in self.repo.securities()
                if s["symbol"] in mine or s["symbol"].endswith("=X")]
        return render(request, "portfolio/prices.html", secs=secs,
                      runs=self.repo.runs(15), stats=self.repo.price_stats(),
                      scheduler=self.app.state.scheduler.status(),
                      config=self.app.state.config,
                      running=self.app.state.collector.running,
                      tracked=[s["symbol"] for s in secs if s["symbol"] != CASH_SYMBOL],
                      classes=CLASSES)

    async def prices_run(self, request: Request):
        if self.app.state.collector.running:
            flash(request, "A collection run is already in progress.", "info")
        else:
            collect_in_background(self.app.state.collector, None, "manual")
            flash(request, "Collection started in the background. Reload to see it finish.",
                  "success")
        return redirect_to(request, "prices")

    async def api_tickers(self, request: Request):
        q = (request.query_params.get("q") or "").strip()
        if not q:
            return {"results": []}
        key = q.lower()
        hit = _SEARCH_CACHE.get(key)
        if hit and time.time() - hit[0] < 600:
            return {"results": hit[1]}
        try:
            results = yahoo.search(q)
        except yahoo.YahooError as exc:
            return JSONResponse({"results": [], "error": str(exc)}, status_code=502)
        if len(_SEARCH_CACHE) > 500:
            _SEARCH_CACHE.clear()
        _SEARCH_CACHE[key] = (time.time(), results)
        return {"results": results}

    async def api_portfolio(self, request: Request, pid: int):
        try:
            sid, pf = self._get(request, pid)
        except NotFound:
            return JSONResponse({"error": "not found"}, status_code=404)
        v = self.repo.valuation(sid, pid)
        return {"id": pf["id"], "name": pf["name"], "currency": pf["currency"],
                "as_of": v.as_of, "total": v.total, "cost": v.cost,
                "day_change": v.day_change, "unpriced": v.unpriced,
                "net_worth": v.net_worth, "property": v.property_total, "debts": v.debts,
                "accounts": [dict(id=a.id, name=a.name, type=a.type, kind=a.kind,
                                  owner=a.owner_label, institution=a.institution,
                                  value=a.value, as_of=a.as_of, rate=a.rate,
                                  months_left=a.months_left) for a in v.accounts],
                "holdings": [dict(symbol=p.symbol, name=p.name, quantity=p.quantity,
                                  price=p.price, currency=p.currency, fx=p.fx,
                                  value=p.value, weight=p.weight, account=p.account,
                                  account_id=p.account_id, asset_class=p.asset_class,
                                  cost_basis=p.cost_basis)
                             for p in v.positions if not p.synthetic],
                "date": date.today().isoformat()}
