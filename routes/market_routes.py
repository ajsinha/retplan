"""Market data: securities collected every day, held or not.

    GET  /market                          every collected security, by kind
    POST /market/add                      collect one symbol or a pasted list
    POST /market/preset/{key}             collect a ready-made set (indices, sectors…)
    POST /market/{symbol}/keep            how much history to keep
    POST /market/{symbol}/stop            stop collecting it
    POST /market/collect                  collect everything now
    GET  /securities/{symbol}.csv         a security's stored daily bars as CSV

Anyone can browse; adding, changing and stopping are for the administrator,
because securities and prices are shared by every workspace.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import csv
import io
import logging

from fastapi import FastAPI, Request
from fastapi.responses import Response

from portfolio import market
from portfolio.prices import collect_in_background
from portfolio.repository import normalise_symbol
from web.admin import admin_mode, is_admin
from web.fastapi_compat import flash, redirect_to, render

logger = logging.getLogger(__name__)
MAX_PASTE = 200


class MarketRoutes:
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
        add("/market", self.index, methods=["GET"], name="market", **r)
        add("/market/add", self.add, methods=["POST"], name="market_add", **r)
        add("/market/collect", self.collect, methods=["POST"], name="market_collect", **r)
        add("/market/preset/{key}", self.preset, methods=["POST"], name="market_preset", **r)
        add("/market/{symbol}/keep", self.keep, methods=["POST"], name="market_keep", **r)
        add("/market/{symbol}/stop", self.stop, methods=["POST"], name="market_stop", **r)
        # before /securities/{symbol}, which would otherwise take it
        add("/securities/{symbol}.csv", self.csv, methods=["GET"], name="security_csv", **r)

    def _deny(self, request):
        flash(request, "Only an administrator can change what is collected - market data is "
                       "shared by everyone using this RetPlan. " +
              {"password": "Sign in as administrator first (shield icon).",
               "local": "Open RetPlan from this machine to administer it.",
               "off": "Administration is switched off in the configuration."}
              .get(admin_mode(request), ""), "error")
        return redirect_to(request, "market")

    # -- the page ------------------------------------------------------------
    async def index(self, request: Request):
        rows = self.repo.market_data()
        groups = []
        for key, label in market.CATEGORIES:
            members = [r for r in rows if market.category(r["quote_type"]) == key]
            if members:
                groups.append((label, members))
        have = {r["symbol"] for r in rows}
        presets = [dict(p, have=sum(s in have for s in p["symbols"])) for p in market.PRESETS]
        cfg = self.app.state.config
        return render(request, "market/index.html", groups=groups, n=len(rows),
                      presets=presets, keep_choices=market.KEEP_CHOICES,
                      admin=is_admin(request), mode=admin_mode(request),
                      retention=cfg.prices_retention_days,
                      scheduler=self.app.state.scheduler.status(),
                      running=self.app.state.collector.running,
                      last_run=self.repo.last_successful_run())

    # -- changing what is collected -------------------------------------------
    def _watch(self, request, symbols, keep):
        added, bad = [], []
        for sym in symbols[:MAX_PASTE]:
            try:
                self.repo.watch(sym, keep)
                added.append(normalise_symbol(sym))
            except ValueError as exc:
                bad.append(str(exc))
        if added:
            collect_in_background(self.app.state.collector, added, "market")
            flash(request, f"Collecting {len(added)} symbol{'' if len(added) == 1 else 's'}"
                           f" ({', '.join(added[:8])}{'…' if len(added) > 8 else ''}). Their "
                           "history is being fetched now - reload in a moment. A symbol Yahoo "
                           "does not know is flagged in the list.", "success")
        if bad:
            flash(request, "Skipped: " + "; ".join(bad[:5]), "warning")
        if len(symbols) > MAX_PASTE:
            flash(request, f"Only the first {MAX_PASTE} symbols were taken.", "warning")

    async def add(self, request: Request):
        if not is_admin(request):
            return self._deny(request)
        form = await request.form()
        symbols = market.parse_symbols(form.get("symbols") or "")
        if not symbols:
            flash(request, "Type a symbol, or paste a list.", "error")
            return redirect_to(request, "market")
        self._watch(request, symbols, market.keep_for(form.get("keep_days")))
        return redirect_to(request, "market")

    async def preset(self, request: Request, key: str):
        if not is_admin(request):
            return self._deny(request)
        p = market.PRESET_BY_KEY.get(key)
        if p is None:
            flash(request, "There is no such set.", "error")
            return redirect_to(request, "market")
        form = await request.form()
        self._watch(request, p["symbols"], market.keep_for(form.get("keep_days")))
        return redirect_to(request, "market")

    async def keep(self, request: Request, symbol: str):
        if not is_admin(request):
            return self._deny(request)
        form = await request.form()
        sym = normalise_symbol(symbol)
        old = self.repo.keep_days(sym, self.app.state.config.prices_retention_days)
        keep = market.keep_for(form.get("keep_days"))
        self.repo.set_keep_days(sym, keep)
        new = self.repo.keep_days(sym, self.app.state.config.prices_retention_days)
        if new > old:
            collect_in_background(self.app.state.collector, [sym], "backfill")
            flash(request, f"{sym}: fetching the longer history now.", "success")
        else:
            flash(request, f"{sym}: history beyond the new window goes after the next run.",
                  "success")
        return redirect_to(request, "market")

    async def stop(self, request: Request, symbol: str):
        if not is_admin(request):
            return self._deny(request)
        sym = normalise_symbol(symbol)
        self.repo.unwatch(sym)
        held = self.repo.holders(sym)
        flash(request, f"{sym} is no longer collected as market data" +
              (f" - it is still priced for the {held} holding(s) of it." if held else
               "; its prices are pruned to the global window.") , "success")
        return redirect_to(request, "market")

    async def collect(self, request: Request):
        if not is_admin(request):
            return self._deny(request)
        if self.app.state.collector.running:
            flash(request, "A collection run is already in progress.", "info")
        else:
            collect_in_background(self.app.state.collector, None, "manual")
            flash(request, "Collecting every symbol now, in the background.", "success")
        return redirect_to(request, "market")

    # -- download ---------------------------------------------------------------
    async def csv(self, request: Request, symbol: str):
        sym = normalise_symbol(symbol)
        sec = self.repo.security(sym)
        if sec is None:
            return Response("unknown symbol\n", status_code=404, media_type="text/plain")
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["date", "open", "high", "low", "close", "adj_close", "volume"])
        for b in self.repo.bars(sym):
            w.writerow([b["date"], b["open"], b["high"], b["low"], b["close"],
                        b["adj_close"], b["volume"]])
        name = sym.replace("^", "").replace("=", "_").replace("/", "_").lower()
        return Response(out.getvalue(), media_type="text/csv", headers={
            "Content-Disposition": f'attachment; filename="{name}-daily.csv"'})
