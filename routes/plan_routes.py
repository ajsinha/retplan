"""Plan editor routes.

Each editable table declares its columns once, here, as a field specification.
The templates render from that spec and the POST handler parses against the same
spec, so a column cannot drift between the form and the parser - the failure mode
that makes hand-written CRUD forms rot.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request

from retplan.plan import (CATEGORIES, Conversion, ExpenseRow, IncomeRow, Ledger, Loan,
                          Person, Wrapper)
from web.fastapi_compat import flash, flash_error_and_log, redirect_to, render
from web.help_catalog import CONTEXT_HELP
from web.store import session_id

logger = logging.getLogger(__name__)

YESNO = ["Yes", "No"]
BASIS = ["real", "nominal"]
CAPTYPE = ["none", "absolute", "pct_income"]
REBAL = ["annual", "none"]
POLICIES = ["fixed_real", "fixed_nominal", "pct_portfolio", "vpw", "guardrails",
            "table"]
# Jinja has no list comprehensions, so option pairs are built here.
POLICY_OPTIONS = [(p, p.replace("_", " ")) for p in POLICIES]


def F(name, label, kind="number", **kw):
    """One column of an editable table."""
    return dict(name=name, label=label, kind=kind, **kw)


INCOME_FIELDS = [
    F("label", "Label", "text", width="wide"),
    F("owner", "Owner", "select", options=[(0, "Person 1"), (1, "Person 2")]),
    F("category", "Category", "select", options=[(c, c.replace("_", " ")) for c in CATEGORIES]),
    F("amount", "Amount / year", "money"),
    F("basis", "Basis", "select", options=[(b, b) for b in BASIS], adv=True,
      help="real keeps pace with inflation; nominal is a fixed future amount"),
    F("growth", "Growth", "pct", help="growth in the chosen basis, per year", adv=True),
    F("start_age", "From age", "number"),
    F("end_age", "To age", "number"),
    F("taxable_fraction", "Taxable", "pct", adv=True,
      help="100 = fully taxable, 0 = tax free, 75 = a 25% tax-free element"),
    F("survivor_fraction", "Survivor", "pct", adv=True,
      help="share that continues after the owner dies"),
    F("probability", "Probability", "pct", adv=True),
]

EXPENSE_FIELDS = [
    F("label", "Label", "text", width="wide"),
    F("amount", "Amount / year", "money"),
    F("basis", "Basis", "select", options=[(b, b) for b in BASIS], adv=True),
    F("essential", "Essential", "check",
      help="essential spending is a floor no flexible policy may cut"),
    F("infl_delta", "Above CPI", "pct", adv=True,
      help="care and education typically run 1-3% above general inflation"),
    F("smile", "Age curve", "check", adv=True,
      help="apply the spending smile - real spending drifts down with age"),
    F("start_age", "From age", "number"),
    F("end_age", "To age", "number"),
    F("recur_years", "Every N years", "int", help="0 or 1 = every year", adv=True),
    F("probability", "Probability", "pct", adv=True),
]

LOAN_FIELDS = [
    F("label", "Label", "text", width="wide"),
    F("balance", "Balance", "money"),
    F("rate", "Rate", "pct"),
    F("term_years", "Years left", "int"),
    F("kind", "Type", "select", adv=True,
      options=[(k, k.replace("_", " ")) for k in ("amortising", "interest_only", "bullet")]),
    F("extra_payment", "Overpayment / year", "money", adv=True),
    F("start_year", "Starts in year", "int", adv=True),
]

WRAPPER_FIELDS = [
    F("label", "Wrapper", "text", width="wide"),
    F("contribution_deductible", "Contribution deductible", "pct",
      help="share of a contribution that reduces taxable income (the first E in EET)"),
    F("withdrawal_taxable_fraction", "Withdrawal taxable", "pct",
      help="1 = taxed in full on the way out; 0 = never taxed again"),
    F("realises_capital_gains", "Realises gains", "check",
      help="withdrawals are taxable only to the extent they are gain"),
    F("cap_type", "Cap", "select", options=[(c, c.replace("_", " ")) for c in CAPTYPE], adv=True),
    F("cap_value", "Cap value", "money", adv=True),
    F("early_age", "Penalty before age", "number", adv=True),
    F("early_penalty", "Penalty", "pct", adv=True),
    F("mrd_age", "Forced draws from", "number", help="999 = never", adv=True),
    F("lock_age", "Locked until", "number", adv=True),
    F("liquid", "Liquid", "check", adv=True,
      help="illiquid holdings are excluded from drawdown unless sold"),
]

LEDGER_FIELDS = [
    F("label", "Account", "text", width="wide"),
    F("wrapper", "Wrapper", "wrapper"),
    F("owner", "Owner", "select", options=[(0, "Person 1"), (1, "Person 2")]),
    F("opening", "Balance", "money"),
    F("basis", "Cost basis", "money", adv=True),
    F("withdraw_priority", "Draw order", "int", adv=True),
    F("contribute_priority", "Pay-in order", "int", adv=True),
    F("contribution", "Contribution / year", "money"),
    F("contribution_pct_income", "% of earnings", "pct"),
    F("employer_match_pct", "Employer match", "pct"),
    F("employer_match_cap_pct", "Match cap", "pct", adv=True),
    F("rebalance", "Rebalance", "select", options=[(r, r) for r in REBAL], adv=True),
]

CONVERSION_FIELDS = [
    F("label", "Label", "text", width="wide"),
    F("from_ledger", "From account", "ledger",
      help="usually a pension or other account taxed on the way out"),
    F("to_ledger", "To account", "ledger", help="usually a tax-free account"),
    F("mode", "How much", "select",
      options=[("amount", "a fixed amount"), ("fill_to", "fill taxable income to")],
      help="a fixed amount a year, or just enough to bring taxable income up to the figure"),
    F("amount", "Amount / target", "money"),
    F("start_age", "From age", "number"),
    F("end_age", "Until age", "number", help="the conversion stops before this age"),
]

SECTIONS = [
    ("household", "Household", "bi-people", "Who the plan covers and how long it runs."),
    ("income", "Income", "bi-arrow-down-circle", "Every stream of money coming in."),
    ("expenses", "Spending", "bi-arrow-up-circle", "What the money is for."),
    ("debt", "Debt", "bi-bank", "Mortgages and loans, amortised year by year."),
    ("wrappers", "Tax wrappers", "bi-shield-lock", "When money is taxed: in, during, or out."),
    ("accounts", "Accounts", "bi-wallet2", "Balances, allocation and drawdown order."),
    ("markets", "Markets", "bi-graph-up-arrow", "Returns, regimes, crashes, inflation, fees."),
    ("tax", "Tax", "bi-percent", "A table of bands. No jurisdiction is assumed."),
    ("policy", "Policy", "bi-sliders", "How much you take out, and what counts as success."),
    ("conversions", "Conversions", "bi-arrow-left-right",
     "Move money between accounts each year, paying the tax now to pay less later."),
]


def completeness(plan) -> dict:
    """One short line per section for the editor's rail: what is in it."""
    def n(k, word):
        if k == 1:
            return f"{k} {word}"
        return f"{k} {word}es" if word.endswith("s") else f"{k} {word}s"
    active = [l for l in plan.ledgers if l.enabled]
    return {
        "household": " · ".join(f"{p.label} {p.age:.0f}→{p.retire_age:.0f}"
                                for p in plan.persons[:2]),
        "income": n(len(plan.income), "stream") if plan.income else "none yet",
        "expenses": (f"{sum(e.amount for e in plan.expenses if not e.recur_years):,.0f} / yr"
                     if plan.expenses else "none yet"),
        "debt": n(len(plan.loans), "loan") if plan.loans else "none",
        "wrappers": n(len(plan.wrappers), "wrapper"),
        "accounts": f"{sum(l.opening for l in active):,.0f} in {n(len(active), 'account')}",
        "markets": n(len(plan.market.assets), "asset class"),
        "tax": n(len(plan.tax.ordinary.lowers), "band"),
        "policy": plan.policy.method.replace("_", " "),
        "conversions": n(len(plan.conversions), "conversion") if plan.conversions else "none",
    }


