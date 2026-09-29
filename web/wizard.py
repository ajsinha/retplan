"""The quick-start wizard: six short steps in, a complete plan out.

The full editor asks for everything a careful plan needs - wrappers, tax bands,
regimes, glide paths. Most people start with far less: their age, what they earn,
what they have saved and what they spend. :func:`build_plan` turns those few
answers into a complete :class:`~retplan.plan.Plan`, borrowing every assumption
it was not told (market model, tax wrappers, spending curve) from the sample
household, so the first answer arrives in minutes and every default can be
refined later in the editor.

The answers are a flat dict of strings, exactly as the form posts them, so the
wizard can keep a draft in the session between steps.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from retplan.plan import (JUST_BEFORE, ExpenseRow, IncomeRow, Ledger, Loan, Person, Plan,
                          Wrapper)
from retplan.samples import sample_plan, sample_wrappers
from retplan.tax import Schedule

# --------------------------------------------------------------------------- #
# accounts by type: each is taxed differently, which changes how long money lasts
# --------------------------------------------------------------------------- #
LIMITS_YEAR = 2026
# The IRS Uniform Lifetime Table (2022 onwards): the divisor for each age.
US_RMD = [(73, 26.5), (74, 25.5), (75, 24.6), (76, 23.7), (77, 22.9), (78, 22.0),
          (79, 21.1), (80, 20.2), (81, 19.4), (82, 18.5), (83, 17.7), (84, 16.8),
          (85, 16.0), (86, 15.2), (87, 14.4), (88, 13.7), (89, 12.9), (90, 12.2),
          (91, 11.5), (92, 10.8), (93, 10.1), (94, 9.5), (95, 8.9), (96, 8.4),
          (97, 7.8), (98, 7.3), (99, 6.8), (100, 6.4), (101, 6.0), (102, 5.6),
          (103, 5.2), (104, 4.9), (105, 4.6), (106, 4.3), (107, 4.1), (108, 3.9),
          (109, 3.7), (110, 3.5)]

# key, label, icon, what it is, how it is taxed, how saving into it is asked
# ("pct" of pay with an employer match, or an "amount" a year), per person or
# one for the household, and its draw and pay-in order.
ACCOUNT_TYPES = [
    dict(key="k401", label="401(k) / 403(b)", icon="building", group="Through work",
         blurb="A traditional workplace plan (457 and TSP too).",
         tax="Tax deducted now; taxed when you take it out.", save="pct", per_person=True,
         limit=f"{LIMITS_YEAR} limit 24,500 each, plus 8,000 from age 50.",
         draw=2, pay=1),
    dict(key="roth401k", label="Roth 401(k)", icon="building", group="Through work",
         blurb="The Roth side of a workplace plan.",
         tax="Paid in after tax; tax-free in retirement.", save="pct", per_person=True,
         limit="Shares the 401(k) limit.", draw=3, pay=2),
    dict(key="ira", label="Traditional IRA", icon="piggy-bank", group="On your own",
         blurb="Including rollovers from old jobs.",
         tax="Taxed when you take it out; withdrawals required from 73.", save="amount",
         per_person=True, limit=f"{LIMITS_YEAR} limit 7,500 each, plus 1,100 from age 50.",
         draw=2, pay=4),
    dict(key="roth_ira", label="Roth IRA", icon="shield-check", group="On your own",
         blurb="Including backdoor Roth contributions.",
         tax="Paid in after tax; tax-free, no required withdrawals.", save="amount",
         per_person=True, limit="Shares the IRA limit.", draw=3, pay=5),
    dict(key="hsa", label="HSA", icon="heart", group="On your own",
         blurb="A health savings account, invested.",
         tax="Deductible now; tax-free when spent on health.", save="amount",
         per_person=False, limit=f"{LIMITS_YEAR} limit 4,400 (8,750 family), plus 1,000 from 55.",
         draw=4, pay=3),
    dict(key="brokerage", label="Brokerage", icon="graph-up-arrow", group="On your own",
         blurb="An ordinary investment account.",
         tax="Dividends taxed yearly; gains taxed when you sell.", save="amount",
         per_person=False, limit="No limit.", draw=1, pay=6),
    dict(key="cash", label="Savings and CDs", icon="cash-stack", group="On your own",
         blurb="Bank savings, money market, CDs.",
         tax="Interest taxed every year.", save="amount", per_person=False,
         limit="", draw=5, pay=7),
    dict(key="pension_pot", label="Pension pot", icon="bank", group="Outside the US",
         blurb="A workplace or personal pension: SIPP, RRSP, super…",
         tax="Taxed when you take it out.", save="pct", per_person=True, limit="",
         draw=2, pay=1),
    dict(key="isa", label="Tax-free savings", icon="umbrella", group="Outside the US",
         blurb="An ISA, TFSA and the like.",
         tax="Paid in after tax; never taxed again.", save="amount", per_person=True,
         limit="", draw=3, pay=5),
]
ACCOUNT_BY_KEY = {t["key"]: t for t in ACCOUNT_TYPES}


def account_keys(t: dict) -> list[str]:
    """The answer keys one account type uses."""
    k = t["key"]
    keys = [k, f"{k}_save"]
    if t["save"] == "pct":
        keys.append(f"{k}_match")
    if t["per_person"]:
        keys += [f"{x}_p2" for x in keys]
    return keys


def account_wrappers(a: dict, two: bool) -> dict:
    """One tax wrapper per account type, by the rules of its kind."""
    born = 2026 - _f(a, "age", 45)
    rmd_age = 75.0 if born >= 1960 else 73.0            # SECURE 2.0
    generic = sample_wrappers()
    return {
        "k401": Wrapper("401(k) / 403(b)", contribution_deductible=1.0,
                        growth_taxed_annually=False, growth_taxable_fraction=0.0,
                        withdrawal_taxable_fraction=1.0, realises_capital_gains=False,
                        cap_type="absolute", cap_value=24500, catch_up_age=50,
                        catch_up_amount=8000, early_age=59.5, early_penalty=0.10,
                        mrd_age=rmd_age, mrd_divisors=list(US_RMD)),
        "roth401k": Wrapper("Roth 401(k)", contribution_deductible=0.0,
                            growth_taxed_annually=False, growth_taxable_fraction=0.0,
                            withdrawal_taxable_fraction=0.0, realises_capital_gains=False,
                            cap_type="absolute", cap_value=24500, catch_up_age=50,
                            catch_up_amount=8000, early_age=59.5, early_penalty=0.10),
        "ira": Wrapper("Traditional IRA", contribution_deductible=1.0,
                       growth_taxed_annually=False, growth_taxable_fraction=0.0,
                       withdrawal_taxable_fraction=1.0, realises_capital_gains=False,
                       cap_type="absolute", cap_value=7500, catch_up_age=50,
                       catch_up_amount=1100, early_age=59.5, early_penalty=0.10,
                       mrd_age=rmd_age, mrd_divisors=list(US_RMD)),
        # Roth IRA contributions can come out at any time, so no penalty is applied.
        "roth_ira": Wrapper("Roth IRA", contribution_deductible=0.0,
                            growth_taxed_annually=False, growth_taxable_fraction=0.0,
                            withdrawal_taxable_fraction=0.0, realises_capital_gains=False,
                            cap_type="absolute", cap_value=7500, catch_up_age=50,
                            catch_up_amount=1100),
        # Assumes the money is spent on health, where it is never taxed.
        "hsa": Wrapper("HSA", contribution_deductible=1.0, growth_taxed_annually=False,
                       growth_taxable_fraction=0.0, withdrawal_taxable_fraction=0.0,
                       realises_capital_gains=False, cap_type="absolute",
                       cap_value=8750 if two else 4400, catch_up_age=55, catch_up_amount=1000),
        "brokerage": Wrapper("Brokerage", contribution_deductible=0.0,
                             growth_taxed_annually=True, growth_taxable_fraction=1.0,
                             withdrawal_taxable_fraction=0.0, realises_capital_gains=True),
        "cash": generic[3],
        "pension_pot": generic[1],
        "isa": generic[2],
        "property": generic[4],
    }


# US federal income tax, 2026: brackets over the standard deduction, joint and single.
US_FEDERAL = {
    "joint": (32200, [24800, 100800, 211400, 403550, 512450, 768700]),
    "single": (16100, [12400, 50400, 105700, 201775, 256225, 640600]),
}
US_RATES = [0.10, 0.12, 0.22, 0.24, 0.32, 0.35, 0.37]


def us_federal(two: bool) -> Schedule:
    deduction, tops = US_FEDERAL["joint" if two else "single"]
    return Schedule("US federal income tax", [0.0, deduction] + [deduction + t for t in tops],
                    [0.0] + US_RATES)

STEPS = [
    ("you", "You", "people"),
    ("income", "Income", "arrow-down-circle"),
    ("savings", "Savings", "wallet2"),
    ("spending", "Spending", "arrow-up-circle"),
    ("assumptions", "Assumptions", "sliders"),
    ("review", "Review", "check2-circle"),
]

RISK = {
    "conservative": dict(label="Conservative", blurb="About 35% shares. Smaller swings, lower growth.",
                         mix={"equity": 0.35, "government": 0.35, "corporate": 0.20, "cash": 0.10}),
    "balanced": dict(label="Balanced", blurb="About 60% shares. The classic middle road.",
                     mix={"equity": 0.60, "government": 0.25, "corporate": 0.10, "cash": 0.05}),
    "growth": dict(label="Growth", blurb="About 85% shares. Bigger swings, more growth.",
                   mix={"equity": 0.85, "government": 0.10, "corporate": 0.05}),
}

TAX = {
    "us": dict(label="US federal",
               blurb="2026 brackets and standard deduction, joint or single. Social Security "
                     "85% taxable; long-term gains at about two-thirds of the income rate. "
                     "No state tax."),
    "sample": dict(label="Progressive bands (example)",
                   blurb="0% to 12,570, then 20%, 40%, 60% taper, 45%. Edit later."),
    "flat": dict(label="One flat rate", blurb="A single rate on all taxable income."),
    "none": dict(label="Ignore tax", blurb="Everything before tax - useful for a quick look."),
}

DEFAULTS = {
    "name": "My plan", "age": "45", "retire_age": "65", "plan_to": "95",
    "partner": "", "p2_age": "43", "p2_retire_age": "65", "p2_plan_to": "95",
    "salary": "60000", "salary_growth": "1", "p2_salary": "0",
    "pension": "10000", "pension_age": "67", "p2_pension": "0", "p2_pension_age": "67",
    "other_income": "0", "other_income_end": "",
    "has_k401": "1", "k401": "150000", "k401_save": "8", "k401_match": "4",
    "has_roth_ira": "1", "roth_ira": "20000", "roth_ira_save": "0",
    "has_brokerage": "1", "brokerage": "50000", "brokerage_save": "5000",
    "has_cash": "1", "cash": "15000", "cash_save": "0",
    "spend": "40000", "retire_spend_pct": "80", "essential_pct": "60",
    "mortgage": "0", "mortgage_rate": "4.5", "mortgage_years": "20",
    "risk": "balanced", "tax": "us", "flat_rate": "20", "inflation": "2.5",
    "legacy": "0",
}
for _t in ACCOUNT_TYPES:
    DEFAULTS.setdefault(f"has_{_t['key']}", "")
    for _k in account_keys(_t):
        DEFAULTS.setdefault(_k, "0")


def _f(a: dict, key: str, default: float = 0.0) -> float:
    raw = str(a.get(key, "") if a.get(key) is not None else "").strip()
    raw = raw.replace(",", "").replace("%", "").replace("$", "")
    if raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def validate(step: str, a: dict) -> list[str]:
    """Plain-language problems with one step's answers (empty when fine)."""
    errs = []
    if step == "you":
        age, ret, end = _f(a, "age"), _f(a, "retire_age"), _f(a, "plan_to")
        if not 16 <= age <= 100:
            errs.append("Your age should be between 16 and 100.")
        if ret < age and age:
            errs.append("Retirement age can't be before your current age "
                        "(if you've already retired, use your current age).")
        if end <= max(age, ret):
            errs.append("Plan-to age must be after retirement.")
        if a.get("partner"):
            p2, r2, e2 = _f(a, "p2_age"), _f(a, "p2_retire_age"), _f(a, "p2_plan_to")
            if not 16 <= p2 <= 100:
                errs.append("Your partner's age should be between 16 and 100.")
            if r2 < p2:
                errs.append("Your partner's retirement age can't be before their current age.")
            if e2 <= max(p2, r2):
                errs.append("Your partner's plan-to age must be after their retirement.")
    elif step == "savings":
        keys = [k for t in ACCOUNT_TYPES for k in account_keys(t)]
        if any(_f(a, k) < 0 for k in keys):
            errs.append("Balances and amounts can't be negative.")
        for t in ACCOUNT_TYPES:
            if t["save"] == "pct" and any(_f(a, f"{t['key']}_save{s}") > 100
                                          for s in ("", "_p2")):
                errs.append(f"A {t['label']} saving rate is a share of pay, at most 100%.")
    elif step == "spending":
        if _f(a, "spend") <= 0:
            errs.append("Enter what you spend in a year - even a rough figure.")
        if not 0 <= _f(a, "essential_pct") <= 100:
            errs.append("The essential share is a percentage between 0 and 100.")
    elif step == "assumptions":
        if a.get("risk") not in RISK:
            errs.append("Choose an investment mix.")
        if not -2 <= _f(a, "inflation") <= 15:
            errs.append("Inflation should be between -2% and 15%.")
    return errs


