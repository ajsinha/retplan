"""The plan editor as a conversation: cards, and a dialog a step at a time.

A wide table with a dozen columns is the fastest way to edit twenty rows and the
worst way to add the first one. So each list in the plan - income, spending,
debt, accounts, health and care, conversions - is shown as cards that read as
sentences, and adding or editing one opens a dialog that asks:

  1. what kind of thing it is (a salary, a public pension, a mortgage…), which
     fills in sensible answers from the household;
  2. a few plain questions per step, each with a hint;
  3. "more options" last, for the columns most people never need.

This module is the single definition of that conversation: the kinds and their
presets, the steps and their questions, and each card's summary. The table view
still exists for bulk edits, and both are validated by the same field
specifications in routes/plan_routes.py.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from dataclasses import asdict

from retplan.plan import CareRisk, Conversion, ExpenseRow, IncomeRow, Ledger, Loan

LIFE = 200.0            # "for life": the engine's end age for streams that never stop


def _q(name, question, hint="", widget=None, required=False, **kw):
    return dict(name=name, question=question, hint=hint, widget=widget, required=required, **kw)


def _people(plan):
    return [(i, p.label) for i, p in enumerate(plan.persons)]


def _p0(plan):
    return plan.persons[0]


# --------------------------------------------------------------------------- #
# kinds and their presets
# --------------------------------------------------------------------------- #
def _income_kinds(plan):
    p = _p0(plan)
    couple = len(plan.persons) > 1
    return [
        dict(key="salary", label="A salary", icon="briefcase",
             blurb="Pay from a job, until you retire.",
             preset=dict(label="Salary", category="employment", growth=0.01,
                         start_age=p.age, end_age=p.retire_age, survivor_fraction=0.0)),
        dict(key="public", label="A public pension", icon="bank",
             blurb="Social Security, State Pension, CPP…", preset=dict(
                 label="Public pension", category="state_pension", growth=0.0, start_age=67.0,
                 end_age=LIFE, survivor_fraction=0.5 if couple else 0.0)),
        dict(key="workplace", label="A workplace pension", icon="building",
             blurb="A defined-benefit pension paid for life.", preset=dict(
                 label="Workplace pension", category="db_pension", growth=0.0,
                 start_age=p.retire_age, end_age=LIFE, survivor_fraction=0.5 if couple else 0.0)),
        dict(key="rental", label="Rent", icon="house-door",
             blurb="Rent from a property, after its costs.", preset=dict(
                 label="Rental income", category="rental", growth=0.0, start_age=p.age,
                 end_age=LIFE, survivor_fraction=1.0)),
        dict(key="parttime", label="Part-time work", icon="clock",
             blurb="Some earnings in the first years of retirement.", preset=dict(
                 label="Part-time work", category="self_employment", growth=0.0,
                 start_age=p.retire_age, end_age=p.retire_age + 5)),
        dict(key="annuity", label="An annuity", icon="shield-check",
             blurb="A guaranteed income you have bought.", preset=dict(
                 label="Annuity", category="annuity", growth=0.0, start_age=p.retire_age,
                 end_age=LIFE, survivor_fraction=0.5 if couple else 0.0)),
        dict(key="oneoff", label="A one-off sum", icon="gift",
             blurb="An inheritance, a sale, a lump sum.", preset=dict(
                 label="Inheritance", category="one_off", growth=0.0, start_age=p.age + 10,
                 end_age=p.age + 11, taxable_fraction=0.0)),
        dict(key="other", label="Something else", icon="three-dots",
             blurb="Any other money coming in.", preset=dict(
                 label="Other income", category="other_taxable", start_age=p.age, end_age=LIFE)),
    ]


def _expense_kinds(plan):
    p = _p0(plan)
    return [
        dict(key="essentials", label="Everyday essentials", icon="basket",
             blurb="Food, bills, transport - what you could not cut.", preset=dict(
                 label="Everyday essentials", essential=True, start_age=p.age, end_age=LIFE)),
        dict(key="housing", label="Housing", icon="house",
             blurb="Rent, property tax, upkeep, insurance.", preset=dict(
                 label="Housing", essential=True, start_age=p.age, end_age=LIFE)),
        dict(key="lifestyle", label="Travel and fun", icon="globe",
             blurb="What you would like to do - and could trim.", preset=dict(
                 label="Travel and leisure", essential=False, smile=True, start_age=p.age,
                 end_age=LIFE)),
        dict(key="health", label="Health", icon="heart",
             blurb="Insurance and costs that rise faster than prices.", preset=dict(
                 label="Health costs", essential=True, infl_delta=0.02, start_age=p.age,
                 end_age=LIFE)),
        dict(key="recurring", label="Every few years", icon="arrow-repeat",
             blurb="A new car, a new roof, a big trip.", preset=dict(
                 label="Car replacement", essential=False, recur_years=8, start_age=p.age + 1,
                 end_age=85.0)),
        dict(key="temporary", label="For some years", icon="mortarboard",
             blurb="University fees, supporting a parent.", preset=dict(
                 label="University support", essential=False, start_age=p.age + 5,
                 end_age=p.age + 9)),
        dict(key="oneoff", label="Once", icon="calendar-event",
             blurb="A wedding, a gift, a move.", preset=dict(
                 label="Wedding", essential=False, start_age=p.age + 3, end_age=p.age + 4)),
        dict(key="other", label="Something else", icon="three-dots",
             blurb="Anything else you spend.", preset=dict(
                 label="Other spending", essential=False, start_age=p.age, end_age=LIFE)),
    ]


def _debt_kinds(plan):
    return [
        dict(key="mortgage", label="A mortgage", icon="house", blurb="Repaid over its term.",
             preset=dict(label="Mortgage", rate=0.045, term_years=20, kind="amortising")),
        dict(key="car", label="A car loan", icon="truck", blurb="A shorter loan.",
             preset=dict(label="Car loan", rate=0.07, term_years=5, kind="amortising")),
        dict(key="student", label="A student loan", icon="mortarboard", blurb="Education debt.",
             preset=dict(label="Student loan", rate=0.05, term_years=10, kind="amortising")),
        dict(key="interest", label="Interest-only", icon="percent",
             blurb="Only interest is paid; the balance at the end.",
             preset=dict(label="Interest-only loan", rate=0.05, term_years=10,
                         kind="interest_only")),
        dict(key="other", label="Something else", icon="three-dots", blurb="Any other debt.",
             preset=dict(label="Loan", rate=0.06, term_years=5, kind="amortising")),
    ]


def _account_kinds(plan):
    out = []
    for i, w in enumerate(plan.wrappers):
        how = ("taxed when you take it out" if w.withdrawal_taxable_fraction >= 0.99 else
               "never taxed again" if w.withdrawal_taxable_fraction <= 0.01
               and not w.realises_capital_gains else
               "gains taxed when you sell" if w.realises_capital_gains else "taxed as it grows")
        out.append(dict(key=f"w{i}", label=w.label, icon=_wrapper_icon(i),
                        blurb=how.capitalize() + ("." if w.liquid else "; not drawn on."),
                        preset=dict(label=w.label, wrapper=i, withdraw_priority=len(plan.ledgers) + 1,
                                    contribute_priority=len(plan.ledgers) + 1)))
    return out


def _wrapper_icon(i: int) -> str:
    icons = ["wallet2", "piggy-bank", "shield-check", "cash-stack", "building", "bank"]
    return icons[i % len(icons)]


KINDS = {"income": _income_kinds, "expenses": _expense_kinds, "debt": _debt_kinds,
         "accounts": _account_kinds}

NOUNS = {"income": "income", "expenses": "spending", "debt": "debt", "accounts": "account",
         "care": "care risk", "conversions": "conversion"}

MIXES = [("keep", "Keep as it is", "No change to how it is invested."),
         ("cash", "Cash", "No shares or bonds."),
         ("conservative", "Conservative", "About 35% shares."),
         ("balanced", "Balanced", "About 60% shares."),
         ("growth", "Growth", "About 85% shares.")]


def is_once(section: str, row: dict) -> bool:
    """A one-off: asked "at what age", and stored as a one-year stream."""
    if section == "income":
        return row.get("category") == "one_off"
    if section == "expenses":
        return row.get("kind_key") == "oneoff" or (
            not row.get("recur_years") and 0 < row.get("end_age", 0) - row.get("start_age", 0) <= 1)
    return False


# --------------------------------------------------------------------------- #
# the conversation, step by step
# --------------------------------------------------------------------------- #
def steps(section: str, plan, row: dict) -> list[dict]:
    people = _people(plan)
    two = len(people) > 1
    if section == "income":
        once = is_once(section, row)
        return [
            dict(title="What it is", fields=[
                _q("label", "What do you call it?", "Just a name you will recognise.", "text", True),
                *([_q("owner", "Whose is it?", "", "person")] if two else []),
                _q("amount", "How much, once?" if once else "How much a year?",
                   "Before tax, in today's money." if not once else "In today's money.",
                   "money", True)]),
            dict(title="When", fields=(
                [_q("start_age", "At what age does it arrive?", "Your age at the time (or the owner's).",
                    "age", True)] if once else
                [_q("start_age", "From what age?", "The owner's age when it starts.", "age", True),
                 _q("end_age", "Until what age?", "", "age_or_life")])),
            dict(title="More options", optional=True, fields=[
                _q("category", "What sort of income is it?",
                   "It decides the icon and how the tools treat it - a public pension, say.",
                   "select", options=[(c, CATEGORY_WORDS[c]) for c in CATEGORY_WORDS]),
                _q("growth", "Does it grow faster than prices?",
                   "A pay rise above inflation, say 1%. Leave 0 if it keeps pace.", "pct"),
                _q("taxable_fraction", "How much of it is taxable?",
                   "100% for most income; 0% if tax-free; 75% if a quarter is tax-free.", "pct"),
                *([_q("survivor_fraction", "If its owner dies, how much carries on?",
                      "Often 50% for a pension, 100% for rent, 0% for pay.", "pct")] if two else []),
                _q("basis", "Is the amount in today's money?",
                   "“Yes” keeps pace with inflation; “no” is a fixed amount of future money.",
                   "basis"),
                _q("probability", "How likely is it?", "100% if certain. 50% counts half of it.",
                   "pct")]),
        ]
    if section == "expenses":
        once = is_once(section, row)
        recurring = row.get("recur_years", 0) > 1
        return [
            dict(title="What it is", fields=[
                _q("label", "What is it for?", "", "text", True),
                _q("amount", "How much, each time?" if (once or recurring) else "How much a year?",
                   "In today's money.", "money", True),
                _q("essential", "Could you cut it in a bad year?",
                   "Essentials are paid first, whatever the markets do.", "essential")]),
            dict(title="When", fields=[
                _q("start_age", "From what age?" if not once else "At what age?",
                   "Your age (the first person's).", "age", True),
                *([] if once else [_q("end_age", "Until what age?", "", "age_or_life")]),
                *([_q("recur_years", "Every how many years?", "", "int")] if recurring else [])]),
            dict(title="More options", optional=True, fields=[
                _q("infl_delta", "Does it rise faster than prices?",
                   "Health and education often run 1-3% a year above inflation.", "pct"),
                _q("smile", "Should it ease off with age?",
                   "Spending on travel and fun tends to fall in your late seventies and eighties.",
                   "yesno"),
                _q("probability", "How likely is it?", "100% if certain.", "pct")]),
        ]
    if section == "debt":
        return [
            dict(title="The loan", fields=[
                _q("label", "What do you call it?", "", "text", True),
                _q("balance", "How much is owed today?", "", "money", True),
                _q("rate", "At what interest rate?", "The yearly rate.", "pct", True),
                _q("term_years", "How many years are left?", "", "int", True)]),
            dict(title="More options", optional=True, fields=[
                _q("kind", "How is it repaid?", "", "select", options=[
                    ("amortising", "Capital and interest, evenly"),
                    ("interest_only", "Interest only; the balance at the end"),
                    ("bullet", "Nothing until the end")]),
                _q("extra_payment", "Do you pay extra each year?", "Overpayments shorten it.", "money"),
                _q("start_year", "Does it start later?", "Years from now; 0 if it is running.", "int")]),
        ]
    if section == "accounts":
        return [
            dict(title="The account", fields=[
                _q("label", "What do you call it?", "", "text", True),
                *([_q("owner", "Whose is it?", "", "person")] if two else []),
                _q("wrapper", "How is it taxed?", "", "wrapper"),
                _q("opening", "What is it worth today?", "", "money", True)]),
            dict(title="Saving into it", fields=[
                _q("contribution", "Do you add a fixed amount a year?",
                   "In today's money, until you retire. 0 if not.", "money"),
                _q("contribution_pct_income", "Or a share of your pay?",
                   "E.g. 8% into a workplace pension.", "pct"),
                _q("employer_match_pct", "Does an employer match what you pay in?",
                   "100% if they add one for one; 50% if half; 0 if there is no match.", "pct"),
                _q("employer_match_cap_pct", "…on up to what share of your pay?",
                   "E.g. 5%: they match what you pay in, up to 5% of your pay.", "pct")]),
            dict(title="How it is invested", fields=[
                _q("mix", "How is it invested?", "You can set exact weights and a glide path in "
                   "the table view.", "mix")]),
            dict(title="More options", optional=True, fields=[
                _q("basis", "What did you pay for it?",
                   "The cost basis, for tax on gains. Leave as is if unsure.", "money"),
                _q("withdraw_priority", "In what order is it drawn on?",
                   "1 is spent first. The draw-order tool can work this out.", "int"),
                _q("contribute_priority", "In what order is it paid into?", "1 first.", "int"),
                _q("rebalance", "Rebalanced each year?", "", "select",
                   options=[("annual", "Yes, back to its mix each year"), ("none", "No, let it drift")])]),
        ]
    if section == "care":
        return [
            dict(title="The risk", fields=[
                _q("label", "What do you call it?", "", "text", True),
                *([_q("owner", "For whom?", "", "person")] if two else []),
                _q("probability", "How likely is it to be needed?",
                   "Around half of people reaching 65 need some care.", "pct", True),
                _q("amount", "What would it cost a year?", "In today's money.", "money", True)]),
            dict(title="When and for how long", fields=[
                _q("start_min", "Starting no earlier than age", "", "age", True),
                _q("start_max", "and no later than age", "The start is drawn between the two.",
                   "age", True),
                _q("years", "For how many years?", "Most care lasts under two years; some much longer.",
                   "number", True)]),
            dict(title="More options", optional=True, fields=[
                _q("infl_delta", "Does it rise faster than prices?", "Care costs usually do.", "pct")]),
        ]
    if section == "conversions":
        return [
            dict(title="From and to", fields=[
                _q("label", "What do you call it?", "", "text", True),
                _q("from_ledger", "Move money out of", "Usually an account taxed on the way out.",
                   "ledger"),
                _q("to_ledger", "…and into", "Usually a tax-free account.", "ledger")]),
            dict(title="How much and when", fields=[
                _q("mode", "How much each year?", "", "select", options=[
                    ("amount", "A fixed amount"), ("fill_to", "Enough to fill taxable income to a level")]),
                _q("amount", "Amount (or income level)", "In today's money.", "money", True),
                _q("start_age", "From age", "", "age", True),
                _q("end_age", "Until age", "It stops before this age.", "age", True)]),
        ]
    return []


# --------------------------------------------------------------------------- #
# cards
# --------------------------------------------------------------------------- #
CATEGORY_WORDS = {"employment": "pay", "self_employment": "self-employed", "rental": "rent",
                  "db_pension": "workplace pension", "state_pension": "public pension",
                  "annuity": "annuity", "other_taxable": "other", "tax_free": "tax-free",
                  "one_off": "one-off"}


def _money(v):
    return f"{v:,.0f}"


def _ages(start, end, life=True, lifelong=120.0):
    if end >= lifelong:
        return f"from age {start:.0f}, for life" if life else f"from age {start:.0f}"
    return f"age {start:.0f} to {end:.0f}"


def cards(section: str, plan) -> list[dict]:
    rows = {"income": plan.income, "expenses": plan.expenses, "debt": plan.loans,
            "accounts": plan.ledgers, "care": plan.care, "conversions": plan.conversions}[section]
    people = [p.label for p in plan.persons]
    lifelong = min(120.0, max((p.death_age for p in plan.persons), default=120.0))
    out = []
    for i, r in enumerate(rows):
        who = people[r.owner] if hasattr(r, "owner") and 0 <= r.owner < len(people) else ""
        chips, icon = [], "circle"
        if section == "income":
            icon = {"employment": "briefcase", "state_pension": "bank", "db_pension": "building",
                    "rental": "house-door", "annuity": "shield-check", "one_off": "gift",
                    "self_employment": "clock"}.get(r.category, "arrow-down-circle")
            amount = _money(r.amount) + ("" if r.category == "one_off" else " a year")
            when = f"at age {r.start_age:.0f}" if r.category == "one_off" else _ages(r.start_age, r.end_age, lifelong=lifelong)
            detail = f"{who} · {when}" if len(people) > 1 else when
            chips = [CATEGORY_WORDS.get(r.category, r.category)]
            if r.taxable_fraction <= 0:
                chips.append("tax-free")
            if r.growth:
                chips.append(f"grows {r.growth:.1%} a year")
            if r.probability < 1:
                chips.append(f"{r.probability:.0%} likely")
        elif section == "expenses":
            icon = "basket" if r.essential else "globe"
            if r.recur_years > 1:
                amount = f"{_money(r.amount)} every {r.recur_years} years"
            else:
                amount = f"{_money(r.amount)} a year"
            detail = _ages(r.start_age, r.end_age, lifelong=lifelong)
            chips = ["essential" if r.essential else "could be cut"]
            if r.infl_delta:
                chips.append(f"+{r.infl_delta:.1%} above prices")
            if r.smile:
                chips.append("eases with age")
        elif section == "debt":
            icon = "house" if "mortgage" in r.label.lower() else "credit-card"
            amount = _money(r.balance) + " owed"
            detail = f"{r.rate:.2%} for {r.term_years} more years"
            chips = [r.kind.replace("_", " ")]
            if r.extra_payment:
                chips.append(f"+{_money(r.extra_payment)} a year extra")
        elif section == "accounts":
            w = plan.wrappers[r.wrapper] if r.wrapper < len(plan.wrappers) else None
            icon = _wrapper_icon(r.wrapper)
            amount = _money(r.opening)
            parts = [w.label if w else ""]
            if len(people) > 1:
                parts.append(who)
            detail = " · ".join(p for p in parts if p)
            saving = []
            if r.contribution:
                saving.append(f"{_money(r.contribution)} a year")
            if r.contribution_pct_income:
                saving.append(f"{r.contribution_pct_income:.0%} of pay")
            if saving:
                chips.append("saves " + " + ".join(saving))
            if r.employer_match_pct and r.employer_match_cap_pct:
                chips.append(f"employer matches to {r.employer_match_cap_pct:.0%}")
            eq = _equity_share(plan, r.weights)
            if eq:
                chips.append(f"{eq:.0%} shares")
            chips.append(f"drawn {r.withdraw_priority}{_ordinal(r.withdraw_priority)}")
        elif section == "care":
            icon = "heart"
            amount = f"{_money(r.amount)} a year"
            detail = (f"{who + ' · ' if len(people) > 1 else ''}{r.probability:.0%} chance, "
                      f"starting between {r.start_min:.0f} and {r.start_max:.0f}, "
                      f"for {r.years:g} years")
        elif section == "conversions":
            icon = "arrow-left-right"
            src = plan.ledgers[r.from_ledger].label if r.from_ledger < len(plan.ledgers) else "?"
            dst = plan.ledgers[r.to_ledger].label if r.to_ledger < len(plan.ledgers) else "?"
            amount = (f"{_money(r.amount)} a year" if r.mode == "amount"
                      else f"fill income to {_money(r.amount)}")
            detail = f"{src} → {dst} · age {r.start_age:.0f} to {r.end_age:.0f}"
        out.append(dict(i=i, title=r.label, amount=amount, detail=detail, chips=chips,
                        icon=icon, enabled=getattr(r, "enabled", True)))
    return out


def _ordinal(n):
    return "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def _equity_share(plan, weights):
    if not weights:
        return None
    total = 0.0
    for a, w in zip(plan.market.assets, weights):
        if any(k in a.label.lower() for k in ("equity", "stock", "share")):
            total += w
    return total


# --------------------------------------------------------------------------- #
# a row as the dialog sees it, and back
# --------------------------------------------------------------------------- #
FACTORY = {"income": IncomeRow, "expenses": ExpenseRow, "debt": Loan, "accounts": Ledger,
           "care": CareRisk, "conversions": Conversion}


def rows_of(section, plan):
    return {"income": plan.income, "expenses": plan.expenses, "debt": plan.loans,
            "accounts": plan.ledgers, "care": plan.care, "conversions": plan.conversions}[section]


def new_row(section, plan, kind: str | None):
    """A fresh row with the chosen kind's preset applied."""
    base = asdict(FACTORY[section]())
    if section == "accounts":
        n = len(plan.market.assets)
        base["weights"] = [1.0] + [0.0] * (n - 1)
        base["glide_to"] = []
        base["glide_start_age"] = base["glide_end_age"] = LIFE
        base["contribution"] = 0.0
    if section == "income":
        base.update(amount=0.0, basis="real", start_age=_p0(plan).age)
    if section == "expenses":
        base.update(amount=0.0, owner=-1)
    if section == "care":
        base.update(amount=0.0)
    if section == "conversions":
        base.update(start_age=_p0(plan).retire_age, end_age=_p0(plan).retire_age + 5,
                    to_ledger=min(1, max(0, len(plan.ledgers) - 1)))
    if kind and section in KINDS:
        for k in KINDS[section](plan):
            if k["key"] == kind:
                base.update(k["preset"])
                base["kind_key"] = kind
    return base
