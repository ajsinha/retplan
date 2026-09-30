"""The AI assistant's pages (web/assistant).

    GET  /assistant                     the conversation page
    POST /api/assistant/ask             one question -> the answer, its tool calls, proposals
    POST /api/assistant/confirm/{pid}   approve or decline a proposed write
    GET  /assistant/preview             exactly what is sent about this plan
    POST /assistant/{cid}/delete        forget a conversation
    GET  /admin/assistant               administrator: provider and models, status, a test
    POST /admin/assistant               choose the provider and models (kept in the database)
    POST /admin/assistant/reset         go back to the configuration's choices
    POST /admin/assistant/test          send a test message to the chosen model

Everything else - on or off, key, access, features, tools, privacy, limits,
logging, prompts - is ``assistant.*`` in config/retplan.yaml, read live.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import json
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from web.admin import is_admin
from web.assistant import Assistant, AssistantUnavailable, plan_brief, providers
from web.assistant.privacy import Redactor
from web.assistant.prompts import system_prompt
from web.assistant.settings import UI_KEYS, AssistantSettings, save_ui_choice
from web.assistant.tools import ToolContext, enabled_tools, get_plan_summary
from web.fastapi_compat import flash, redirect_to, render
from web.store import session_id

logger = logging.getLogger(__name__)

SUGGESTIONS = [
    ("what_if", "What if I retire two years earlier?"),
    ("explain_strategy", "Find my best strategy and explain it."),
    ("review", "Review my plan: what am I missing?"),
    ("what_if", "When should I claim Social Security?"),
    ("intake", "Help me set up a new plan."),
]


class AssistantRoutes:
    def __init__(self, app: FastAPI, store):
        self.app = app
        self.store = store
        app.state.assistant = Assistant(app)
        self._register_routes()

    @property
    def assistant(self) -> Assistant:
        return self.app.state.assistant

    def _register_routes(self) -> None:
        add = self.app.add_api_route
        r = dict(include_in_schema=False)
        add("/assistant", self.page, methods=["GET"], name="assistant", **r)
        add("/assistant/preview", self.preview, methods=["GET"], name="assistant_preview", **r)
        add("/assistant/{cid}/delete", self.delete, methods=["POST"], name="assistant_delete", **r)
        add("/api/assistant/ask", self.ask, methods=["POST"], name="api_assistant_ask")
        add("/api/assistant/confirm/{pid}", self.confirm, methods=["POST"],
            name="api_assistant_confirm")
        add("/admin/assistant", self.settings_page, methods=["GET"], name="admin_assistant", **r)
        add("/admin/assistant", self.settings_save, methods=["POST"],
            name="admin_assistant_save", **r)
        add("/admin/assistant/reset", self.settings_reset, methods=["POST"],
            name="admin_assistant_reset", **r)
        add("/admin/assistant/test", self.settings_test, methods=["POST"],
            name="admin_assistant_test", **r)

    # -- the conversation --------------------------------------------------------
    async def page(self, request: Request):
        sid = session_id(request)
        s = self.assistant.settings()
        ok, why = self.assistant.check(is_admin(request), s)
        store = self.assistant.store
        cid = request.query_params.get("c")
        current = store.get(sid, int(cid)) if cid and cid.isdigit() else None
        return render(request, "assistant/index.html", ok=ok, why=why, s=s,
                      conversations=store.list(sid) if s.enabled else [],
                      current=current, messages=store.messages(sid, current["id"]) if current else [],
                      suggestions=[q for f, q in SUGGESTIONS if s.features.get(f)],
                      ask=request.query_params.get("ask", "")[:500],
                      mode=request.query_params.get("mode", "chat"),
                      usage=store.usage_today(sid) if s.enabled else None,
                      provider=providers.get(s.provider))

    async def ask(self, request: Request):
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        cid = body.get("conversation")
        try:
            out = self.assistant.ask(session_id(request), str(body.get("question") or ""),
                                     int(cid) if str(cid or "").isdigit() else None,
                                     str(body.get("mode") or "chat"), is_admin(request))
        except AssistantUnavailable as exc:
            return JSONResponse({"error": str(exc)}, status_code=409)
        return out

    async def confirm(self, request: Request, pid: str):
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        try:
            return self.assistant.confirm(session_id(request), pid, bool(body.get("approve")),
                                          is_admin(request))
        except AssistantUnavailable as exc:
            return JSONResponse({"error": str(exc)}, status_code=409)

    async def preview(self, request: Request):
        """What the model would be given about this plan: the instructions with the
        brief, and the plan summary as its tool returns it - redacted and rounded."""
        sid = session_id(request)
        s = self.assistant.settings()
        plan = self.store.get(sid)
        red = Redactor(s.share_names, s.round_money_to).learn_plan(plan)
        ctx = ToolContext(self.app, sid, s, red, plan)
        summary = red.data(get_plan_summary(ctx, {}))
        return render(request, "assistant/preview.html", s=s,
                      system=system_prompt(s, red.text(plan_brief(plan))),
                      summary=json.dumps(summary, indent=2, default=str),
                      tools=enabled_tools(s))

    async def delete(self, request: Request, cid: int):
        self.assistant.store.delete(session_id(request), cid)
        return redirect_to(request, "assistant", flash_message="Conversation deleted.")

    # -- administrator: provider and models ------------------------------------------
    def _deny(self, request):
        flash(request, "Only the administrator can change the assistant's provider and model.",
              "error")
        return redirect_to(request, "admin_login", next="/admin/assistant")

    async def settings_page(self, request: Request):
        if not is_admin(request):
            return self._deny(request)
        s = self.assistant.settings()
        ok, why = s.status()
        catalogue = []
        for p in providers.providers():
            ready, note = p.available(s)
            catalogue.append(dict(key=p.key, label=p.label, blurb=p.blurb, ready=ready, note=note,
                                  models=p.models()))
        return render(request, "admin/assistant.html", s=s, ok=ok, why=why, catalogue=catalogue,
                      test=request.session.pop("assistant_test", None))

    async def settings_save(self, request: Request):
        if not is_admin(request):
            return self._deny(request)
        form = await request.form()
        key = form.get("provider") or ""
        p = providers.get(key)
        if p is None:
            flash(request, "Choose one of the providers listed.", "error")
            return redirect_to(request, "admin_assistant")
        ids = {m.id for m in p.models()}
        model = (form.get("model_custom") or form.get("model") or "").strip()
        smodel = (form.get("strategy_model_custom") or form.get("strategy_model") or "").strip()
        if not model:
            flash(request, "Choose a model.", "error")
            return redirect_to(request, "admin_assistant")
        smodel = smodel or model
        db = self.app.state.db
        save_ui_choice(db, "provider", key)
        save_ui_choice(db, "model", model)
        save_ui_choice(db, "strategy_model", smodel)
        note = "" if model in ids else " (a model id not in RetPlan's list - taken as given)"
        return redirect_to(request, "admin_assistant", flash_message=
                           f"The assistant now uses {p.label}: {model}{note}. This setting is kept "
                           "in the database and wins over the configuration until you reset it.")

    async def settings_reset(self, request: Request):
        if not is_admin(request):
            return self._deny(request)
        for k in UI_KEYS:
            save_ui_choice(self.app.state.db, k, None)
        return redirect_to(request, "admin_assistant",
                           flash_message="Back to the provider and models in the configuration.")

    async def settings_test(self, request: Request):
        if not is_admin(request):
            return self._deny(request)
        s = self.assistant.settings()
        p = s.provider_obj()
        result = dict(provider=s.provider, model=s.model)
        if p is None:
            result.update(ok=False, text=f"Unknown provider '{s.provider}'.")
        else:
            ready, why = p.available(s)
            if not ready:
                result.update(ok=False, text=why)
            else:
                try:
                    reply = p.reply(s.model, "Reply in one short sentence.",
                                    [{"role": "user", "text": "Say hello to RetPlan."}], [], s)
                    result.update(ok=True, text=reply.text or "(an empty reply)",
                                  tokens=reply.tokens_in + reply.tokens_out)
                except providers.ProviderError as exc:
                    result.update(ok=False, text=str(exc))
        request.session["assistant_test"] = result
        return redirect_to(request, "admin_assistant")
