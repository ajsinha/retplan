"""Download and upload a plan; build the LibreOffice workbook on demand.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import io
import json
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from web.fastapi_compat import flash, flash_error_and_log, redirect_to
from web.store import session_id

logger = logging.getLogger(__name__)


class ExportRoutes:
    def __init__(self, app: FastAPI, store):
        self.app = app
        self.store = store
        self._register_routes()

    def _register_routes(self) -> None:
        add = self.app.add_api_route
        add("/export/plan.json", self.export_plan, methods=["GET"],
            name="export_plan", include_in_schema=False)
        add("/import", self.import_plan, methods=["POST"], name="import_plan",
            include_in_schema=False)
        # Three segments on purpose: "/plan/reset" would be captured by the
        # editor's "/plan/{section}" POST route, which is registered first, and
        # the reset would silently become a failed save.
        add("/plan/actions/reset", self.reset, methods=["POST"], name="plan_reset",
            include_in_schema=False)
        add("/plan/actions/clear", self.clear, methods=["POST"], name="plan_clear",
            include_in_schema=False)

    async def export_plan(self, request: Request):
        sid = session_id(request)
        text = self.store.export_json(sid)
        name = (self.store.get(sid).label or "plan").replace(" ", "-").lower()
        return StreamingResponse(
            io.BytesIO(text.encode("utf-8")), media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{name}.json"'})

    async def import_plan(self, request: Request):
        sid = session_id(request)
        form = await request.form()
        upload = form.get("file")
        try:
            if upload is not None and hasattr(upload, "read"):
                raw = (await upload.read()).decode("utf-8")
            else:
                raw = form.get("text") or ""
            if not raw.strip():
                flash(request, "Nothing to import.", "error")
                return redirect_to(request, "plan_section", section="household")
            json.loads(raw)                     # fail before touching the store
            self.store.import_json(sid, raw)
        except Exception as exc:  # noqa: BLE001
            flash_error_and_log(request, "That file is not a valid plan", exc)
            return redirect_to(request, "plan_section", section="household")
        return redirect_to(request, "dashboard",
                           flash_message="Plan imported.", section="household")

    async def reset(self, request: Request):
        self.store.reset(session_id(request))
        return redirect_to(request, "plan_section",
                           flash_message="Reloaded the sample household.",
                           section="household")

    async def clear(self, request: Request):
        self.store.clear(session_id(request))
        return redirect_to(request, "plan_section",
                           flash_message="Started an empty plan.",
                           section="household")
