"""Net worth over time, portfolio by portfolio.

    GET  /networth                    net worth today and over time: all accounts, each portfolio

Every account the workspace has, counted once, and each portfolio: net worth is
recorded every day prices are collected (portfolio/networth.py), and a
portfolio's page can record one on demand.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request

from web import charts
from web.fastapi_compat import render
from web.store import session_id

logger = logging.getLogger(__name__)


class NetWorthRoutes:
    def __init__(self, app: FastAPI, store):
        self.app = app
        self.store = store
        self._register_routes()

    def _register_routes(self) -> None:
        self.app.add_api_route("/networth", self.index, methods=["GET"], name="networth",
                               include_in_schema=False)

    def _row(self, sid, name, v, hist, pid=None):
        chart = ""
        if len(hist) >= 2:
            chart = charts.date_line(
                [h["taken_on"] for h in hist],
                [("Net worth", [h["net"] for h in hist]),
                 ("Assets", [h["assets"] for h in hist]),
                 ("Debts", [h["liabilities"] for h in hist])],
                title=f"{name}: net worth over time",
                desc="recorded every day prices are collected", zero_floor=True,
                y_fmt=charts._fmt_compact)
        first = hist[0] if hist else None
        return dict(name=name, pid=pid, v=v, hist=hist, chart=chart,
                    change=(v.net_worth - first["net"]) if first else None,
                    since=first["taken_on"] if first else None)

    async def index(self, request: Request):
        sid = session_id(request)
        repo, nw = self.app.state.portfolios, self.app.state.networth
        everything = self._row(sid, "Every account", repo.all_valuation(sid), nw.history(sid))
        rows = [self._row(sid, p["name"], repo.valuation(sid, p["id"]), nw.history(sid, p["id"]),
                          p["id"]) for p in repo.list(sid)]
        return render(request, "networth.html", everything=everything, rows=rows,
                      has_accounts=bool(everything["v"].accounts))
