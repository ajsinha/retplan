"""RetPlan web application (FastAPI).

Singleton application object that builds the FastAPI app, mounts static files,
installs session middleware, constructs every route handler with its
dependencies, and exposes the engine through ``app.state`` so route classes stay
free of module-level globals.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import logging
import os
import secrets
import threading

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from retplan import __version__ as VERSION
from web.fastapi_compat import STATIC_DIR, render, wants_json
from web.store import PlanStore

logger = logging.getLogger(__name__)


class RetPlanWebApp:
    """Builds and owns the FastAPI application."""

    _instance = None
    _lock = threading.Lock()

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.store = PlanStore(os.path.join(data_dir, "plans"))
        self.app = FastAPI(title="RetPlan", version=VERSION,
                           docs_url="/api/docs", redoc_url=None)
        self._configure()
        self._register_routes()
        self._install_error_handlers()
        logger.info("RetPlan %s ready (data dir: %s)", VERSION, data_dir)

    # -- singleton ---------------------------------------------------------
    @classmethod
    def get_instance(cls, data_dir: str = "data") -> "RetPlanWebApp":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(data_dir=data_dir)
        return cls._instance

    # -- wiring ------------------------------------------------------------
    def _configure(self) -> None:
        # A generated secret is fine: sessions carry only an opaque plan id, so
        # the worst a restart costs is a new blank session. An operator who wants
        # sessions to survive a restart sets RETPLAN_SECRET.
        secret = os.environ.get("RETPLAN_SECRET") or secrets.token_hex(32)
        self.app.add_middleware(SessionMiddleware, secret_key=secret,
                                session_cookie="retplan_session",
                                same_site="lax", max_age=60 * 60 * 24 * 30)
        self.app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
        self.app.state.store = self.store
        self.app.state.version = VERSION

    def _register_routes(self) -> None:
        from routes import (DashboardRoutes, ExportRoutes, NoAuthRoutes,
                            PlanRoutes, ReportRoutes, SimulationRoutes)
        for handler in (NoAuthRoutes, PlanRoutes, DashboardRoutes,
                        SimulationRoutes, ReportRoutes, ExportRoutes):
            handler(self.app, self.store)

    def _install_error_handlers(self) -> None:
        app = self.app

        @app.exception_handler(404)
        async def not_found(request: Request, exc):        # noqa: ANN001
            if wants_json(request):
                return JSONResponse({"error": "not found"}, status_code=404)
            return render(request, "error.html", status_code=404,
                          code=404, message="That page does not exist.")

        @app.exception_handler(Exception)
        async def unhandled(request: Request, exc: Exception):
            # Mandate: show the user something honest AND log the full trace.
            logger.exception("unhandled error on %s", request.url.path)
            if wants_json(request):
                return JSONResponse({"error": str(exc)}, status_code=500)
            return render(request, "error.html", status_code=500, code=500,
                          message="Something went wrong. The details are in the "
                                  "server log.", detail=str(exc))


def create_app() -> FastAPI:
    """Factory for ``uvicorn --reload``."""
    return RetPlanWebApp.get_instance(
        data_dir=os.environ.get("RETPLAN_DATA", "data")).app
