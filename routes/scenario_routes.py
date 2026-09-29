"""Scenarios: several named versions of the plan, and a side-by-side comparison.

Every workspace keeps one or more plans and exactly one is active - the one the
editor, the dashboard and the reports show. Duplicating the active plan and
changing one thing is how "what if I retire two years later?" is answered;
the comparison page then lines the versions up.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

from web import charts
from web.fastapi_compat import flash, flash_error_and_log, redirect_to, render
from web.store import blank_plan, session_id
from web.viewmodel import base_view, simulate

logger = logging.getLogger(__name__)
COMPARE_TRIALS = 1500


def _safe_next(url: str | None, fallback: str) -> str:
    """Only same-site relative paths, so ?next= cannot redirect off-site."""
    if url and url.startswith("/") and not url.startswith("//"):
        return url
    return fallback


class ScenarioRoutes:
    def __init__(self, app: FastAPI, store):
        self.app = app
        self.store = store
        self._register_routes()

    def _register_routes(self) -> None:
        add = self.app.add_api_route
        add("/scenarios", self.index, methods=["GET"], name="scenarios",
            include_in_schema=False)
        add("/scenarios/new", self.create, methods=["POST"], name="scenario_new",
            include_in_schema=False)
        add("/scenarios/{plan_id}/activate", self.activate, methods=["POST"],
            name="scenario_activate", include_in_schema=False)
        add("/scenarios/{plan_id}/duplicate", self.duplicate, methods=["POST"],
            name="scenario_duplicate", include_in_schema=False)
        add("/scenarios/{plan_id}/rename", self.rename, methods=["POST"],
            name="scenario_rename", include_in_schema=False)
        add("/scenarios/{plan_id}/delete", self.delete, methods=["POST"],
            name="scenario_delete", include_in_schema=False)
        add("/compare", self.compare, methods=["GET"], name="compare",
            include_in_schema=False)
        add("/api/compare/run", self.run_all, methods=["POST"], name="api_compare_run")

    async def index(self, request: Request):
        sid = session_id(request)
        rows = []
        for s in self.store.scenarios(sid):
            plan = self.store.get_by_id(sid, s["id"])
            p0 = plan.persons[0] if plan.persons else None
            rows.append(dict(s, persons=len(plan.persons),
                             retire=p0.retire_age if p0 else None,
                             assets=sum(l.opening for l in plan.ledgers if l.enabled),
                             spend=sum(e.amount for e in plan.expenses
                                       if e.enabled and not e.recur_years and p0
                                       and e.start_age <= p0.age < e.end_age),
                             sim=self.store.results_for(s["id"])))
        return render(request, "scenarios/index.html", rows=rows)

    async def create(self, request: Request):
        sid = session_id(request)
        form = await request.form()
        name = (form.get("name") or "").strip() or "New plan"
        start = form.get("start") or "blank"
        try:
            if start == "copy":
                self.store.duplicate(sid, self.store.active_id(sid), name)
            elif start == "sample":
                from retplan.samples import sample_plan
                self.store.create(sid, name, sample_plan())
            else:
                self.store.create(sid, name, blank_plan(name))
        except Exception as exc:  # noqa: BLE001
            flash_error_and_log(request, "Could not create the scenario", exc)
            return redirect_to(request, "scenarios")
        return redirect_to(request, "plan_section", section="household",
                           flash_message=f"Created and switched to '{name}'.")

    async def activate(self, request: Request, plan_id: int):
        sid = session_id(request)
        form = await request.form()
        try:
            self.store.activate(sid, plan_id)
        except LookupError:
            flash(request, "That scenario does not exist.", "error")
            return redirect_to(request, "scenarios")
        flash(request, f"Switched to '{self.store.get(sid).label}'.", "success")
        return RedirectResponse(_safe_next(form.get("next"), "/dashboard"),
                                status_code=303)

    async def duplicate(self, request: Request, plan_id: int):
        sid = session_id(request)
        form = await request.form()
        try:
            self.store.duplicate(sid, plan_id, (form.get("name") or "").strip() or None)
        except LookupError:
            flash(request, "That scenario does not exist.", "error")
            return redirect_to(request, "scenarios")
        return redirect_to(request, "scenarios", flash_message=
                           "Copied. The copy is now active - change one thing and compare.")

    async def rename(self, request: Request, plan_id: int):
        sid = session_id(request)
        form = await request.form()
        try:
            self.store.rename(sid, plan_id, form.get("name") or "")
        except LookupError:
            flash(request, "That scenario does not exist.", "error")
            return redirect_to(request, "scenarios")
        return redirect_to(request, "scenarios", flash_message="Renamed.")

    async def delete(self, request: Request, plan_id: int):
        sid = session_id(request)
        try:
            self.store.delete(sid, plan_id)
        except ValueError as exc:
            flash(request, str(exc).capitalize() + ".", "error")
            return redirect_to(request, "scenarios")
        return redirect_to(request, "scenarios", flash_message="Scenario deleted.")

    # -- comparison --------------------------------------------------------
    def _column(self, sid, s):
        plan = self.store.get_by_id(sid, s["id"])
        view = base_view(plan)
        sim = self.store.results_for(s["id"])
        p0 = plan.persons[0] if plan.persons else None
        return dict(
            id=s["id"], name=s["name"], active=bool(s["is_active"]),
            retire=p0.retire_age if p0 else None, horizon_age=p0.death_age if p0 else None,
            assets=sum(l.opening for l in plan.ledgers if l.enabled),
            saving=sum(l.contribution for l in plan.ledgers if l.enabled),
            spend=view["first_year_spend"], funded=view["funded"],
            verdict=view["funded_verdict"], depleted_age=view["depleted_age"],
            terminal=view["terminal"], total_tax=view["total_tax"],
            policy=plan.policy.method.replace("_", " "),
            years=view["years"], net_worth=view["net_worth"],
            success=(sim["kpis"]["success_probability"] if sim else None),
            success_se=(sim["kpis"]["success_se"] if sim else None),
            p50=(sim["kpis"]["terminal_real_p50"] if sim else None),
            p5=(sim["kpis"]["terminal_real_p5"] if sim else None),
            median=(sim["median"] if sim else None),
            trials=(sim["trials"] if sim else None))

    async def compare(self, request: Request):
        sid = session_id(request)
        scen = self.store.scenarios(sid)
        cols = []
        for s in scen:
            try:
                cols.append(self._column(sid, s))
            except Exception as exc:  # noqa: BLE001
                logger.exception("scenario %s could not be projected", s["id"])
                flash(request, f"'{s['name']}' could not be projected: {exc}", "error")
        chart = ""
        chart_mc = ""
        if cols:
            years = cols[0]["years"]
            n = min(len(c["years"]) for c in cols)
            chart = charts.line_chart(years[:n], [(c["name"], c["net_worth"][:n]) for c in cols],
                                      "Net worth, fixed-return projection", "today's money")
            with_sim = [c for c in cols if c["median"]]
            if len(with_sim) == len(cols):
                m = min(len(c["median"]) for c in cols)
                chart_mc = charts.line_chart(
                    years[:m], [(c["name"], c["median"][:m]) for c in cols],
                    "Median net worth across simulated futures", "today's money")
        return render(request, "scenarios/compare.html", cols=cols, chart=chart,
                      chart_mc=chart_mc, trials=COMPARE_TRIALS)

    async def run_all(self, request: Request):
        """Simulate every scenario with the same trial count and seed, so the
        differences are the plans', not the dice's."""
        sid = session_id(request)
        t0 = time.time()
        done = []
        try:
            for s in self.store.scenarios(sid):
                plan = self.store.get_by_id(sid, s["id"])
                payload = simulate(plan, COMPARE_TRIALS, seed=20260916)
                payload["seconds"] = 0.0
                payload["has_solvers"] = False
                self.store.set_results(sid, payload, plan_id=s["id"])
                done.append(s["id"])
        except Exception as exc:  # noqa: BLE001
            logger.exception("comparison run failed")
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
        return {"ok": True, "trials": COMPARE_TRIALS, "scenarios": len(done),
                "seconds": round(time.time() - t0, 2)}
