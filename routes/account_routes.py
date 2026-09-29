"""Accounts: every account a workspace has, on its own; portfolios are selections.

    /accounts                          all accounts, grouped by kind, and net worth
    /accounts/dialog                   add or edit an account (a dialog)
    /accounts/save                     save it (and which portfolios it belongs to)
    /accounts/{aid}                    one account: its holdings or its value
    /accounts/{aid}/portfolios         which portfolios include it
    /accounts/{aid}/holdings           add one holding
    /accounts/{aid}/import             paste holdings
    /accounts/{aid}/holdings/save      edit, move or delete holdings
    /holdings/{hid}/delete             delete one holding

An account is one of four kinds (portfolio/account_types.py): investments hold
positions; cash and property carry a value; debts pay themselves down. A
portfolio holds references to accounts, so a change here is seen at once by every
portfolio that includes the account, and by every plan linked to one of them.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import logging
from datetime import date

from fastapi import FastAPI, Request

from portfolio import account_types as at
from portfolio.assets import CASH_SYMBOL, CLASS_OPTIONS
from portfolio.importer import parse as parse_holdings
from portfolio.prices import collect_in_background
from portfolio.repository import NotFound, normalise_symbol
from web import charts
from web.fastapi_compat import flash, flash_error_and_log, redirect_to, render
from web.store import session_id

logger = logging.getLogger(__name__)
CURRENCIES = ["USD", "EUR", "GBP", "CAD", "AUD", "CHF", "JPY", "INR", "SGD", "HKD",
              "NZD", "SEK", "NOK", "DKK", "ZAR"]


def _f(form, key, default=None):
    raw = (form.get(key) or "").strip().replace(",", "").replace("%", "")
    if raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _q(name, question, hint="", widget=None, required=False, **kw):
    return dict(name=name, question=question, hint=hint, widget=widget, required=required, **kw)


def account_steps(info: dict, row: dict, editing: bool, portfolios: list) -> list[dict]:
    """The questions for one account, a step at a time (see plan/_dialog_macros.html)."""
    kind = info["kind"]
    first = [_q("name", "What do you call it?", "As your statements do - 'Fidelity "
                "brokerage', 'Chase savings'.", "text", True),
             _q("owner_person", "Whose is it?", "", "radio",
                options=[(str(k), label) for k, label in at.OWNERS]),
             _q("institution", "Where is it held?" if kind != "debt" else "Who is the lender?",
                "Optional.", "text")]
    if editing:
        first.insert(1, _q("type", "What kind of account is it?", "", "select",
                           options=[(t["key"], t["label"]) for t in at.of_kind(kind)]))
    steps = [dict(title="The account" if kind != "debt" else "The loan", fields=first)]
    money = _q("currency", "In what currency?", "The currency of its statements.", "select",
               options=[(c, c) for c in CURRENCIES + ([row.get("currency")]
                                                      if row.get("currency") not in CURRENCIES
                                                      else [])])
    if kind in ("cash", "property"):
        steps.append(dict(title="Its value", fields=[
            _q("value", "What is it worth today?" if kind == "property"
               else "What is the balance today?",
               "A fair estimate is fine; update it now and then." if kind == "property"
               else "Update it now and then; RetPlan remembers when.", "money", True), money]))
    elif kind == "debt":
        steps.append(dict(title="What you owe", fields=[
            _q("value", "How much is owed today?", "", "money", True),
            _q("rate", "At what interest rate?", "The yearly rate.", "pct", True),
            _q("years", "How many years are left?", "For a credit card, how long it "
               "would take to clear.", "number", True),
            _q("payment", "What do you pay each month?",
               "Optional - worked out from the rate and years if left blank.", "money"),
            money]))
    else:
        steps[0]["fields"].append(money)
    if portfolios:
        steps.append(dict(title="Portfolios", optional=True, fields=[
            _q("portfolios", "Which portfolios is it part of?",
               "Any number, or none for now. A portfolio made of other portfolios "
               "includes it through them.", "checks",
               options=[(str(p["id"]), p["name"]) for p in portfolios])]))
    return steps


class AccountRoutes:
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
        add("/accounts", self.index, methods=["GET"], name="accounts", **r)
        add("/accounts/dialog", self.dialog, methods=["GET"], name="account_dialog", **r)
        add("/accounts/save", self.save, methods=["POST"], name="account_save", **r)
        add("/accounts/{aid}", self.view, methods=["GET"], name="account_view", **r)
        add("/accounts/{aid}/delete", self.delete, methods=["POST"], name="account_delete", **r)
        add("/accounts/{aid}/duplicate", self.duplicate, methods=["POST"],
            name="account_duplicate", **r)
        add("/accounts/{aid}/portfolios", self.set_portfolios, methods=["POST"],
            name="account_portfolios", **r)
        add("/accounts/{aid}/refresh", self.refresh, methods=["POST"], name="account_refresh", **r)
        add("/accounts/{aid}/holdings", self.add_holding, methods=["POST"],
            name="holding_add", **r)
        add("/accounts/{aid}/import", self.import_holdings, methods=["POST"],
            name="holding_import", **r)
        add("/accounts/{aid}/holdings/save", self.save_holdings, methods=["POST"],
            name="holdings_save", **r)
        add("/holdings/{hid}/delete", self.delete_holding, methods=["POST"],
            name="holding_delete", **r)

    def _missing(self, request):
        return render(request, "error.html", status_code=404, code=404,
                      message="That account does not exist in this workspace.")

    def _back(self, request, form, aid=None, **kw):
        """Back to the portfolio the change was made from, else the account or the list."""
        pid = str(form.get("back_pid") or "")
        if pid.isdigit():
            return redirect_to(request, "portfolio_view", pid=int(pid), **kw)
        if aid:
            return redirect_to(request, "account_view", aid=aid, **kw)
        return redirect_to(request, "accounts", **kw)

    # -- all accounts ------------------------------------------------------
    async def index(self, request: Request):
        sid = session_id(request)
        v = self.repo.all_valuation(sid)
        memberships = {a.id: self.repo.portfolios_of(sid, a.id) for a in v.accounts}
        hist = self.app.state.networth.history(sid)
        chart = ""
        if len(hist) >= 2:
            chart = charts.date_line(
                [h["taken_on"] for h in hist],
                [("Net worth", [h["net"] for h in hist]),
                 ("Assets", [h["assets"] for h in hist]),
                 ("Debts", [h["liabilities"] for h in hist])],
                title="Net worth over time", desc="every account, recorded daily",
                zero_floor=True, y_fmt=charts._fmt_compact)
        return render(request, "accounts/index.html", v=v, kinds=at.KINDS,
                      memberships=memberships, hist=hist, chart=chart,
                      portfolios=self.repo.list(sid))

    # -- add / edit --------------------------------------------------------
    async def dialog(self, request: Request):
        sid = session_id(request)
        q = request.query_params
        partial = q.get("partial") == "1"
        acct, typ = None, q.get("type") or ""
        if q.get("aid"):
            try:
                acct = self.repo.account(sid, int(q["aid"]))
                typ = acct["type"]
            except (NotFound, ValueError):
                return self._missing(request)
        back = q.get("pid") or ""
        portfolios = self.repo.list(sid)
        ctx = dict(partial=partial, acct=acct, kinds=at.KINDS, types=at.TYPES,
                   kind=q.get("kind") or "", back_pid=back, heading="",
                   back_name=next((p["name"] for p in portfolios if str(p["id"]) == back), ""))
        if typ not in at.BY_KEY:
            return render(request, "accounts/dialog.html", mode="types", **ctx)
        info = at.BY_KEY[typ]
        if acct:
            row = dict(acct)
            row["portfolios"] = [str(p["id"]) for p in self.repo.portfolios_of(sid, acct["id"])
                                 if p["direct"]]
        else:
            rate, years = at.DEBT_DEFAULTS.get(typ, (None, None))
            row = dict(name=info["label"], type=typ, owner_person=0, institution="",
                       value=0.0, rate=rate, payment=None,
                       term_months=years * 12 if years else None, notes="",
                       currency=self.repo.home_currency(sid),
                       portfolios=[back] if back else [])
        if row.get("term_months"):
            row["years"] = round(row["term_months"] / 12, 1)
        ctx["heading"] = acct["name"] if acct else info["label"]
        return render(request, "accounts/dialog.html", mode="steps", info=info, row=row,
                      steps=account_steps(info, row, bool(acct), portfolios), **ctx)

    async def save(self, request: Request):
        sid = session_id(request)
        form = await request.form()
        typ = form.get("type") or ""
        if typ not in at.BY_KEY:
            flash(request, "Choose what kind of account it is.", "error")
            return self._back(request, form)
        info = at.BY_KEY[typ]
        fields = dict(name=(form.get("name") or "").strip() or info["label"], type=typ,
                      owner_person=int(_f(form, "owner_person", 0) or 0),
                      institution=(form.get("institution") or "").strip(),
                      currency=(form.get("currency") or "USD").strip().upper(),
                      notes=(form.get("notes") or "").strip())
        if info["kind"] != "investments":
            value = _f(form, "value", 0.0) or 0.0
            if value < 0:
                flash(request, "A value can't be negative - a debt is entered as what you owe.",
                      "error")
                return self._back(request, form)
            fields["value"] = value
        if info["kind"] == "debt":
            rate, years, payment = _f(form, "rate"), _f(form, "years"), _f(form, "payment")
            fields["rate"] = rate / 100 if rate is not None else None
            fields["term_months"] = int(round(years * 12)) if years else None
            fields["payment"] = payment if payment else (
                at.monthly_payment(fields["value"], fields["rate"] or 0.0, years)
                if years else None)
        chosen = [int(p) for p in (form.getlist("portfolios") if hasattr(form, "getlist")
                                   else []) if str(p).isdigit()]
        aid = _f(form, "aid")
        try:
            if aid:
                aid = int(aid)
                acct = self.repo.account(sid, aid)
                if at.get(acct["type"])["kind"] == "investments" and \
                        info["kind"] != "investments" and self.repo.holdings(sid, aid):
                    flash(request, "That account holds positions, so it stays an investment "
                                   "account. Move or remove them first.", "error")
                    return self._back(request, form, aid)
                if info["kind"] != "investments":
                    fields["as_of"] = date.today().isoformat()
                self.repo.update_account(sid, aid, **fields)
                if form.get("portfolios_asked"):
                    self._set_direct(sid, aid, chosen)
                msg = f"Saved '{fields['name']}'."
            else:
                aid = self.repo.create_account(
                    sid, fields["name"], typ, fields["owner_person"], fields["institution"],
                    fields.get("value", 0.0), None, fields.get("rate"), fields.get("payment"),
                    fields.get("term_months"), fields["notes"], fields["currency"], chosen)
                msg = f"Added '{fields['name']}'."
        except (NotFound, ValueError) as exc:
            flash(request, f"Could not save the account: {exc}", "error")
            return self._back(request, form)
        collect_in_background(self.app.state.collector, self.repo.missing_fx_pairs(), "fx")
        if info["kind"] == "investments" and not _f(form, "aid"):
            return redirect_to(request, "account_view", aid=aid, flash_message=
                               msg + " Now add what it holds: upload your broker's file, "
                                     "paste the positions, or add them one by one.")
        return self._back(request, form, aid, flash_message=msg)

    def _set_direct(self, sid, aid, chosen):
        """Put the account directly in exactly these portfolios."""
        for p in self.repo.list(sid):
            direct = any(a["id"] == aid for a in self.repo.direct_accounts(sid, p["id"]))
            if p["id"] in chosen and not direct:
                self.repo.add_to_portfolio(sid, p["id"], aid)
            elif p["id"] not in chosen and direct:
                self.repo.remove_from_portfolio(sid, p["id"], aid)

    async def set_portfolios(self, request: Request, aid: int):
        sid = session_id(request)
        form = await request.form()
        try:
            self.repo.account(sid, aid)
            self._set_direct(sid, aid, [int(p) for p in form.getlist("portfolios")
                                        if str(p).isdigit()])
        except NotFound:
            return self._missing(request)
        return redirect_to(request, "account_view", aid=aid, flash_message="Portfolios saved.")

    # -- one account -------------------------------------------------------
    async def view(self, request: Request, aid: int):
        sid = session_id(request)
        try:
            acct = self.repo.account(sid, aid)
        except NotFound:
            return self._missing(request)
        info = at.get(acct["type"])
        v = self.repo.account_valuation(sid, aid)
        return render(request, "accounts/view.html", acct=acct, info=info, a=v.accounts[0],
                      v=v, classes=CLASS_OPTIONS,
                      others=[x for x in self.repo.accounts(sid)
                              if at.get(x["type"])["kind"] == "investments" and x["id"] != aid],
                      memberships=self.repo.portfolios_of(sid, aid),
                      portfolios=self.repo.list(sid),
                      owner_label=at.OWNER_LABEL.get(acct["owner_person"], "You"))

    async def delete(self, request: Request, aid: int):
        sid = session_id(request)
        form = await request.form()
        try:
            acct = self.repo.account(sid, aid)
        except NotFound:
            return self._missing(request)
        self.repo.delete_account(sid, aid)
        pid = str(form.get("back_pid") or "")
        msg = f"Deleted '{acct['name']}' - from every portfolio."
        if pid.isdigit():
            return redirect_to(request, "portfolio_view", pid=int(pid), flash_message=msg)
        return redirect_to(request, "accounts", flash_message=msg)

    async def duplicate(self, request: Request, aid: int):
        sid = session_id(request)
        try:
            new = self.repo.duplicate_account(sid, aid)
        except NotFound:
            return self._missing(request)
        return redirect_to(request, "account_view", aid=new, flash_message=
                           "Copied, with its holdings - try another mix without touching "
                           "the original. It is in no portfolio yet.")

    async def refresh(self, request: Request, aid: int):
        sid = session_id(request)
        try:
            syms = sorted({h["symbol"] for h in self.repo.holdings(sid, aid)
                           if h["symbol"] != CASH_SYMBOL})
        except NotFound:
            return self._missing(request)
        syms = sorted(set(syms) | set(self.repo.fx_pairs_needed()))
        if not syms:
            flash(request, "Nothing to price.", "info")
        elif len(syms) <= 8:
            res = self.app.state.collector.collect(syms, reason="manual")
            flash(request, f"Prices refreshed: {res['ok']} updated"
                           + (f", {res['failed']} failed" if res["failed"] else "") + ".",
                  "success" if not res["failed"] else "warning")
        else:
            collect_in_background(self.app.state.collector, syms, "manual")
            flash(request, f"Refreshing {len(syms)} symbols in the background.", "info")
        return redirect_to(request, "account_view", aid=aid)

    # -- holdings ----------------------------------------------------------
    def _import_rows(self, sid, aid, text):
        added, bad = [], []
        for row in parse_holdings(text):
            if row.error:
                bad.append(f"line {row.line}: {row.error}")
                continue
            try:
                self.repo.add_holding(sid, aid, row.symbol, row.quantity, row.cost_basis,
                                      row.asset_class)
                added.append(normalise_symbol(row.symbol))
            except Exception as exc:  # noqa: BLE001
                bad.append(f"line {row.line}: {exc}")
        fetch = [s for s in added if s != CASH_SYMBOL]
        if fetch:
            collect_in_background(self.app.state.collector, fetch)
        return added, bad

    async def add_holding(self, request: Request, aid: int):
        sid = session_id(request)
        form = await request.form()
        try:
            self.repo.account(sid, aid)
        except NotFound:
            return self._missing(request)
        sym = normalise_symbol(form.get("symbol") or "")
        qty = _f(form, "quantity")
        if not sym or qty is None:
            flash(request, "A holding needs a symbol and a quantity (for cash, the amount).",
                  "error")
            return redirect_to(request, "account_view", aid=aid)
        cost = _f(form, "cost_basis")
        if cost is not None and form.get("cost_mode") == "per_unit":
            cost = cost * qty
        try:
            self.repo.add_holding(sid, aid, sym, qty, cost, form.get("asset_class") or "")
        except Exception as exc:  # noqa: BLE001
            flash_error_and_log(request, "Could not add the holding", exc)
            return redirect_to(request, "account_view", aid=aid)
        if sym != CASH_SYMBOL:
            sec = self.repo.security(sym) or {}
            if not sec.get("last_price"):
                # price it now, synchronously, so the page shows a value at once
                try:
                    self.app.state.collector.collect([sym], reason="new-symbol")
                except Exception:  # noqa: BLE001
                    logger.exception("first price for %s failed", sym)
                sec = self.repo.security(sym) or {}
                if sec.get("fetch_error"):
                    flash(request, f"Added {sym}, but it could not be priced: "
                                   f"{sec['fetch_error']}. Check the symbol.", "warning")
                    return redirect_to(request, "account_view", aid=aid)
        return redirect_to(request, "account_view", aid=aid, flash_message=f"Added {sym}.")

    async def import_holdings(self, request: Request, aid: int):
        sid = session_id(request)
        form = await request.form()
        try:
            self.repo.account(sid, aid)
        except NotFound:
            return self._missing(request)
        text = form.get("text") or ""
        upload = form.get("file")
        if upload is not None and hasattr(upload, "read"):
            raw = await upload.read()
            if raw:
                text = raw.decode("utf-8-sig", errors="replace")
        if form.get("replace"):
            for h in self.repo.holdings(sid, aid):
                self.repo.delete_holding(sid, h["id"])
        added, bad = self._import_rows(sid, aid, text)
        if bad:
            flash(request, f"{len(bad)} line(s) skipped: " + "; ".join(bad[:6]), "warning")
        if added:
            flash(request, f"Imported {len(added)} holding(s). Prices are being fetched "
                           "in the background - reload in a few seconds.", "success")
        elif not bad:
            flash(request, "Nothing to import.", "warning")
        return redirect_to(request, "account_view", aid=aid)

    async def save_holdings(self, request: Request, aid: int):
        """The holdings table is one form: edit quantities, costs, classes; move a
        holding to another investment account."""
        sid = session_id(request)
        form = await request.form()
        try:
            holdings = self.repo.holdings(sid, aid)
        except NotFound:
            return self._missing(request)
        moved = 0
        for h in holdings:
            k = f"h-{h['id']}-"
            if form.get(k + "delete"):
                self.repo.delete_holding(sid, h["id"])
                continue
            if (k + "quantity") not in form:
                continue
            fields = dict(quantity=_f(form, k + "quantity", h["quantity"]),
                          cost_basis=_f(form, k + "cost_basis"),
                          asset_class=form.get(k + "asset_class") or "")
            if fields["asset_class"] == "__inherit__":
                fields["asset_class"] = ""
            move = _f(form, k + "account_id")
            if move and int(move) != aid:
                fields["account_id"] = int(move)
                moved += 1
            try:
                self.repo.update_holding(sid, h["id"], **fields)
            except (NotFound, ValueError) as exc:
                flash(request, f"{h['symbol']}: {exc}", "error")
        return redirect_to(request, "account_view", aid=aid, flash_message=
                           "Holdings saved." + (f" {moved} moved to another account."
                                                if moved else ""))

    async def delete_holding(self, request: Request, hid: int):
        sid = session_id(request)
        try:
            h = self.repo.holding(sid, hid)
        except NotFound:
            return self._missing(request)
        self.repo.delete_holding(sid, hid)
        return redirect_to(request, "account_view", aid=h["account_id"],
                           flash_message="Removed.")
