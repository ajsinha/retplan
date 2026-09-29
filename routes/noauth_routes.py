"""Landing page, about, method notes, search and the system page.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import platform

from fastapi import FastAPI, Request

from web.fastapi_compat import render, url_for
from web.help_catalog import search as help_search
from web.store import session_id

# (label, route, params, icon, words) - the pages search can land on
PAGES = [
    ("Quick start", "wizard", {}, "magic", "wizard new plan onboarding start"),
    ("Dashboard", "dashboard", {}, "speedometer2", "results verdict success odds"),
    ("Scenarios", "scenarios", {}, "layers", "versions what if copy"),
    ("Compare scenarios", "compare", {}, "columns-gap", "side by side comparison"),
    ("Household", "plan_section", {"section": "household"}, "people", "ages people horizon smile"),
    ("Income", "plan_section", {"section": "income"}, "arrow-down-circle", "salary pension rent"),
    ("Spending", "plan_section", {"section": "expenses"}, "arrow-up-circle", "expenses budget"),
    ("Debt", "plan_section", {"section": "debt"}, "bank", "mortgage loan"),
    ("Accounts", "plan_section", {"section": "accounts"}, "wallet2", "balances allocation glide"),
    ("Tax wrappers", "plan_section", {"section": "wrappers"}, "shield-lock", "pension isa 401k roth"),
    ("Tax", "plan_section", {"section": "tax"}, "percent", "bands rates"),
    ("Markets", "plan_section", {"section": "markets"}, "graph-up-arrow", "returns volatility crash inflation"),
    ("Withdrawal policy", "plan_section", {"section": "policy"}, "sliders", "guardrails vpw 4% rule"),
    ("Cash-flow report", "report", {"name": "cashflow"}, "table", "year by year income"),
    ("Balance sheet", "report", {"name": "balance"}, "journal-text", "net worth accounts"),
    ("Tax report", "report", {"name": "tax"}, "receipt", "tax by year"),
    ("Audit", "audit", {}, "clipboard-check", "checks reconciliation"),
    ("Portfolios", "portfolios", {}, "briefcase", "holdings investments selections"),
    ("Your accounts", "accounts", {}, "wallet2", "brokerage 401k ira roth savings mortgage home net worth"),
    ("New portfolio", "portfolio_new", {}, "plus-square", "create import paste"),
    ("Prices", "prices", {}, "cloud-download", "yahoo collector daily"),
    ("Securities", "securities", {}, "search", "look up symbol stock fund add security admin"),
    ("System", "system", {}, "hdd-stack", "database config postgres sqlite"),
    ("About", "about", {}, "info-circle", "version credits"),
    ("Method", "method", {}, "braces", "mathematics model engine"),
]


class NoAuthRoutes:
    def __init__(self, app: FastAPI, store):
        self.app = app
        self.store = store
        self._register_routes()

    def _register_routes(self) -> None:
        add = self.app.add_api_route
        add("/", self.index, methods=["GET"], name="index", include_in_schema=False)
        add("/about", self.about, methods=["GET"], name="about", include_in_schema=False)
        add("/about/compare", self.compare, methods=["GET"], name="about_compare",
            include_in_schema=False)
        add("/method", self.method, methods=["GET"], name="method",
            include_in_schema=False)
        add("/search", self.search, methods=["GET"], name="search",
            include_in_schema=False)
        add("/system", self.system, methods=["GET"], name="system",
            include_in_schema=False)
        add("/healthz", self.health, methods=["GET"], name="health")

    async def index(self, request: Request):
        return render(request, "landing.html")

    async def about(self, request: Request):
        return render(request, "about.html")

    async def compare(self, request: Request):
        return render(request, "about_compare.html")

    async def method(self, request: Request):
        return render(request, "method.html")

    async def search(self, request: Request):
        q = (request.query_params.get("q") or "").strip()
        words = [w for w in q.lower().split() if w]
        pages, topics, holdings, portfolios, scenarios, accounts = [], [], [], [], [], []
        if words:
            for label, route, params, icon, extra in PAGES:
                hay = f"{label} {extra}".lower()
                if all(w in hay for w in words):
                    pages.append(dict(label=label, icon=icon,
                                      href=url_for(request, route, **params)))
            topics = help_search(q)
            sid = session_id(request)
            repo = request.app.state.portfolios
            for p in repo.list(sid):
                if all(w in f"{p['name']} {p['description']}".lower() for w in words):
                    portfolios.append(p)
            for a in repo.accounts(sid):
                if all(w in f"{a['name']} {a['institution']}".lower() for w in words):
                    accounts.append(a)
            for h in repo.all_holdings(sid):
                sec = repo.security(h["symbol"]) or {}
                hay = f"{h['symbol']} {sec.get('name', '')} {h['account']}".lower()
                if all(w in hay for w in words):
                    holdings.append(dict(h, name=sec.get("name", "")))
            for s in self.store.scenarios(sid):
                if all(w in s["name"].lower() for w in words):
                    scenarios.append(s)
        total = (len(pages) + len(topics) + len(holdings) + len(portfolios) + len(scenarios)
                 + len(accounts))
        return render(request, "search.html", q=q, pages=pages, topics=topics,
                      holdings=holdings, portfolios=portfolios, scenarios=scenarios,
                      accounts=accounts,
                      total=total)

    async def system(self, request: Request):
        st = request.app.state
        db = st.db
        counts = {}
        for table in ("plans", "portfolios", "accounts", "portfolio_accounts", "holdings",
                      "securities", "prices",
                      "fetch_runs", "projections"):
            counts[table] = db.scalar(f"SELECT COUNT(*) FROM {table}", default=0)
        import sqlalchemy
        return render(request, "system.html", cfg=st.config, db_url=db.safe_url,
                      dialect=db.dialect, counts=counts, scheduler=st.scheduler.status(),
                      stats=st.portfolios.price_stats(),
                      versions=dict(python=platform.python_version(),
                                    sqlalchemy=sqlalchemy.__version__,
                                    app=st.version))

    async def health(self, request: Request):
        st = request.app.state
        try:
            st.db.scalar("SELECT 1")
            db_ok = True
        except Exception:  # noqa: BLE001
            db_ok = False
        return {"status": "ok" if db_ok else "degraded", "version": st.version,
                "database": st.db.dialect, "database_ok": db_ok,
                "prices": st.scheduler.status()}
