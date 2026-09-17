"""JSON API that runs the Monte Carlo and the solvers.

Long runs are the reason this is an API rather than a form post: the page starts
the run, shows progress, and swaps the results in when they land, instead of
holding a request open and timing out.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from web.store import session_id
from web.viewmodel import simulate, solver_view

logger = logging.getLogger(__name__)
MAX_TRIALS = 50000


class SimulationRoutes:
    def __init__(self, app: FastAPI, store):
        self.app = app
        self.store = store
        self._register_routes()

    def _register_routes(self) -> None:
        add = self.app.add_api_route
        add("/api/simulate", self.run, methods=["POST"], name="api_simulate")
        add("/api/analysis", self.analysis, methods=["POST"], name="api_analysis")
        add("/api/results", self.results, methods=["GET"], name="api_results")
        add("/api/clear", self.clear, methods=["POST"], name="api_clear")

    async def run(self, request: Request):
        sid = session_id(request)
        plan = self.store.get(sid)
        body = {}
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001 - an empty body is fine
            pass
        trials = int(body.get("trials") or 2000)
        trials = max(100, min(MAX_TRIALS, trials))
        t0 = time.time()
        try:
            payload = simulate(plan, trials)
        except Exception as exc:  # noqa: BLE001
            logger.exception("simulation failed")
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
        payload["seconds"] = time.time() - t0
        payload["has_solvers"] = False
        self.store.set_results(sid, payload)
        return self._summary(payload)

    async def analysis(self, request: Request):
        """Simulation plus the solvers, the spending sweep and the tornado."""
        sid = session_id(request)
        plan = self.store.get(sid)
        body = {}
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            pass
        trials = max(100, min(MAX_TRIALS, int(body.get("trials") or 2000)))
        t0 = time.time()
        try:
            payload = simulate(plan, trials)
            payload.update(solver_view(plan, trials))
        except Exception as exc:  # noqa: BLE001
            logger.exception("analysis failed")
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
        payload["seconds"] = time.time() - t0
        payload["has_solvers"] = True
        self.store.set_results(sid, payload)
        return self._summary(payload)

    async def results(self, request: Request):
        payload = self.store.results(session_id(request))
        if not payload:
            return JSONResponse({"ok": False, "error": "no results yet"},
                                status_code=404)
        return self._summary(payload)

    async def clear(self, request: Request):
        self.store.drop_results(session_id(request))
        return {"ok": True}

    @staticmethod
    def _summary(payload):
        k = payload["kpis"]
        return {
            "ok": True,
            "trials": payload["trials"],
            "seconds": round(payload.get("seconds", 0.0), 2),
            "success": k["success_probability"],
            "success_se": k["success_se"],
            "terminal_p50": k["terminal_real_p50"],
            "terminal_p5": k["terminal_real_p5"],
            "failure_rate": k["failure_rate"],
            "worst_drawdown": k["worst_drawdown"],
            "has_solvers": payload.get("has_solvers", False),
            "max_spend": payload.get("max_spend"),
            "earliest_age": payload.get("earliest_age"),
        }
