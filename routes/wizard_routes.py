"""The quick-start wizard: /start.

Six short steps with a draft kept in the session, so Back and a reload lose
nothing. Every step validates on its own and says what is wrong in words; the
last step builds a complete plan with web.wizard.build_plan, saves it as a new
scenario (or over the active one) and lands on the dashboard.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request

from web import plan_link, wizard
from web.fastapi_compat import flash, flash_error_and_log, redirect_to, render
from web.store import session_id

logger = logging.getLogger(__name__)
DRAFT = "wizard"
KEYS = list(wizard.DEFAULTS)


class WizardRoutes:
    def __init__(self, app: FastAPI, store):
        self.app = app
        self.store = store
        self._register_routes()

    def _register_routes(self) -> None:
        add = self.app.add_api_route
        add("/start", self.show, methods=["GET"], name="wizard", include_in_schema=False)
        add("/start/reset", self.reset, methods=["POST"], name="wizard_reset",
            include_in_schema=False)
        add("/start/finish", self.finish, methods=["POST"], name="wizard_finish",
            include_in_schema=False)
        add("/start/{step}", self.save, methods=["POST"], name="wizard_save",
            include_in_schema=False)

    @staticmethod
    def _draft(request: Request) -> dict:
        d = dict(wizard.DEFAULTS)
        d.update(request.session.get(DRAFT) or {})
        return d

    async def show(self, request: Request, step: str = "you"):
        steps = [s[0] for s in wizard.STEPS]
        if step not in steps:
            step = "you"
        sid = session_id(request)
        repo = request.app.state.portfolios
        pick = request.query_params.get("portfolio")
        if pick and pick.isdigit():                 # "start a plan from this portfolio"
            draft = dict(request.session.get(DRAFT) or {})
            draft["link_portfolio"] = pick
            request.session[DRAFT] = draft
        a = self._draft(request)
        idx = steps.index(step)
        linked = wizard.linked_accounts(repo, sid, a["link_portfolio"]) \
            if a.get("link_portfolio") else (None, [])
        return render(request, "wizard.html", step=step, idx=idx, steps=wizard.STEPS,
                      a=a, risk=wizard.RISK, tax=wizard.TAX,
                      account_types=wizard.ACCOUNT_TYPES, linked_pf=linked[0],
                      linked_accounts=linked[1], pay_types=wizard.PAY_TYPES,
                      summary=wizard.summary(a, linked),
                      done=set(request.session.get("wizard_done") or []),
                      portfolios=repo.list(sid),
                      prev=steps[idx - 1] if idx else None)

    async def save(self, request: Request, step: str):
        steps = [s[0] for s in wizard.STEPS]
        if step not in steps:
            return redirect_to(request, "wizard")
        form = await request.form()
        draft = dict(request.session.get(DRAFT) or {})
        for k in KEYS:
            if k in form:
                draft[k] = str(form.get(k))
        # unchecked checkboxes are absent from the post
        if step == "you":
            draft["partner"] = "1" if form.get("partner") else ""
        if step == "savings":
            for k in form.keys():                   # what goes into each linked account
                if k.startswith("lk_"):
                    draft[k] = str(form.get(k))
            if form.get("unlink"):
                draft["link_portfolio"] = ""
                request.session[DRAFT] = draft
                return redirect_to(request, "wizard", step="savings")
            if form.get("go") == "link":
                draft["link_portfolio"] = form.get("pick_portfolio") or ""
                request.session[DRAFT] = draft
                return redirect_to(request, "wizard", step="savings")
        if step == "savings" and not draft.get("link_portfolio"):
            # An account type counts when ticked. Without script every type's inputs
            # are posted, so a type with figures typed in counts too; with script an
            # unticked type's inputs are disabled, so they are absent and cleared.
            for t in wizard.ACCOUNT_TYPES:
                keys = wizard.account_keys(t)
                typed = any(wizard._f(form, k) > 0 for k in keys if k in form)
                has = bool(form.get(f"has_{t['key']}")) or typed
                draft[f"has_{t['key']}"] = "1" if has else ""
                if not has:
                    for k in keys:
                        draft[k] = "0"
        request.session[DRAFT] = draft
        errs = wizard.validate(step, self._draft(request))
        if errs:
            for e in errs:
                flash(request, e, "error")
            return redirect_to(request, "wizard", step=step)
        done = set(request.session.get("wizard_done") or [])
        done.add(step)
        request.session["wizard_done"] = sorted(done)
        go = form.get("go") or "next"
        idx = steps.index(step)
        target = steps[max(0, idx - 1)] if go == "back" else steps[min(len(steps) - 1, idx + 1)]
        return redirect_to(request, "wizard", step=target)

    async def reset(self, request: Request):
        request.session.pop(DRAFT, None)
        request.session.pop("wizard_done", None)
        return redirect_to(request, "wizard", flash_message="Started over.")

    async def finish(self, request: Request):
        sid = session_id(request)
        form = await request.form()
        a = self._draft(request)
        for step, *_ in wizard.STEPS:
            errs = wizard.validate(step, a)
            if errs:
                for e in errs:
                    flash(request, e, "error")
                return redirect_to(request, "wizard", step=step)
        try:
            plan = wizard.build_plan(a)
            if a.get("link_portfolio"):
                plan_link.link(plan, request.app.state.portfolios, sid, int(a["link_portfolio"]))
                wizard.apply_linked_saving(plan, a)
            if form.get("mode") == "replace":
                self.store.put(sid, plan)
            else:
                self.store.create(sid, plan.label, plan, activate=True)
        except Exception as exc:  # noqa: BLE001
            flash_error_and_log(request, "Could not build the plan", exc)
            return redirect_to(request, "wizard", step="review")
        request.session.pop(DRAFT, None)
        request.session.pop("wizard_done", None)
        return redirect_to(request, "dashboard", flash_message=
                           f"'{plan.label}' is ready. Press Run simulation for the odds; "
                           "refine anything in the Plan menu.")
