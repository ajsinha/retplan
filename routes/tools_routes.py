"""Planning tools: live what-if, the levers that matter, claiming age, conversions.

    POST /api/whatif              the adjusted plan's odds, for the dashboard sliders
    POST /api/whatif/save         keep an adjustment as a new scenario
    POST /api/levers              every common change tried alone, ranked
    GET/POST /tools/claiming      public-pension claiming-age explorer
    GET/POST /tools/conversions   account-conversion explorer (Roth-style, any wrapper)
    POST /tools/conversions/add   add the chosen conversion to the plan

All of them work on the active plan and save nothing unless asked.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from retplan.plan import CareRisk, Conversion
from web import charts, levers
from web.fastapi_compat import flash, flash_error_and_log, redirect_to, render
from web.store import session_id

logger = logging.getLogger(__name__)


def _f(v, default=None):
    try:
        t = str(v).strip().replace(",", "").replace("%", "")
        return float(t) if t else default
    except (TypeError, ValueError):
        return default


def _numbers(text: str) -> list[float]:
    out = []
    for part in (text or "").replace(";", ",").split(","):
        v = _f(part)
        if v is not None and v > 0:
            out.append(v)
    return out[:8]


class ToolsRoutes:
    def __init__(self, app: FastAPI, store):
        self.app = app
        self.store = store
        self._register_routes()

    def _register_routes(self) -> None:
        add = self.app.add_api_route
        r = dict(include_in_schema=False)
        add("/api/whatif", self.whatif, methods=["POST"], name="api_whatif")
        add("/api/whatif/save", self.whatif_save, methods=["POST"], name="api_whatif_save")
        add("/api/levers", self.levers, methods=["POST"], name="api_levers")
        add("/tools/claiming", self.claiming, methods=["GET", "POST"], name="tool_claiming", **r)
        add("/tools/conversions", self.conversions, methods=["GET", "POST"],
            name="tool_conversions", **r)
        add("/tools/conversions/add", self.conversion_add, methods=["POST"],
            name="tool_conversion_add", **r)
        add("/tools/spending", self.spending, methods=["GET", "POST"], name="tool_spending", **r)
        add("/tools/draw-order", self.draw_order, methods=["GET", "POST"],
            name="tool_draw_order", **r)
        add("/tools/draw-order/apply", self.draw_order_apply, methods=["POST"],
            name="tool_draw_order_apply", **r)
        add("/tools/health", self.health, methods=["GET", "POST"], name="tool_health", **r)
        add("/tools/health/add", self.health_add, methods=["POST"], name="tool_health_add", **r)

    # -- what-if --------------------------------------------------------------
    async def _body(self, request):
        try:
            return await request.json()
        except Exception:  # noqa: BLE001
            return {}

    async def whatif(self, request: Request):
        sid = session_id(request)
        plan = self.store.get(sid)
        adj = levers.Adjust.from_dict(await self._body(request))
        try:
            base = levers.run(plan)
            out = base if adj.is_zero() else levers.run(levers.apply(plan, adj))
        except Exception as exc:  # noqa: BLE001
            logger.exception("what-if failed")
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
        return {"ok": True, "base": base, "adjusted": out, "describe": adj.describe()}

    async def whatif_save(self, request: Request):
        sid = session_id(request)
        body = await self._body(request)
        adj = levers.Adjust.from_dict(body)
        if adj.is_zero():
            return JSONResponse({"ok": False, "error": "nothing changed"}, status_code=400)
        plan = self.store.get(sid)
        q = levers.apply(plan, adj)
        name = (body.get("name") or "").strip() or f"{plan.label}: {adj.describe()}"
        q.label = name[:80]
        self.store.create(sid, q.label, q, activate=True)
        flash(request, f"Saved as a new scenario, “{q.label}”, and switched to it. "
                       "The original is unchanged.", "success")
        return {"ok": True, "name": q.label}

    async def levers(self, request: Request):
        sid = session_id(request)
        try:
            return {"ok": True, **levers.levers(self.store.get(sid))}
        except Exception as exc:  # noqa: BLE001
            logger.exception("levers failed")
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

    # -- claiming age -----------------------------------------------------------
    async def claiming(self, request: Request):
        sid = session_id(request)
        plan = self.store.get(sid)
        pensions = [(i, r) for i, r in enumerate(plan.income)
                    if r.category == "state_pension" and r.enabled]
        form = await request.form() if request.method == "POST" else {}
        result, chart = None, ""
        early = (_f(form.get("early"), 6.67) if form else 6.67) / 100
        late = (_f(form.get("late"), 8.0) if form else 8.0) / 100
        lo = int(_f(form.get("from_age"), 62) if form else 62)
        hi = int(_f(form.get("to_age"), 70) if form else 70)
        row = int(_f(form.get("row"), pensions[0][0] if pensions else 0)) if form else \
            (pensions[0][0] if pensions else 0)
        if form and pensions:
            lo, hi = max(50, min(lo, hi)), min(80, max(lo, hi))
            try:
                result = levers.claiming(plan, row, range(lo, hi + 1), early, late)
                ages = [x["age"] for x in result["rows"]]
                chart = charts.line_chart(ages, [("Chance of success", [x["success"] for x in result["rows"]])],
                                          "Success by claiming age", "probability",
                                          y_fmt=charts._pct_fmt, x_name="Claim at")
            except Exception as exc:  # noqa: BLE001
                flash_error_and_log(request, "The claiming comparison failed", exc)
        return render(request, "tools/claiming.html", plan=plan, pensions=pensions,
                      result=result, chart=chart, early=early, late=late, lo=lo, hi=hi,
                      row=row)

    # -- conversions -------------------------------------------------------------
    def _conversion_defaults(self, plan):
        src = next((i for i, lg in enumerate(plan.ledgers)
                    if plan.wrappers[lg.wrapper].withdrawal_taxable_fraction >= 0.99), 0)
        dst = next((i for i, lg in enumerate(plan.ledgers)
                    if plan.wrappers[lg.wrapper].withdrawal_taxable_fraction <= 0.01
                    and not plan.wrappers[lg.wrapper].realises_capital_gains
                    and plan.wrappers[lg.wrapper].liquid), min(1, len(plan.ledgers) - 1))
        p0 = plan.persons[0]
        start = max(p0.age, p0.retire_age)
        pension = min((r.start_age for r in plan.income if r.category == "state_pension"),
                      default=start + 10)
        return src, dst, start, max(start + 1, min(pension, start + 10))

    async def conversions(self, request: Request):
        sid = session_id(request)
        plan = self.store.get(sid)
        src, dst, start, end = self._conversion_defaults(plan)
        form = await request.form() if request.method == "POST" else {}
        values = dict(src=src, dst=dst, start=start, end=end, amounts="10000, 20000, 40000",
                      fill=", ".join(f"{b:g}" for b in plan.tax.ordinary.lowers[1:3]),
                      heir=25.0)
        result, chart = None, ""
        if form:
            values.update(src=int(_f(form.get("src"), src)), dst=int(_f(form.get("dst"), dst)),
                          start=_f(form.get("start"), start), end=_f(form.get("end"), end),
                          amounts=form.get("amounts") or "", fill=form.get("fill") or "",
                          heir=_f(form.get("heir"), 25.0))
            if values["src"] == values["dst"]:
                flash(request, "Choose two different accounts.", "error")
            elif values["end"] <= values["start"]:
                flash(request, "The last age must be after the first.", "error")
            else:
                try:
                    result = levers.conversions(plan, values["src"], values["dst"], values["start"],
                                                values["end"], _numbers(values["amounts"]),
                                                _numbers(values["fill"]), values["heir"] / 100)
                except Exception as exc:  # noqa: BLE001
                    flash_error_and_log(request, "The conversion comparison failed", exc)
        return render(request, "tools/conversions.html", plan=plan, v=values, result=result,
                      chart=chart)

    async def conversion_add(self, request: Request):
        sid = session_id(request)
        form = await request.form()
        plan = self.store.get(sid)
        mode = form.get("mode") if form.get("mode") in ("amount", "fill_to") else "amount"
        cv = Conversion(form.get("label") or "Conversion", int(_f(form.get("src"), 0)),
                        int(_f(form.get("dst"), 1)), mode, _f(form.get("value"), 0.0),
                        _f(form.get("start"), 0.0), _f(form.get("end"), 0.0))
        if form.get("as_scenario"):
            plan.conversions = list(plan.conversions) + [cv]
            plan.label = f"{plan.label} + {cv.label.lower()}"[:80]
            self.store.create(sid, plan.label, plan, activate=True)
            msg = f"Saved as a new scenario, “{plan.label}”."
        else:
            plan.conversions = list(plan.conversions) + [cv]
            self.store.put(sid, plan)
            msg = "Conversion added to your plan."
        return redirect_to(request, "plan_section", section="conversions", flash_message=msg)

    # -- spending check ----------------------------------------------------------
    async def spending(self, request: Request):
        sid = session_id(request)
        plan = self.store.get(sid)
        form = await request.form() if request.method == "POST" else {}
        pct = lambda k, d: (_f(form.get(k), d * 100) if form else d * 100) / 100   # noqa: E731
        target = pct("target", plan.policy.confidence)
        lower = pct("lower", max(0.0, plan.policy.confidence - 0.15))
        upper = pct("upper", min(0.99, plan.policy.confidence + 0.10))
        savings = _f(form.get("savings")) if form else None
        result, chart = None, ""
        if form:
            if not lower < target < upper:
                flash(request, "The lower guardrail must be below the target and the upper "
                               "one above it.", "error")
            else:
                try:
                    result = levers.spending_check(plan, target, lower, upper, savings)
                    xs = [r["spend"] for r in result["rows"]]
                    chart = charts.line_chart(
                        xs, [("Chance of success", [r["success"] for r in result["rows"]]),
                             ("Target", [target] * len(xs)), ("Upper guardrail", [upper] * len(xs)),
                             ("Lower guardrail", [lower] * len(xs))],
                        "Success against spending", "probability", y_fmt=charts._pct_fmt,
                        x_name="Spending")
                except Exception as exc:  # noqa: BLE001
                    flash_error_and_log(request, "The spending check failed", exc)
        from web.levers import spending_now
        liquid = sum(lg.opening for lg in plan.ledgers
                     if lg.enabled and plan.wrappers[lg.wrapper].liquid)
        return render(request, "tools/spending.html", plan=plan, result=result, chart=chart,
                      target=target, lower=lower, upper=upper, liquid=liquid,
                      savings=savings if savings is not None else liquid,
                      now=spending_now(plan))

    # -- draw order --------------------------------------------------------------
    async def draw_order(self, request: Request):
        sid = session_id(request)
        plan = self.store.get(sid)
        form = await request.form() if request.method == "POST" else {}
        heir = _f(form.get("heir"), 25.0) if form else 25.0
        result = None
        if form:
            try:
                result = levers.draw_orders(plan, heir / 100)
            except Exception as exc:  # noqa: BLE001
                flash_error_and_log(request, "The draw-order comparison failed", exc)
        current = sorted([lg for lg in plan.ledgers if lg.enabled],
                         key=lambda lg: lg.withdraw_priority)
        return render(request, "tools/draw_order.html", plan=plan, result=result, heir=heir,
                      current=current)

    async def draw_order_apply(self, request: Request):
        sid = session_id(request)
        form = await request.form()
        plan = self.store.get(sid)
        try:
            order = [int(x) for x in (form.get("order") or "").split(",") if x.strip()]
        except ValueError:
            order = []
        if not order:
            return redirect_to(request, "tool_draw_order")
        q = levers.apply_draw_order(plan, order)
        if form.get("as_scenario"):
            q.label = f"{plan.label} - new draw order"[:80]
            self.store.create(sid, q.label, q, activate=True)
            msg = f"Saved as a new scenario, “{q.label}”."
        else:
            self.store.put(sid, q)
            msg = "Draw order updated."
        return redirect_to(request, "plan_section", section="accounts", flash_message=msg)

    # -- health and care ---------------------------------------------------------
    def _health_values(self, plan, form):
        p0 = plan.persons[0]
        g = lambda k, d: _f(form.get(k), d) if form else d   # noqa: E731
        return dict(bridge=g("bridge", 0.0), bridge_to=g("bridge_to", max(65.0, p0.retire_age)),
                    later=g("later", 0.0), later_from=g("later_from", max(75.0, p0.retire_age)),
                    growth=g("growth", 2.0), care_prob=g("care_prob", 50.0),
                    care_from=g("care_from", 80.0), care_to=g("care_to", 90.0),
                    care_years=g("care_years", 3.0), care_cost=g("care_cost", 0.0),
                    care_all=bool(form.get("care_all")) if form else True)

    def _with_health(self, plan, v):
        import copy
        q = copy.deepcopy(plan)
        q.expenses = list(q.expenses) + levers.health_rows(
            q, v["bridge"], v["bridge_to"], v["later"], v["later_from"], v["growth"] / 100)
        if v["care_cost"] > 0:
            owners = range(len(q.persons)) if v["care_all"] else [0]
            q.care = list(q.care) + [
                CareRisk(f"Long-term care - {q.persons[i].label}", i, v["care_prob"] / 100,
                         v["care_from"], v["care_to"], v["care_years"], v["care_cost"],
                         v["growth"] / 100) for i in owners]
        return q

    async def health(self, request: Request):
        sid = session_id(request)
        plan = self.store.get(sid)
        form = await request.form() if request.method == "POST" else {}
        v = self._health_values(plan, form)
        result = None
        if form:
            try:
                before = levers.run(plan, levers.TOOL)
                after = levers.run(self._with_health(plan, v), levers.TOOL)
                result = dict(before=before, after=after)
            except Exception as exc:  # noqa: BLE001
                flash_error_and_log(request, "The health-cost test failed", exc)
        return render(request, "tools/health.html", plan=plan, v=v, result=result)

    async def health_add(self, request: Request):
        sid = session_id(request)
        form = await request.form()
        plan = self.store.get(sid)
        q = self._with_health(plan, self._health_values(plan, form))
        if form.get("as_scenario"):
            q.label = f"{plan.label} + health and care"[:80]
            self.store.create(sid, q.label, q, activate=True)
            msg = f"Saved as a new scenario, “{q.label}”."
        else:
            self.store.put(sid, q)
            msg = "Health costs and care risks added to your plan."
        return redirect_to(request, "plan_section", section="care", flash_message=msg)
