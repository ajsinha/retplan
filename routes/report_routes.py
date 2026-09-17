"""Year-by-year reports: cash flow, balance sheet and tax.

Every table is the table-view twin of a chart on the dashboard, so no number is
reachable only by hovering.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from fastapi import FastAPI, Request

from web.fastapi_compat import render
from web.store import session_id
from web.viewmodel import base_view

REPORTS = [("cashflow", "Cash flow"), ("balance", "Balance sheet"), ("tax", "Tax")]


class ReportRoutes:
    def __init__(self, app: FastAPI, store):
        self.app = app
        self.store = store
        self._register_routes()

    def _register_routes(self) -> None:
        add = self.app.add_api_route
        add("/reports", self.report, methods=["GET"], name="reports",
            include_in_schema=False)
        add("/reports/{name}", self.report, methods=["GET"], name="report",
            include_in_schema=False)

    async def report(self, request: Request, name: str = "cashflow"):
        if name not in dict(REPORTS):
            name = "cashflow"
        plan = self.store.get(session_id(request))
        view = base_view(plan)
        res = view["res"]
        rows = []
        for t, year in enumerate(view["years"]):
            rows.append(dict(
                year=year, age=view["ages"][t],
                income=float(res.income[0, t]), mrd=float(res.mrd[0, t]),
                spend=float(res.spend[0, t]), tax=float(res.tax[0, t]),
                withdrawal=float(res.withdrawal[0, t]),
                contribution=float(res.contribution[0, t]),
                fees=float(res.fees[0, t]),
                shortfall=float(res.shortfall[0, t]),
                portfolio=float(res.balance_close[0, t]),
                debt=float(res.debt_balance[0, t]),
                net_worth=float(res.net_worth[0, t]),
                taxable=float(res.taxable_income[0, t]),
                wrappers=[float(x) for x in res.balance_by_wrapper[0, t]],
            ))
        return render(request, f"results/{name}.html", plan=plan, view=view,
                      rows=rows, reports=REPORTS, active=name)