# --------------------------------------------------------------------------- #
# form parsing
# --------------------------------------------------------------------------- #
def _num(form, key, default=0.0):
    raw = (form.get(key) or "").strip().replace(",", "")
    if raw in ("", "-"):
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _pct(form, key, default=0.0):
    """Percent inputs are typed as percents and stored as fractions."""
    raw = (form.get(key) or "").strip().replace("%", "").replace(",", "")
    if raw == "":
        return default
    try:
        return float(raw) / 100.0
    except ValueError:
        return default


def parse_rows(form, prefix: str, fields: list) -> list:
    """Collect ``prefix-<i>-<field>`` inputs into row dicts, skipping deletions."""
    indices = set()
    for key in form.keys():
        if key.startswith(f"{prefix}-"):
            parts = key.split("-", 2)
            if len(parts) == 3 and parts[1].isdigit():
                indices.add(int(parts[1]))
    rows = []
    for i in sorted(indices):
        if form.get(f"delete-{prefix}-{i}"):
            continue
        row = {}
        for f in fields:
            key = f"{prefix}-{i}-{f['name']}"
            kind = f["kind"]
            if kind == "check":
                row[f["name"]] = bool(form.get(key))
            elif kind in ("money", "number"):
                row[f["name"]] = _num(form, key)
            elif kind == "int":
                row[f["name"]] = int(_num(form, key))
            elif kind == "pct":
                row[f["name"]] = _pct(form, key)
            elif kind in ("wrapper", "ledger"):
                row[f["name"]] = int(_num(form, key))
            elif kind == "select":
                val = form.get(key, "")
                opts = f.get("options") or []
                if opts and isinstance(opts[0][0], int):
                    row[f["name"]] = int(_num(form, key))
                else:
                    row[f["name"]] = val
            else:
                row[f["name"]] = (form.get(key) or "").strip()
        if prefix in ("income", "expenses", "debt") and not row.get("label") \
                and not row.get("amount") and not row.get("balance"):
            continue
        rows.append(row)
    return rows


