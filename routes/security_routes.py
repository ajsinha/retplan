"""Securities: look one up, and (as an administrator) add, amend or delete it.

    /securities                     the list, a live Yahoo lookup, and (admin) Add
    /securities/lookup?symbol=      inquiry: a year of prices and statistics for any
                                    symbol, straight from Yahoo, nothing stored
    /securities/{symbol}            one tracked security; admin tools beneath

Anyone may inquire. Changing the shared securities master - adding one, editing
its description or class, typing in or deleting prices, deleting it - needs an
administrator (web/admin.py). A security still held in any portfolio cannot be
deleted.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import logging
import math
from datetime import date

import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

from portfolio import yahoo
from portfolio.assets import CASH_SYMBOL, CLASS_OPTIONS, CLASSES, classify
from portfolio.fx import is_fx
from portfolio.repository import normalise_symbol
from web import charts
from portfolio import market
from portfolio.calendar import CALENDARS
from web.admin import admin_mode, is_admin
from web.fastapi_compat import flash, redirect_to, render
from web.store import session_id

logger = logging.getLogger(__name__)
QUOTE_TYPES = ["EQUITY", "ETF", "MUTUALFUND", "MONEYMARKET", "INDEX", "CRYPTOCURRENCY",
               "CURRENCY", "FUTURE", "BOND", "PRIVATE", "OTHER"]


def parse_prices(text: str) -> tuple[list, list]:
    """'date, close[, adjusted close]' per line (comma, tab or semicolon; a header
    line is skipped). Returns (rows, problems)."""
    rows, bad = [], []
    for n, line in enumerate((text or "").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        for sep in ("\t", ";", ","):
            if sep in line:
                parts = [x.strip() for x in line.split(sep)]
                break
        else:
            parts = line.split()
        try:
            d = date.fromisoformat(parts[0][:10]).isoformat()
        except (ValueError, IndexError):
            if n == 1:
                continue                      # a header row
            bad.append(f"line {n}: the date must look like 2026-09-29")
            continue
        try:
            close = float(parts[1].replace(",", ""))
            adj = float(parts[2].replace(",", "")) if len(parts) > 2 and parts[2] else None
        except (ValueError, IndexError):
            bad.append(f"line {n}: no price")
            continue
        if close <= 0 or (adj is not None and adj <= 0):
            bad.append(f"line {n}: prices must be positive")
            continue
        rows.append((d, close, adj))
    return rows, bad


def stats_for(closes: list[float]) -> dict:
    """One year of statistics from a list of (adjusted) closes."""
    if len(closes) < 21:
        return {}
    adj = np.asarray(closes, dtype=float)
    r = np.diff(np.log(adj))
    return dict(ret_1y=float(adj[-1] / adj[0] - 1),
                vol=float(r.std(ddof=1) * math.sqrt(252)),
                hi=float(adj.max()), lo=float(adj.min()),
                max_dd=float((adj / np.maximum.accumulate(adj) - 1).min()),
                days=len(adj))


class SecurityRoutes:
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
        add("/securities", self.index, methods=["GET"], name="securities", **r)
        add("/securities/lookup", self.lookup, methods=["GET"], name="security_lookup", **r)
        add("/securities/new", self.create, methods=["POST"], name="security_create", **r)
        add("/securities/{symbol}", self.view, methods=["GET"], name="security", **r)
        add("/securities/{symbol}/edit", self.edit, methods=["POST"],
            name="security_edit", **r)
        add("/securities/{symbol}/class", self.my_class, methods=["POST"],
            name="security_class", **r)
        add("/securities/{symbol}/prices", self.prices, methods=["POST"],
            name="security_prices", **r)
        add("/securities/{symbol}/refresh", self.refresh, methods=["POST"],
            name="security_refresh", **r)
        add("/securities/{symbol}/delete", self.delete, methods=["POST"],
            name="security_delete", **r)

    # -- helpers -------------------------------------------------------------
    def _mine(self, request) -> set[str]:
        sid = session_id(request)
        return {h["symbol"] for h in self.repo.all_holdings(sid)}

    def _deny(self, request, symbol=None):
        flash(request, "Only an administrator can change the securities list. "
                       + {"password": "Sign in as administrator first (Administrator "
                                      "in the top bar).",
                          "local": "Administration is allowed only from this computer.",
                          "off": "Administration is switched off in the configuration."}
                       [admin_mode(request)], "error")
        if symbol:
            return redirect_to(request, "security", symbol=symbol)
        return redirect_to(request, "securities")

    # -- list and lookup -----------------------------------------------------
    async def index(self, request: Request):
        admin = is_admin(request)
        mine = self._mine(request)
        q = (request.query_params.get("q") or "").strip().lower()
        rows = []
        for s in self.repo.securities():
            if s["symbol"] == CASH_SYMBOL:
                continue
            if not admin and s["symbol"] not in mine and not is_fx(s["symbol"]) \
                    and not s.get("collect"):
                continue
            if q and q not in f"{s['symbol']} {s['name']}".lower():
                continue
            rows.append(dict(s, mine=s["symbol"] in mine))
        return render(request, "securities/index.html", rows=rows, q=q, admin=admin,
                      mode=admin_mode(request), classes=CLASS_OPTIONS,
                      class_info=CLASSES, quote_types=QUOTE_TYPES,
                      retention=self.app.state.config.prices_retention_days)

    async def lookup(self, request: Request):
        """Inquiry: anything Yahoo knows, without storing anything."""
        sym = normalise_symbol(request.query_params.get("symbol") or "")
        if not sym:
            return redirect_to(request, "securities")
        tracked = self.repo.security(sym)
        if tracked and (sym in self._mine(request) or is_admin(request)):
            return redirect_to(request, "security", symbol=sym)
        try:
            h = yahoo.fetch_history(sym, range_="1y")
        except yahoo.YahooError as exc:
            flash(request, f"Yahoo has nothing for '{sym}': {exc}. Try the search box - "
                           "it matches names as well as symbols.", "warning")
            return redirect_to(request, "securities", q=sym.lower())
        lt = yahoo.long_run_stats(sym) or {}
        dates = [b.date for b in h.bars]
        chart = charts.date_line(dates, [("Close", [b.close for b in h.bars])],
                                 title=f"{sym}, a year of daily closes",
                                 desc=f"in {h.currency or 'local currency'}",
                                 y_fmt=lambda v: f"{v:,.2f}")
        cutoff = date.today().replace(year=date.today().year - 1).isoformat()
        divs = sum(a for d, a in h.dividends if d >= cutoff)
        return render(request, "securities/lookup.html", h=h, chart=chart, lt=lt,
                      stats=stats_for([b.adj_close for b in h.bars]),
                      guess=CLASSES[classify(sym, h.name, h.quote_type)]["label"],
                      div_yield=(divs / h.price) if h.price and divs else None,
                      tracked=bool(tracked), admin=is_admin(request),
                      keep_choices=market.KEEP_CHOICES,
                      portfolios=self.repo.list(session_id(request)))

    # -- one security --------------------------------------------------------
    async def view(self, request: Request, symbol: str):
        sym = normalise_symbol(symbol)
        sec = self.repo.security(sym)
        admin = is_admin(request)
        mine = self._mine(request)
        if sec is None or not (sym in mine or is_fx(sym) or admin or sec.get("collect")):
            if sec is None and not admin:
                return redirect_to(request, "security_lookup", symbol=sym)
            if sec is None:
                flash(request, f"{sym} is not in the securities list. Look it up, or add it.",
                      "info")
                return redirect_to(request, "securities", q=sym.lower())
            return redirect_to(request, "security_lookup", symbol=sym)
        rows = self.repo.close_series(sym)
        chart = charts.date_line([d for d, _, _ in rows], [("Close", [c for _, c, _ in rows])],
                                 title=f"{sym}, daily closes",
                                 desc=f"in {sec.get('currency') or 'local currency'}",
                                 y_fmt=lambda v: f"{v:,.2f}")
        sid = session_id(request)
        held = []
        for h in self.repo.all_holdings(sid):
            if h["symbol"] == sym:
                held.append(h)
        return render(request, "securities/view.html", sec=sec, chart=chart,
                      stats=stats_for([a for _, _, a in rows]), mine=held,
                      classes=CLASS_OPTIONS, fx=is_fx(sym), admin=admin,
                      mode=admin_mode(request), holders=self.repo.holders(sym),
                      quote_types=QUOTE_TYPES, bars=list(reversed(self.repo.bars(sym)))[:60],
                      keep_choices=market.KEEP_CHOICES,
                      calendar=CALENDARS[self.repo.calendar(sym)],
                      missing=self.repo.missing_days(sym) if sec.get("source") != "manual" else [],
                      known_gaps=self.repo.known_gaps(sym),
                      retention=self.app.state.config.prices_retention_days)

    async def my_class(self, request: Request, symbol: str):
        """Set the class on *this workspace's* holdings of the symbol. Securities
        are shared between workspaces, so their own guessed class is left alone."""
        form = await request.form()
        sid, sym = session_id(request), normalise_symbol(symbol)
        cls = form.get("asset_class") or ""
        if cls not in CLASSES:
            flash(request, "Choose an asset class.", "error")
            return redirect_to(request, "security", symbol=sym)
        n = 0
        for h in self.repo.all_holdings(sid):
            if h["symbol"] == sym:
                self.repo.update_holding(sid, h["id"], asset_class=cls)
                n += 1
        return redirect_to(request, "security", symbol=sym, flash_message=
                           f"{CLASSES[cls]['label']} set on {n} of your holding(s) of {sym}.")

    # -- administration ------------------------------------------------------
    async def create(self, request: Request):
        if not is_admin(request):
            return self._deny(request)
        form = await request.form()
        sym = normalise_symbol(form.get("symbol") or "")
        source = form.get("source") or "yahoo"
        try:
            self.repo.create_security(
                sym, name=form.get("name") or "", currency=(form.get("currency") or "").strip(),
                quote_type=form.get("quote_type") or "", exchange=form.get("exchange") or "",
                asset_class=form.get("asset_class") or "other", source=source,
                notes=form.get("notes") or "")
        except ValueError as exc:
            flash(request, str(exc).capitalize() + ".", "error")
            return redirect_to(request, "securities")
        if source == "yahoo":
            res = self.app.state.collector.collect([sym], reason="admin-add")
            sec = self.repo.security(sym)
            if res["failed"]:
                flash(request, f"{sym} was added, but Yahoo could not price it: "
                               f"{sec.get('fetch_error')}. Check the symbol, or switch it "
                               "to manual prices.", "warning")
            else:
                flash(request, f"{sym} added with {self.repo.price_stats_for(sym)} closes "
                               "from Yahoo.", "success")
        else:
            rows, bad = parse_prices(form.get("prices") or "")
            got = self.repo.put_prices(sym, rows, self.app.state.config.prices_retention_days)
            self._report_prices(request, sym, got, bad, added=True)
        return redirect_to(request, "security", symbol=sym)

    async def edit(self, request: Request, symbol: str):
        sym = normalise_symbol(symbol)
        if not is_admin(request):
            return self._deny(request, sym)
        form = await request.form()
        try:
            self.repo.update_security(
                sym, name=form.get("name") or "", currency=form.get("currency") or "",
                quote_type=form.get("quote_type") or "", exchange=form.get("exchange") or "",
                asset_class=form.get("asset_class") or "other",
                source=form.get("source") or "yahoo", notes=form.get("notes") or "")
        except ValueError as exc:
            flash(request, str(exc).capitalize() + ".", "error")
            return redirect_to(request, "security", symbol=sym)
        return redirect_to(request, "security", symbol=sym, flash_message="Saved.")

    def _report_prices(self, request, sym, got, bad, added=False):
        msg = (f"{sym} added; " if added else "") + f"{got['stored']} close(s) stored"
        if got["too_old"]:
            msg += (f"; {got['too_old']} older than the {self.app.state.config.prices_retention_days}"
                    "-day retention window were skipped")
        flash(request, msg + ".", "success" if got["stored"] else "warning")
        if bad:
            flash(request, f"{len(bad)} line(s) skipped: " + "; ".join(bad[:5]), "warning")

    async def prices(self, request: Request, symbol: str):
        sym = normalise_symbol(symbol)
        if not is_admin(request):
            return self._deny(request, sym)
        form = await request.form()
        dels = form.getlist("delete_date") if hasattr(form, "getlist") else []
        if dels:
            n = self.repo.delete_prices(sym, dels)
            flash(request, f"Deleted {n} close(s).", "success")
        text = form.get("prices") or ""
        if form.get("one_date") and form.get("one_close"):
            text += f"\n{form.get('one_date')},{form.get('one_close')}"
        if text.strip():
            rows, bad = parse_prices(text)
            got = self.repo.put_prices(sym, rows, self.app.state.config.prices_retention_days)
            self._report_prices(request, sym, got, bad)
        return redirect_to(request, "security", symbol=sym)

    async def refresh(self, request: Request, symbol: str):
        sym = normalise_symbol(symbol)
        if not is_admin(request):
            return self._deny(request, sym)
        sec = self.repo.security(sym) or {}
        if sec.get("source") == "manual":
            flash(request, f"{sym} is manually priced; switch its source to Yahoo first.",
                  "warning")
            return redirect_to(request, "security", symbol=sym)
        res = self.app.state.collector.collect([sym], reason="admin")
        if res["failed"]:
            flash(request, f"Yahoo could not price {sym}: {'; '.join(res['errors'])}", "error")
        else:
            flash(request, f"{sym} refreshed ({res['rows_added']} row(s) written).", "success")
        return redirect_to(request, "security", symbol=sym)

    async def delete(self, request: Request, symbol: str):
        sym = normalise_symbol(symbol)
        if not is_admin(request):
            return self._deny(request, sym)
        try:
            self.repo.delete_security(sym)
        except ValueError as exc:
            flash(request, str(exc).capitalize() + ".", "error")
            return redirect_to(request, "security", symbol=sym)
        return redirect_to(request, "securities",
                           flash_message=f"{sym} and its prices were deleted.")
