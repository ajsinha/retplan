"""The strategy optimiser's pages (web/strategy.py).

    GET  /strategy                  choose the objective; see the latest strategy
    POST /strategy/run              start a search in the background
    GET  /api/strategy/{job}        progress of a search (the page polls it)
    POST /strategy/{job}/save       keep the strategy as a new scenario

A search takes a minute or so, so it runs in a background thread and the page
polls for progress. Settings come from ``strategy.*`` in config/retplan.yaml,
read each time a search starts.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from retplan.plan import plan_from_dict
from web import strategy
from web.fastapi_compat import flash, redirect_to, render
from web.store import session_id

logger = logging.getLogger(__name__)


class StrategyRoutes:
    def __init__(self, app: FastAPI, store):
        self.app = app
        self.store = store
        self._register_routes()

    @property
    def jobs(self) -> strategy.Jobs:
        return self.app.state.strategy_jobs

    def _register_routes(self) -> None:
        add = self.app.add_api_route
        r = dict(include_in_schema=False)
        add("/strategy", self.index, methods=["GET"], name="strategy", **r)
        add("/strategy/run", self.run, methods=["POST"], name="strategy_run", **r)
        add("/api/strategy/{job}", self.status, methods=["GET"], name="api_strategy")
        add("/strategy/{job}/save", self.save, methods=["POST"], name="strategy_save", **r)

    def _enabled(self) -> bool:
        return self.app.state.config.get_bool("strategy.enabled", True)

    async def index(self, request: Request):
        sid = session_id(request)
        plan = self.store.get(sid)
        q = request.query_params
        job = self.jobs.get(sid, q["job"]) if q.get("job") else self.jobs.latest(sid)
        return render(request, "strategy/index.html", plan=plan, job=job,
                      objectives=strategy.OBJECTIVES, areas=strategy.AREAS,
                      enabled=self._enabled(),
                      settings=strategy.Settings.from_config(self.app.state.config),
                      working=[plan.persons[i] for i in strategy.working(plan)],
                      pensions=[plan.income[i] for i in strategy.pension_rows(plan)])

    async def run(self, request: Request):
        if not self._enabled():
            flash(request, "The strategy optimiser is switched off (strategy.enabled).", "warning")
            return redirect_to(request, "strategy")
        sid = session_id(request)
        form = await request.form()
        plan = self.store.get(sid)
        objective = form.get("objective") or "odds"
        try:
            target = float(form.get("target") or plan.policy.confidence * 100) / 100
        except ValueError:
            target = plan.policy.confidence
        target = min(0.99, max(0.5, target))
        try:
            latest = float(form.get("latest_age") or 0) or None
        except ValueError:
            latest = None
        areas = [a for a, _ in strategy.AREAS if form.get(f"area_{a}")] or None
        settings = strategy.Settings.from_config(self.app.state.config)
        jid = self.jobs.start(sid, plan, objective=objective, target=target,
                              settings=settings, areas=areas, latest_age=latest)
        return redirect_to(request, "strategy", job=jid)

    async def status(self, request: Request, job: str):
        j = self.jobs.get(session_id(request), job)
        if j is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return {"status": j["status"], "progress": round(j["progress"], 3),
                "stage": j["stage"], "error": j["error"]}

    async def save(self, request: Request, job: str):
        sid = session_id(request)
        j = self.jobs.get(sid, job)
        if j is None or j["status"] != "done":
            flash(request, "That strategy is no longer available - run it again.", "warning")
            return redirect_to(request, "strategy")
        plan = plan_from_dict(j["result"]["plan"])
        label = dict((k, name) for k, name, *_ in strategy.OBJECTIVES).get(
            j["result"]["objective"], "Strategy")
        name = f"{j['plan_label']} - strategy ({label.lower()})"
        self.store.create(sid, name, plan, activate=True)
        return redirect_to(request, "dashboard", flash_message=
                           f"Saved and switched to '{name}'. Run the simulation to see it in "
                           "full; your original plan is unchanged under Scenarios.")
