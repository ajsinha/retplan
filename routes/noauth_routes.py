"""Landing page, about and method notes. No session state required.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from fastapi import FastAPI, Request

from web.fastapi_compat import render


class NoAuthRoutes:
    def __init__(self, app: FastAPI, store):
        self.app = app
        self.store = store
        self._register_routes()

    def _register_routes(self) -> None:
        add = self.app.add_api_route
        add("/", self.index, methods=["GET"], name="index", include_in_schema=False)
        add("/about", self.about, methods=["GET"], name="about",
            include_in_schema=False)
        add("/method", self.method, methods=["GET"], name="method",
            include_in_schema=False)
        add("/healthz", self.health, methods=["GET"], name="health")

    async def index(self, request: Request):
        return render(request, "landing.html")

    async def about(self, request: Request):
        return render(request, "about.html")

    async def method(self, request: Request):
        return render(request, "method.html")

    async def health(self, request: Request):
        return {"status": "ok", "version": request.app.state.version}
