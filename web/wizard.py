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

from retplan.plan import ExpenseRow, IncomeRow, Ledger, Loan, Person, Plan
from retplan.samples import sample_plan
from retplan.tax import Schedule

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
    "taxable": "50000", "deferred": "150000", "taxfree": "20000", "cash": "15000",
    "save_pct": "8", "employer_pct": "4", "save_amount": "5000",
    "spend": "40000", "retire_spend_pct": "80", "essential_pct": "60",
    "mortgage": "0", "mortgage_rate": "4.5", "mortgage_years": "20",
    "risk": "balanced", "tax": "sample", "flat_rate": "20", "inflation": "2.5",
    "legacy": "0",
}


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
        if any(_f(a, k) < 0 for k in ("taxable", "deferred", "taxfree", "cash")):
            errs.append("Balances can't be negative.")
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
                           False, age, ret, -1, 0, 1.0),
                ExpenseRow("Discretionary (working years)", spend * (1 - ess), "real",
                           False, 0.0, False, age, ret, -1, 0, 1.0)]
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

    # -- accounts, onto the sample's wrappers:
    #    0 taxable, 1 pension (EET), 2 tax-free (TEE), 3 cash
    risk = RISK.get(a.get("risk"), RISK["balanced"])
    w = _weights(plan, risk["mix"])
    cash_w = _weights(plan, {"cash": 1.0})
    glide = _weights(plan, RISK["conservative"]["mix"])
    save_pct = _f(a, "save_pct", 0) / 100
    emp = _f(a, "employer_pct", 0) / 100
    plan.ledgers = [
        Ledger("Workplace / retirement account", 1, 0, _f(a, "deferred"), 0.0, w, glide,
               max(age, ret - 10), ret + 5, 3, 1, 0.0, save_pct, 1.0 if emp else 0.0,
               emp, "annual"),
        Ledger("Tax-free account", 2, 0, _f(a, "taxfree"), _f(a, "taxfree"), w, glide,
               max(age, ret - 10), ret + 5, 2, 2, 0.0, 0.0, 0.0, 0.0, "annual"),
        Ledger("Taxable investments", 0, 0, _f(a, "taxable"), _f(a, "taxable"), w, glide,
               max(age, ret - 10), ret + 5, 1, 3, _f(a, "save_amount"), 0.0, 0.0, 0.0,
               "annual"),
        Ledger("Cash savings", 3, 0, _f(a, "cash"), _f(a, "cash"), cash_w, [], 200, 200,
               4, 4, 0.0, 0.0, 0.0, 0.0, "annual"),
    ]
    plan.policy.sweep_ledger = 2
    plan.policy.legacy_target = max(0.0, _f(a, "legacy", 0))

    # -- tax
    choice = a.get("tax") or "sample"
    if choice == "flat":
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
    sav = [("Retirement account", m("deferred")), ("Tax-free account", m("taxfree")),
           ("Taxable investments", m("taxable")), ("Cash", m("cash")),
           ("Saving", f"{a.get('save_pct') or 0}% of pay (+{a.get('employer_pct') or 0}% "
                      f"employer) and {m('save_amount')} a year")]
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