class PlanRoutes:
    """The plan editor."""

    def __init__(self, app: FastAPI, store):
        self.app = app
        self.store = store
        self._register_routes()

    def _register_routes(self) -> None:
        add = self.app.add_api_route
        add("/plan", self.section, methods=["GET"], name="plan",
            include_in_schema=False)
        add("/plan/{section}", self.section, methods=["GET"], name="plan_section",
            include_in_schema=False)
        add("/plan/{section}", self.save, methods=["POST"], name="plan_save",
            include_in_schema=False)
        add("/plan/{section}/add", self.add_row, methods=["POST"],
            name="plan_add_row", include_in_schema=False)

    # -- render ------------------------------------------------------------
    async def section(self, request: Request, section: str = "household"):
        plan = self.store.get(session_id(request))
        known = {s[0] for s in SECTIONS}
        if section not in known:
            section = "household"
        fields_for = {"income": INCOME_FIELDS, "expenses": EXPENSE_FIELDS,
                      "debt": LOAN_FIELDS, "wrappers": WRAPPER_FIELDS,
                      "accounts": LEDGER_FIELDS, "conversions": CONVERSION_FIELDS}
        ctx = dict(plan=plan, section=section, sections=SECTIONS,
                   context_help=CONTEXT_HELP, completeness=completeness(plan),
                   has_advanced=any(f.get("adv") for f in fields_for.get(section, [])),
                   income_fields=INCOME_FIELDS, expense_fields=EXPENSE_FIELDS,
                   loan_fields=LOAN_FIELDS, wrapper_fields=WRAPPER_FIELDS,
                   ledger_fields=LEDGER_FIELDS, conversion_fields=CONVERSION_FIELDS,
                   policies=POLICIES,
                   policy_options=POLICY_OPTIONS,
                   categories=CATEGORIES)
        return render(request, f"plan/{section}.html", **ctx)

    # -- mutate ------------------------------------------------------------
    async def add_row(self, request: Request, section: str):
        sid = session_id(request)
        plan = self.store.get(sid)
        try:
            if section == "income":
                plan.income.append(IncomeRow("New income", 0, "employment", 0.0,
                                             "real", 0.0, False, 0, 200, 1.0, 0.0, 1.0))
            elif section == "expenses":
                plan.expenses.append(ExpenseRow("New expense", 0.0, "real", True,
                                                0.0, False, 0, 200, -1, 0, 1.0))
            elif section == "debt":
                plan.loans.append(Loan("New loan", 0.0, 0.05, 20, "amortising"))
            elif section == "wrappers":
                plan.wrappers.append(Wrapper(f"Wrapper {len(plan.wrappers) + 1}"))
            elif section == "accounts":
                n = len(plan.ledgers) + 1
                w = [1.0] + [0.0] * (len(plan.market.assets) - 1)
                plan.ledgers.append(Ledger(f"Account {n}", 0, 0, 0.0, 0.0, w, [],
                                           200, 200, n, n))
            elif section == "conversions":
                n_l = len(plan.ledgers)
                plan.conversions.append(Conversion("New conversion", 0, min(1, n_l - 1), "amount",
                                                   0.0, plan.persons[0].retire_age,
                                                   plan.persons[0].retire_age + 5))
            elif section == "household" and len(plan.persons) < 4:
                plan.persons.append(Person(f"Person {len(plan.persons) + 1}", 40, 65, 95))
            self.store.put(sid, plan)
            return redirect_to(request, "plan_section", section=section)
        except Exception as exc:  # noqa: BLE001
            flash_error_and_log(request, "Could not add the row", exc)
            return redirect_to(request, "plan_section", section=section)

    async def save(self, request: Request, section: str):
        sid = session_id(request)
        plan = self.store.get(sid)
        form = await request.form()
        if not hasattr(self, f"_save_{section}"):
            flash(request, f"There is no plan section called '{section}'.", "error")
            return redirect_to(request, "plan_section", section="household")
        self._notes = []
        try:
            getattr(self, f"_save_{section}")(plan, form)
        except Exception as exc:  # noqa: BLE001
            flash_error_and_log(request, f"Could not save {section}", exc)
            return redirect_to(request, "plan_section", section=section)
        self.store.put(sid, plan)
        for note in self._notes:
            flash(request, note, "warning")
        return redirect_to(request, "plan_section",
                           flash_message=f"{section.title()} saved.",
                           section=section)

    # -- per-section savers ------------------------------------------------
    def _save_household(self, plan, form):
        people = []
        for i in range(4):
            if f"person-{i}-age" not in form:
                continue
            age = _num(form, f"person-{i}-age", 0)
            name = (form.get(f"person-{i}-label") or f"Person {i + 1}").strip()
            if age <= 0:
                continue
            people.append(Person(name, age, _num(form, f"person-{i}-retire_age", 65),
                                 _num(form, f"person-{i}-death_age", 95)))
        plan.persons = people or plan.persons
        plan.label = (form.get("label") or plan.label).strip()
        plan.horizon = max(1, min(80, int(_num(form, "horizon", plan.horizon))))
        plan.timing = form.get("timing") or plan.timing
        plan.seed = int(_num(form, "seed", plan.seed))
        ages = [float(a) for a in (form.getlist("smile_age") if hasattr(form, "getlist")
                                   else [])]
        mults = [float(m) for m in (form.getlist("smile_mult") if hasattr(form, "getlist")
                                    else [])]
        if ages and mults and len(ages) == len(mults):
            plan.smile.ages, plan.smile.mult = ages, mults

    def _save_income(self, plan, form):
        plan.income = [IncomeRow(**r) for r in parse_rows(form, "income", INCOME_FIELDS)]

    def _save_expenses(self, plan, form):
        rows = parse_rows(form, "expenses", EXPENSE_FIELDS)
        plan.expenses = [ExpenseRow(owner=-1, **r) for r in rows]

    def _save_debt(self, plan, form):
        plan.loans = [Loan(**r) for r in parse_rows(form, "debt", LOAN_FIELDS)]

    def _save_wrappers(self, plan, form):
        rows = parse_rows(form, "wrappers", WRAPPER_FIELDS)
        kept = []
        for i, r in enumerate(rows):
            old = plan.wrappers[i] if i < len(plan.wrappers) else Wrapper()
            w = Wrapper(**r)
            w.mrd_divisors = old.mrd_divisors       # kept on the markets page
            w.growth_taxed_annually = old.growth_taxed_annually
            w.growth_taxable_fraction = old.growth_taxable_fraction
            w.catch_up_age, w.catch_up_amount = old.catch_up_age, old.catch_up_amount
            kept.append(w)
        plan.wrappers = kept or plan.wrappers

    def _save_accounts(self, plan, form):
        rows = parse_rows(form, "accounts", LEDGER_FIELDS)
        n_assets = len(plan.market.assets)
        kept = []
        for i, r in enumerate(rows):
            old = plan.ledgers[i] if i < len(plan.ledgers) else Ledger()
            lg = Ledger(**r)
            lg.weights = [_pct(form, f"accounts-{i}-w{j}") for j in range(n_assets)]
            if sum(lg.weights) <= 0:
                lg.weights = old.weights or ([1.0] + [0.0] * (n_assets - 1))
            glide = [_pct(form, f"accounts-{i}-v{j}") for j in range(n_assets)]
            lg.glide_to = glide if sum(glide) > 0 else []
            lg.glide_start_age = _num(form, f"accounts-{i}-glide_start_age", 200)
            lg.glide_end_age = _num(form, f"accounts-{i}-glide_end_age", 200)
            kept.append(lg)
        plan.ledgers = kept or plan.ledgers
        plan.policy.sweep_ledger = max(0, int(_num(form, "sweep_ledger", 0)))

    def _save_conversions(self, plan, form):
        rows = parse_rows(form, "conversions", CONVERSION_FIELDS)
        plan.conversions = [Conversion(**r) for r in rows
                            if r.get("from_ledger") != r.get("to_ledger")]

    def _save_markets(self, plan, form):
        for j, a in enumerate(plan.market.assets):
            a.label = (form.get(f"asset-{j}-label") or a.label).strip()
            a.mu = _pct(form, f"asset-{j}-mu", a.mu)
            a.sigma = _pct(form, f"asset-{j}-sigma", a.sigma)
            a.income_yield = _pct(form, f"asset-{j}-income_yield", a.income_yield)
            a.ter = _pct(form, f"asset-{j}-ter", a.ter)
            a.crash_beta = _num(form, f"asset-{j}-crash_beta", a.crash_beta)
        n = len(plan.market.assets)
        corr = []
        for i in range(n):
            row = []
            for j in range(n):
                key = f"corr-{i}-{j}"
                row.append(1.0 if i == j else _num(form, key,
                                                   plan.market.corr[i][j]))
            corr.append(row)
        for i in range(n):            # keep it symmetric whatever was typed
            for j in range(i + 1, n):
                corr[j][i] = corr[i][j]
        plan.market.corr = corr
        for k, rg in enumerate(plan.market.regimes):
            rg.label = (form.get(f"regime-{k}-label") or rg.label).strip()
            rg.mean_offset = _pct(form, f"regime-{k}-mean_offset", rg.mean_offset)
            rg.vol_mult = _num(form, f"regime-{k}-vol_mult", rg.vol_mult)
            rg.corr_tighten = _pct(form, f"regime-{k}-corr_tighten", rg.corr_tighten)
            rg.trans = [_pct(form, f"regime-{k}-p{j}", rg.trans[j])
                        for j in range(len(plan.market.regimes))]
            # The market model refuses rows that do not sum to one, which would
            # break every results page; rescale here and say so instead.
            total = sum(rg.trans)
            if total <= 0:
                rg.trans = [1.0 if j == k else 0.0 for j in range(len(rg.trans))]
                self._notes.append(f"'{rg.label}' had no transition probabilities; "
                                   "it now stays in itself.")
            elif abs(total - 1.0) > 1e-9:
                rg.trans = [t / total for t in rg.trans]
                self._notes.append(f"'{rg.label}' transition row summed to "
                                   f"{total:.1%}; rescaled to 100%.")
        c = plan.market.crash
        c.enabled = bool(form.get("crash_enabled"))
        c.prob = _pct(form, "crash_prob", c.prob)
        c.depth_min = _pct(form, "crash_min", c.depth_min)
        c.depth_mode = _pct(form, "crash_mode", c.depth_mode)
        c.depth_max = _pct(form, "crash_max", c.depth_max)
        c.duration = max(1, int(_num(form, "crash_duration", c.duration)))
        c.recovery_fraction = _pct(form, "crash_recovery", c.recovery_fraction)
        c.recovery_periods = max(1, int(_num(form, "crash_recovery_years",
                                             c.recovery_periods)))
        inf = plan.market.inflation
        inf.mode = form.get("inflation_mode") or inf.mode
        inf.mean = _pct(form, "inflation_mean", inf.mean)
        inf.sd = _pct(form, "inflation_sd", inf.sd)
        inf.persistence = _num(form, "inflation_phi", inf.persistence)
        inf.corr_equity = _num(form, "inflation_corr", inf.corr_equity)
        plan.market.dist = form.get("dist") or plan.market.dist
        if form.get("fixed_basis") in ("typical", "average"):
            plan.market.fixed_basis = form.get("fixed_basis")
        plan.market.nu = _num(form, "nu", plan.market.nu)
        plan.market.antithetic = bool(form.get("antithetic"))
        plan.market.calibrate = bool(form.get("calibrate"))
        plan.market.start_regime = form.get("start_regime") or plan.market.start_regime
        plan.platform_fee = _pct(form, "platform_fee", plan.platform_fee)
        plan.adviser_fee = _pct(form, "adviser_fee", plan.adviser_fee)

    def _save_tax(self, plan, form):
        lowers, rates = [], []
        for i in range(12):
            key = f"band-{i}-lower"
            if key not in form or form.get(f"delete-band-{i}"):
                continue
            raw = (form.get(key) or "").strip()
            if raw == "" and i > 0:
                continue
            lowers.append(_num(form, key))
            rates.append(_pct(form, f"band-{i}-rate"))
        if lowers:
            order = sorted(range(len(lowers)), key=lambda k: lowers[k])
            lowers = [lowers[k] for k in order]
            rates = [rates[k] for k in order]
            if lowers[0] != 0:
                lowers.insert(0, 0.0)
                rates.insert(0, 0.0)
            from retplan.tax import Schedule
            plan.tax.ordinary = Schedule("Ordinary income", lowers, rates)
        plan.tax.surtax_rate = _pct(form, "surtax_rate", plan.tax.surtax_rate)
        thr = _num(form, "surtax_threshold", 0)
        plan.tax.surtax_threshold = thr if thr > 0 else 1e18
        plan.tax.cg_inclusion = _pct(form, "cg_inclusion", plan.tax.cg_inclusion)
        plan.tax.index_bands = bool(form.get("index_bands"))

    def _save_policy(self, plan, form):
        p = plan.policy
        p.method = form.get("method") or p.method
        p.pct = _pct(form, "pct", p.pct)
        p.vpw_rate = _pct(form, "vpw_rate", p.vpw_rate)
        p.guard_up = _pct(form, "guard_up", p.guard_up)
        p.guard_down = _pct(form, "guard_down", p.guard_down)
        p.guard_cut = _pct(form, "guard_cut", p.guard_cut)
        p.guard_raise = _pct(form, "guard_raise", p.guard_raise)
        p.guard_final_years = int(_num(form, "guard_final_years", p.guard_final_years))
        p.inflation_skip = bool(form.get("inflation_skip"))
        p.legacy_target = _num(form, "legacy_target", p.legacy_target)
        p.confidence = _pct(form, "confidence", p.confidence)
        p.discount_rate = _pct(form, "discount_rate", p.discount_rate)
        p.cash_buffer_years = _num(form, "cash_buffer_years", p.cash_buffer_years)