def _weights(plan: Plan, mix: dict) -> list[float]:
    """Map a named mix onto the plan's asset classes by their labels."""
    labels = [x.label.lower() for x in plan.market.assets]

    def find(*words):
        for i, lab in enumerate(labels):
            if any(w in lab for w in words):
                return i
        return None

    slots = {"equity": find("equity", "stock", "share"),
             "government": find("government", "gilt", "treasur"),
             "corporate": find("corporate", "credit"),
             "cash": find("cash"), "property": find("property", "real estate"),
             "alternatives": find("alternative", "commodit")}
    w = [0.0] * len(labels)
    for k, share in mix.items():
        i = slots.get(k)
        if i is None:                       # fold a missing class into equity
            i = slots.get("equity") or 0
        w[i] += share
    total = sum(w) or 1.0
    return [x / total for x in w]


def build_plan(a: dict) -> Plan:
    """A complete plan from the wizard's answers."""
    plan = sample_plan()
    plan.label = (a.get("name") or "My plan").strip() or "My plan"
    two = bool(a.get("partner"))
    age, ret, end = _f(a, "age", 45), _f(a, "retire_age", 65), _f(a, "plan_to", 95)
    persons = [Person("You", age, ret, end)]
    if two:
        persons.append(Person("Partner", _f(a, "p2_age", 43), _f(a, "p2_retire_age", 65),
                              _f(a, "p2_plan_to", 95)))
    plan.persons = persons
    plan.horizon = int(max(1, min(80, max(p.death_age - p.age for p in persons))))

    # -- income
    inc = []
    growth = _f(a, "salary_growth", 1.0) / 100
    if _f(a, "salary") > 0:
        inc.append(IncomeRow("Salary", 0, "employment", _f(a, "salary"), "real",
                             growth, False, age, ret, 1.0, 0.0, 1.0))
    if two and _f(a, "p2_salary") > 0:
        inc.append(IncomeRow("Partner's salary", 1, "employment", _f(a, "p2_salary"),
                             "real", growth, False, persons[1].age,
                             persons[1].retire_age, 1.0, 0.0, 1.0))
    if _f(a, "pension") > 0:
        inc.append(IncomeRow("Public / state pension", 0, "state_pension",
                             _f(a, "pension"), "real", 0.0, False,
                             _f(a, "pension_age", 67), 200, 1.0, 0.5 if two else 0.0, 1.0))
    if two and _f(a, "p2_pension") > 0:
        inc.append(IncomeRow("Partner's public pension", 1, "state_pension",
                             _f(a, "p2_pension"), "real", 0.0, False,
                             _f(a, "p2_pension_age", 67), 200, 1.0, 0.5, 1.0))
    if _f(a, "other_income") > 0:
        stop = _f(a, "other_income_end", 200) or 200
        inc.append(IncomeRow("Other income", 0, "other_taxable", _f(a, "other_income"),
                             "real", 0.0, False, age, stop, 1.0, 1.0, 1.0))
    plan.income = inc

    # -- spending: today's level until retirement, then a share of it
    spend = _f(a, "spend", 40000)
    ess = max(0.0, min(1.0, _f(a, "essential_pct", 60) / 100))
    later = spend * max(0.1, _f(a, "retire_spend_pct", 80) / 100)
    exp = []
    if ret > age:
        exp += [ExpenseRow("Essentials (working years)", spend * ess, "real", True, 0.0,
                           False, age, ret - JUST_BEFORE, -1, 0, 1.0),
                ExpenseRow("Discretionary (working years)", spend * (1 - ess), "real",
                           False, 0.0, False, age, ret - JUST_BEFORE, -1, 0, 1.0)]
    exp += [ExpenseRow("Essentials (retirement)", later * ess, "real", True, 0.0,
                       False, ret, 200, -1, 0, 1.0),
            ExpenseRow("Discretionary (retirement)", later * (1 - ess), "real", False,
                       0.0, True, ret, 200, -1, 0, 1.0)]
    plan.expenses = [e for e in exp if e.amount > 0]

    # -- debt
    plan.loans = []
    if _f(a, "mortgage") > 0:
        plan.loans = [Loan("Mortgage", _f(a, "mortgage"), _f(a, "mortgage_rate", 4.5) / 100,
                           int(_f(a, "mortgage_years", 20)), "amortising", 0.0, 0)]

    # -- accounts: one per type and owner, each in its own tax wrapper
    risk = RISK.get(a.get("risk"), RISK["balanced"])
    w = _weights(plan, risk["mix"])
    cash_w = _weights(plan, {"cash": 1.0})
    glide = _weights(plan, RISK["conservative"]["mix"])
    wrappers = account_wrappers(a, two)
    order = list(wrappers)
    plan.wrappers = [wrappers[k] for k in order]
    ledgers = []
    for t in ACCOUNT_TYPES:
        k = t["key"]
        owners = [("", 0, "")] + ([("_p2", 1, "Partner's ")] if two and t["per_person"] else [])
        for sfx, owner, who in owners:
            bal, save = _f(a, f"{k}{sfx}"), _f(a, f"{k}_save{sfx}")
            if bal <= 0 and save <= 0:
                continue
            is_cash = k == "cash"
            pct = t["save"] == "pct"
            match = _f(a, f"{k}_match{sfx}") / 100 if pct else 0.0
            ledgers.append(Ledger(
                f"{who}{t['label']}" if who else (f"Your {t['label']}" if two and t["per_person"]
                                                  else t["label"]),
                order.index(k), owner, bal, bal if k in ("brokerage", "cash") else 0.0,
                cash_w if is_cash else w, [] if is_cash else glide,
                200 if is_cash else max(age, ret - 10), 200 if is_cash else ret + 5,
                t["draw"], t["pay"], 0.0 if pct else save, save / 100 if pct else 0.0,
                1.0 if match else 0.0, match, "annual"))
    if not any(lg.wrapper == order.index("brokerage") for lg in ledgers):
        # unspent income has to land somewhere
        ledgers.append(Ledger("Brokerage (unspent income)", order.index("brokerage"), 0, 0.0,
                              0.0, w, glide, max(age, ret - 10), ret + 5, 1, 6, 0.0, 0.0,
                              0.0, 0.0, "annual"))
    plan.ledgers = ledgers
    plan.policy.sweep_ledger = next(i for i, lg in enumerate(ledgers)
                                    if lg.wrapper == order.index("brokerage"))
    plan.policy.legacy_target = max(0.0, _f(a, "legacy", 0))

    # -- tax
    choice = a.get("tax") or "us"
    if choice == "us":
        plan.tax.ordinary = us_federal(two)
        plan.tax.cg_inclusion = 0.65
        for row in plan.income:
            if row.category == "state_pension":
                row.taxable_fraction = 0.85
    elif choice == "flat":
        plan.tax.ordinary = Schedule("Ordinary income", [0.0],
                                     [max(0.0, min(1.0, _f(a, "flat_rate", 20) / 100))])
    elif choice == "none":
        plan.tax.ordinary = Schedule("Ordinary income", [0.0], [0.0])
    plan.market.inflation.mean = _f(a, "inflation", 2.5) / 100
    return plan


