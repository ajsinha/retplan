"""The portfolio builder: upload a spreadsheet of positions, review, confirm.

    GET  /portfolios/build[?pid=&aid=]  the upload form: into one account (aid), into
                                        a portfolio's accounts (pid), or a new portfolio
    POST /portfolios/build              analyse the file (portfolio/builder.py),
                                        keep the result as a draft, go to review
    GET  /portfolios/build/{did}        review every proposed holding
    POST /portfolios/build/{did}        confirm
    POST /portfolios/build/{did}/delete discard the draft

Uploading into one account puts every position there. A file listing several
accounts (an account column, or one sheet per account) makes one account per
name, its type guessed from the name ("Roth IRA", "401k") and confirmed on the
review. Nothing reaches a portfolio until the review is confirmed.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request

from portfolio import account_types as at
from portfolio import builder
from portfolio.assets import CASH_SYMBOL, CLASSES
from portfolio.prices import collect_in_background
from portfolio.repository import NotFound, normalise_symbol
from web.fastapi_compat import flash, flash_error_and_log, redirect_to, render
from web.store import session_id

logger = logging.getLogger(__name__)
MAX_UPLOAD = 10 * 1024 * 1024
DEFAULT_ACCOUNT = "Brokerage"          # for positions the file does not assign
CURRENCIES = ["USD", "EUR", "GBP", "CAD", "AUD", "CHF", "JPY", "INR", "SGD", "HKD",
              "NZD", "SEK", "NOK", "DKK", "ZAR"]


def _f(v):
    try:
        t = str(v).strip().replace(",", "")
        return float(t) if t else None
    except (TypeError, ValueError):
        return None


class BuilderRoutes:
    def __init__(self, app: FastAPI, store):
        self.app = app
        self.store = store
        self._register_routes()

    @property
    def repo(self):
        return self.app.state.portfolios

    def _register_routes(self) -> None:
        add = self.app.add_api_route
        r = dict(include_in_schema=False)
        # registered before the portfolio routes' /portfolios/{pid}
        add("/portfolios/build", self.form, methods=["GET"], name="builder", **r)
        add("/portfolios/build", self.upload, methods=["POST"], name="builder_upload", **r)
        add("/portfolios/build/{did}", self.review, methods=["GET"], name="builder_review", **r)
        add("/portfolios/build/{did}", self.confirm, methods=["POST"],
            name="builder_confirm", **r)
        add("/portfolios/build/{did}/delete", self.discard, methods=["POST"],
            name="builder_discard", **r)

    def _target(self, sid, pid, aid):
        """(portfolio, account) the upload is aimed at; either may be None."""
        pf = acct = None
        try:
            if pid:
                pf = self.repo.get(sid, int(pid))
                if aid:
                    acct = self.repo.account(sid, int(pid), int(aid))
        except (NotFound, ValueError):
            return None, None
        return pf, acct

    async def form(self, request: Request):
        sid = session_id(request)
        pf, acct = self._target(sid, request.query_params.get("pid"),
                                request.query_params.get("aid"))
        return render(request, "portfolio/build.html", drafts=self.repo.drafts(sid),
                      portfolios=self.repo.list(sid), pf=pf, acct=acct)

    async def upload(self, request: Request):
        sid = session_id(request)
        form = await request.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            flash(request, "Choose a spreadsheet to upload.", "error")
            return redirect_to(request, "builder")
        content = await upload.read(MAX_UPLOAD + 1)
        name = os.path.basename(upload.filename or "positions")
        if not content:
            flash(request, "That file is empty.", "error")
            return redirect_to(request, "builder")
        if len(content) > MAX_UPLOAD:
            flash(request, "That file is over 10 MB; export just the positions.", "error")
            return redirect_to(request, "builder")
        try:
            draft = builder.analyse(content, name)
        except ValueError as exc:
            flash(request, str(exc).capitalize() + ".", "error")
            return redirect_to(request, "builder")
        except Exception as exc:  # noqa: BLE001
            flash_error_and_log(request, "That file could not be read", exc)
            return redirect_to(request, "builder")
        if not draft["lines"]:
            for m in draft["messages"]:
                flash(request, m, "warning")
            return redirect_to(request, "builder")
        pf, acct = self._target(sid, form.get("pid"), form.get("aid"))
        draft["target_pid"] = pf["id"] if pf else None
        draft["target_aid"] = acct["id"] if acct else None
        did = self.repo.save_draft(sid, name, draft)
        return redirect_to(request, "builder_review", did=did)

    async def review(self, request: Request, did: int):
        sid = session_id(request)
        try:
            d = self.repo.draft(sid, did)
        except NotFound:
            flash(request, "That draft has expired or does not exist.", "warning")
            return redirect_to(request, "builder")
        stem = os.path.splitext(d["filename"])[0].replace("_", " ").strip() or "Imported"
        pf, acct = self._target(sid, d.get("target_pid"), d.get("target_aid"))
        names = []
        for ln in d["lines"]:
            n = (ln.get("account") or "").strip() or DEFAULT_ACCOUNT
            if n not in names:
                names.append(n)
        return render(request, "portfolio/build_review.html", d=d,
                      portfolios=self.repo.list(sid), classes=builder.classes(),
                      class_info=CLASSES, currencies=CURRENCIES, pf=pf, acct=acct,
                      accounts=[(n, at.guess(n)) for n in names],
                      investment_types=at.of_kind("investments"),
                      default_name=stem[:60], default_currency=builder.guess_currency(d))

    async def confirm(self, request: Request, did: int):
        sid = session_id(request)
        form = await request.form()
        try:
            d = self.repo.draft(sid, did)
        except NotFound:
            flash(request, "That draft has expired or does not exist.", "warning")
            return redirect_to(request, "builder")
        rows = []
        for i, ln in enumerate(d["lines"]):
            k = f"l{i}-"
            if not form.get(k + "include"):
                continue
            sym = normalise_symbol(form.get(k + "symbol") or "")
            qty = _f(form.get(k + "quantity"))
            if not sym or qty is None:
                flash(request, f"Line {i + 1} ({ln.get('raw_name') or ln.get('raw_symbol')})"
                               " needs a symbol and a quantity - left out.", "warning")
                continue
            cls = form.get(k + "asset_class") or ""
            rows.append(dict(symbol=sym, quantity=qty, cost=_f(form.get(k + "cost")),
                             account=(form.get(k + "account") or "").strip(),
                             asset_class=cls if cls in CLASSES else ""))
        if not rows:
            flash(request, "Nothing was ticked to import.", "warning")
            return redirect_to(request, "builder_review", did=did)
        pf, acct = self._target(sid, d.get("target_pid"), d.get("target_aid"))
        try:
            if acct:                                   # everything into one account
                pid, aid = pf["id"], acct["id"]
                if form.get("replace"):
                    for h in self.repo.holdings(sid, pid, aid):
                        self.repo.delete_holding(sid, pid, h["id"])
                for r in rows:
                    self.repo.add_holding(sid, pid, aid, r["symbol"], r["quantity"],
                                          r["cost"], r["asset_class"])
                where = dict(endpoint="account_view", pid=pid, aid=aid)
            else:                                      # one account per name in the file
                if (form.get("mode") or "new") == "new":
                    pid = self.repo.create(sid, form.get("name") or "Imported portfolio",
                                           form.get("currency") or "USD",
                                           f"Built from {d['filename']}")
                else:
                    pid = int(form.get("portfolio") or 0)
                    self.repo.get(sid, pid)
                chosen = {}
                for i in range(int(form.get("n_accounts") or 0)):
                    name = (form.get(f"acct-{i}-name") or "").strip()
                    typ = form.get(f"acct-{i}-type") or ""
                    if name:
                        chosen[name.lower()] = typ if typ in at.BY_KEY else None
                ids = {}
                for r in rows:
                    name = r["account"] or DEFAULT_ACCOUNT
                    if name.lower() not in ids:
                        ids[name.lower()] = self.repo.find_or_create_account(
                            sid, pid, name, chosen.get(name.lower()))
                    self.repo.add_holding(sid, pid, ids[name.lower()], r["symbol"],
                                          r["quantity"], r["cost"], r["asset_class"])
                where = dict(endpoint="portfolio_view", pid=pid)
        except (NotFound, ValueError) as exc:
            flash(request, f"Could not import: {exc}", "error")
            return redirect_to(request, "builder_review", did=did)
        fetch = sorted({r["symbol"] for r in rows if r["symbol"] != CASH_SYMBOL})
        if fetch:
            collect_in_background(self.app.state.collector, fetch, "import")
        self.repo.delete_draft(sid, did)
        endpoint = where.pop("endpoint")
        return redirect_to(request, endpoint, flash_message=
                           f"Imported {len(rows)} holding(s). Prices are arriving in the "
                           "background - reload in a few seconds.", **where)

    async def discard(self, request: Request, did: int):
        self.repo.delete_draft(session_id(request), did)
        return redirect_to(request, "builder", flash_message="Draft discarded.")
