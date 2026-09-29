"""Net worth over time: snapshots you take, and portfolio values recorded daily.

    GET  /networth                    history, charts and a snapshot form
    POST /networth/snapshot           record today's (or a dated) snapshot
    POST /networth/{sid}/delete       remove a snapshot
    POST /networth/{sid}/to-plan      bring the plan's balances and debts up to date

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import logging
from datetime import date

from fastapi import FastAPI, Request

from web import charts
from web.fastapi_compat import flash, redirect_to, render
from web.store import session_id

logger = logging.getLogger(__name__)


def _f(v):
    try:
        t = str(v).strip().replace(",", "")
        return float(t) if t else 0.0
    except (TypeError, ValueError):
        return 0.0


class NetWorthRoutes:
    def __init__(self, app: FastAPI, store):
        self.app = app
        self.store = store
        self._register_routes()

    def _register_routes(self) -> None:
        add = self.app.add_api_route
        r = dict(include_in_schema=False)
        add("/networth", self.index, methods=["GET"], name="networth", **r)
        add("/networth/snapshot", self.snapshot, methods=["POST"], name="networth_snapshot", **r)
        add("/networth/{snap}/delete", self.delete, methods=["POST"], name="networth_delete", **r)
        add("/networth/{snap}/to-plan", self.to_plan, methods=["POST"], name="networth_to_plan", **r)

    def _prefill(self, sid, plan):
        """Today's items: the plan's accounts and debts, and every portfolio's value."""
        repo = self.app.state.portfolios
        items = [dict(name=lg.label, kind="account", value=round(lg.opening), ref=i)
                 for i, lg in enumerate(plan.ledgers) if lg.enabled]
        for p in repo.list(sid):
            v = repo.valuation(sid, p["id"])
            items.append(dict(name=f"Portfolio: {p['name']}", kind="portfolio",
                              value=round(v.total), ref=p["id"]))
        items += [dict(name=ln.label, kind="debt", value=round(ln.balance), ref=i)
                  for i, ln in enumerate(plan.loans) if ln.enabled and ln.balance > 0]
        return items

    async def index(self, request: Request):
        sid = session_id(request)
        plan = self.store.get(sid)
        nw = self.app.state.networth
        snaps = nw.manual(sid)
        series = nw.portfolio_series(sid)
        names = {str(p["id"]): p["name"] for p in self.app.state.portfolios.list(sid)}
        chart_nw = ""
        if len(snaps) >= 2:
            chart_nw = charts.date_line(
                [s["taken_on"] for s in snaps],
                [("Net worth", [s["net"] for s in snaps]), ("Assets", [s["assets"] for s in snaps]),
                 ("Debts", [s["liabilities"] for s in snaps])],
                title="Net worth over time", desc="from your snapshots", zero_floor=True)
        chart_pf = ""
        if series:
            dates = sorted({d for s in series.values() for d, _ in s})
            lines = []
            for ref, pts in series.items():
                m = dict(pts)
                lines.append((names.get(ref, f"Portfolio {ref}"), [m.get(d) for d in dates]))
            if len(dates) >= 2:
                chart_pf = charts.date_line(dates, lines, title="Portfolio values, recorded daily",
                                            desc="after each price collection")
        return render(request, "networth.html", plan=plan, snaps=list(reversed(snaps)),
                      prefill=self._prefill(sid, plan), chart_nw=chart_nw, chart_pf=chart_pf,
                      series=series, names=names, today=date.today().isoformat())

    async def snapshot(self, request: Request):
        sid = session_id(request)
        form = await request.form()
        items = []
        keys = sorted({k.split("-")[1] for k in form.keys() if k.startswith("it-")}, key=int)
        for i in keys:
            name = (form.get(f"it-{i}-name") or "").strip()
            kind = form.get(f"it-{i}-kind") or "asset"
            if kind not in ("account", "portfolio", "asset", "debt"):
                kind = "asset"
            ref = form.get(f"it-{i}-ref") or ""
            items.append(dict(name=name, kind=kind, value=_f(form.get(f"it-{i}-value")), ref=ref))
        try:
            self.app.state.networth.record(sid, items, form.get("taken_on") or None,
                                           form.get("note") or "")
        except ValueError:
            flash(request, "That date is not valid - use the date picker.", "error")
            return redirect_to(request, "networth")
        return redirect_to(request, "networth", flash_message="Snapshot saved.")

    async def delete(self, request: Request, snap: int):
        self.app.state.networth.delete(session_id(request), snap)
        return redirect_to(request, "networth", flash_message="Snapshot deleted.")

    async def to_plan(self, request: Request, snap: int):
        """Set each plan account's balance, and each loan's balance, to the snapshot's."""
        sid = session_id(request)
        s = self.app.state.networth.get(sid, snap)
        if s is None:
            return redirect_to(request, "networth")
        plan = self.store.get(sid)
        n = 0
        for it in s["data"].get("items", []):
            try:
                ref = int(it.get("ref"))
            except (TypeError, ValueError):
                continue
            if it["kind"] == "account" and 0 <= ref < len(plan.ledgers):
                plan.ledgers[ref].opening = float(it["value"])
                n += 1
            elif it["kind"] == "debt" and 0 <= ref < len(plan.loans):
                plan.loans[ref].balance = abs(float(it["value"]))
                n += 1
        self.store.put(sid, plan)
        return redirect_to(request, "plan_section", section="accounts", flash_message=
                           f"Updated {n} balance(s) in {plan.label} from the snapshot of "
                           f"{s['taken_on']}.")