def summary(a: dict) -> list[tuple[str, list[tuple[str, str]]]]:
    """The review step, grouped - what the plan will contain, in words."""
    def m(k):
        return f"{_f(a, k):,.0f}"
    two = bool(a.get("partner"))
    you = [("Plan name", a.get("name") or "My plan"),
           ("You", f"age {m('age')}, retire at {m('retire_age')}, plan to {m('plan_to')}")]
    if two:
        you.append(("Partner", f"age {m('p2_age')}, retire at {m('p2_retire_age')}, "
                               f"plan to {m('p2_plan_to')}"))
    income = [("Salary", f"{m('salary')} a year, growing {m('salary_growth')}% above inflation")]
    if two:
        income.append(("Partner's salary", f"{m('p2_salary')} a year"))
    if _f(a, "pension"):
        income.append(("Public pension", f"{m('pension')} a year from {m('pension_age')}"))
    else:
        income.append(("Public pension", "none"))
    if _f(a, "other_income"):
        income.append(("Other income", f"{m('other_income')} a year"))
    sav = []
    for t in ACCOUNT_TYPES:
        k = t["key"]
        for sfx, who in [("", "")] + ([("_p2", "partner's ")] if two and t["per_person"] else []):
            bal, save = _f(a, f"{k}{sfx}"), _f(a, f"{k}_save{sfx}")
            if bal <= 0 and save <= 0:
                continue
            text = f"{bal:,.0f}"
            if save and t["save"] == "pct":
                text += f", saving {save:g}% of pay"
                if _f(a, f"{k}_match{sfx}"):
                    text += f" (+ match to {_f(a, f'{k}_match{sfx}'):g}%)"
            elif save:
                text += f", adding {save:,.0f} a year"
            sav.append(((who + t["label"]).capitalize() if who else t["label"], text))
    if not sav:
        sav = [("Savings", "none yet")]
    sp = [("Spending now", f"{m('spend')} a year, {a.get('essential_pct') or 0}% essential"),
          ("In retirement", f"{a.get('retire_spend_pct') or 0}% of today's level")]
    if _f(a, "mortgage"):
        sp.append(("Mortgage", f"{m('mortgage')} at {a.get('mortgage_rate')}% over "
                               f"{a.get('mortgage_years')} years"))
    asm = [("Investment mix", RISK.get(a.get("risk"), RISK["balanced"])["label"]),
           ("Tax", TAX.get(a.get("tax"), TAX["sample"])["label"]
            + (f" ({a.get('flat_rate')}%)" if a.get("tax") == "flat" else "")),
           ("Inflation", f"{a.get('inflation')}% a year")]
    return [("You", you), ("Income", income), ("Savings", sav), ("Spending", sp),
            ("Assumptions", asm)]
