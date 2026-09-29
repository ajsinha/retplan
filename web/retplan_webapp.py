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
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from portfolio.db import Database
from portfolio.networth import NetWorthRepo
from portfolio.prices import PriceCollector, PriceScheduler
from portfolio.repository import PortfolioRepo
from retplan import __version__ as VERSION
from web.config import Config, load_config
from web.fastapi_compat import STATIC_DIR, render, wants_json
from web.store import PlanStore

logger = logging.getLogger(__name__)


class RetPlanWebApp:
    """Builds and owns the FastAPI application."""

    _instance = None
    _lock = threading.Lock()

    def __init__(self, data_dir: str | None = None, config: Config | None = None,
                 start_scheduler: bool = True):
        self.config = config or load_config(data_dir=data_dir)
        self.data_dir = self.config.data_dir
        self.db = Database(self.config.database_url, echo=self.config.database_echo)
        self.store = PlanStore(self.db, legacy_dir=os.path.join(self.data_dir, "plans"))
        self.portfolios = PortfolioRepo(self.db)
        self.networth = NetWorthRepo(self.db)
        # a plan linked to a portfolio takes its accounts and debts from it on every read
        from web import plan_link
        self.store.linker = lambda sid, plan: plan_link.sync(plan, self.portfolios, sid)
        self.collector = PriceCollector(self.portfolios,
                                        retention_days=self.config.prices_retention_days)
        self.scheduler = PriceScheduler(self.collector, run_at=self.config.prices_run_at,
                                        enabled=self.config.prices_enabled and start_scheduler)

        @asynccontextmanager
        async def lifespan(_app):
            self.scheduler.start()
            yield
            self.scheduler.stop()
            self.db.dispose()

        self.app = FastAPI(title="RetPlan", version=VERSION, lifespan=lifespan,
                           docs_url="/api/docs", redoc_url=None)
        self._configure()
        self._register_routes()
        self._install_error_handlers()
        logger.info("RetPlan %s ready (database: %s, config: %s)", VERSION,
                    self.db.safe_url, self.config.source)

    # -- singleton ---------------------------------------------------------
    @classmethod
    def get_instance(cls, data_dir: str | None = None) -> "RetPlanWebApp":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(data_dir=data_dir)
        return cls._instance

    # -- wiring ------------------------------------------------------------
    def _configure(self) -> None:
        # The secret persists in the data directory (or RETPLAN_SECRET), so a
        # restart keeps every browser pointed at its own workspace.
        self.app.add_middleware(SessionMiddleware, secret_key=self.config.secret(),
                                session_cookie="retplan_session",
                                same_site="lax", max_age=60 * 60 * 24 * 365)
        self.app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
        st = self.app.state
        st.store, st.version, st.config = self.store, VERSION, self.config
        st.db, st.portfolios, st.networth = self.db, self.portfolios, self.networth
        st.collector, st.scheduler = self.collector, self.scheduler

    def _register_routes(self) -> None:
        from routes import ALL_ROUTES
        for handler in ALL_ROUTES:
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
    return RetPlanWebApp.get_instance(data_dir=os.environ.get("RETPLAN_DATA")).app
