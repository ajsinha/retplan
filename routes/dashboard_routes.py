"""The dashboard: verdict, KPIs and charts.

The deterministic half is live - it recomputes on every request, so it always
reflects the inputs. The simulated half is shown only when results are cached and
still match the current plan; otherwise the page says so rather than quietly
showing stale numbers.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request

from web.fastapi_compat import flash_error_and_log, render
from web.store import session_id
from web import charts
from web.viewmodel import audit_checks, base_view, plan_start

logger = logging.getLogger(__name__)


class DashboardRoutes:
    def __init__(self, app: FastAPI, store):
        self.app = app
        self.store = store
        self._register_routes()

    def _register_routes(self) -> None:
        add = self.app.add_api_route
        add("/dashboard", self.dashboard, methods=["GET"], name="dashboard",
            include_in_schema=False)
        add("/audit", self.audit, methods=["GET"], name="audit",
            include_in_schema=False)
        add("/report/plan", self.plan_report, methods=["GET"], name="plan_report",
            include_in_schema=False)

    async def dashboard(self, request: Request):
        sid = session_id(request)
        plan = self.store.get(sid)
        try:
            view = base_view(plan)
        except Exception as exc:  # noqa: BLE001
            flash_error_and_log(request, "The projection could not be built", exc)
            return render(request, "error.html", code=500,
                          message="The projection could not be built.",
                          detail=str(exc), status_code=500)
        sim = self.store.results(sid)
        checks = audit_checks(plan, view)
        return render(request, "dashboard.html", plan=plan, view=view, sim=sim,
                      checks=checks, timeline=charts.life_timeline(plan, plan_start(plan)),
                      blocking=[c for c in checks if c["status"] == "FAIL"])

    async def audit(self, request: Request):
        sid = session_id(request)
        plan = self.store.get(sid)
        view = base_view(plan)
        checks = audit_checks(plan, view)
        return render(request, "results/audit.html", plan=plan, view=view,
                      checks=checks)

    async def plan_report(self, request: Request):
        """Everything about the plan on one printable page."""
        sid = session_id(request)
        plan = self.store.get(sid)
        view = base_view(plan)
        checks = audit_checks(plan, view)
        from datetime import date
        return render(request, "results/plan_report.html", plan=plan, view=view,
                      sim=self.store.results(sid), checks=checks, today=date.today().isoformat(),
                      timeline=charts.life_timeline(plan, plan_start(plan)))
