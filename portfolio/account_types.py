"""The kinds of account a portfolio holds, and what each one is.

A portfolio is a collection of accounts; an account is one of four kinds:

- **investments** - hold positions (securities, and cash inside the account),
  priced daily. A brokerage account, a 401(k), an IRA, an HSA…
- **cash** - a balance you update now and then: checking, savings, CDs.
- **property** - a value you update now and then: a home, other real estate, a
  car, other valuables. Counts in net worth, never in investable assets.
- **debt** - a balance with a rate and a payment, which pays itself down between
  updates: a mortgage, a car loan, a credit card.

Each type also says how it is taxed (``tax``: taxable, deferred, free, or none),
which is what the tax-treatment view and the retirement plan need; the plan maps
the type to a tax wrapper with the type's full rules (web/plan_link.py).

This module is plain data so the portfolio package, the plan and the pages can
all share it.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import re

KINDS = [
    ("investments", "Investments", "graph-up-arrow", "Accounts that hold securities, priced every day."),
    ("cash", "Cash", "cash-stack", "Bank balances you update now and then."),
    ("property", "Property", "house", "Your home, other real estate, vehicles, valuables."),
    ("debt", "Debts", "credit-card", "Mortgages and loans; they pay down on their own."),
]
KIND_LABEL = {k: label for k, label, _, _ in KINDS}

# key, label, kind, icon, tax (taxable | deferred | free | none), blurb, group
TYPES: list[dict] = [
    # investments
    dict(key="brokerage", label="Brokerage", kind="investments", icon="graph-up-arrow",
         tax="taxable", blurb="An ordinary investment account; gains taxed when you sell."),
    dict(key="k401", label="401(k) / 403(b)", kind="investments", icon="building",
         tax="deferred", blurb="A traditional workplace plan (457 and TSP too)."),
    dict(key="roth401k", label="Roth 401(k)", kind="investments", icon="building",
         tax="free", blurb="The Roth side of a workplace plan."),
    dict(key="ira", label="Traditional IRA", kind="investments", icon="piggy-bank",
         tax="deferred", blurb="Including rollovers from old jobs."),
    dict(key="roth_ira", label="Roth IRA", kind="investments", icon="shield-check",
         tax="free", blurb="Tax-free in retirement; no required withdrawals."),
    dict(key="hsa", label="HSA", kind="investments", icon="heart",
         tax="free", blurb="A health savings account, invested."),
    dict(key="edu529", label="529 plan", kind="investments", icon="mortarboard",
         tax="free", blurb="Education savings; left out of retirement plans."),
    dict(key="pension_pot", label="Pension pot", kind="investments", icon="bank",
         tax="deferred", blurb="A pension outside the US: SIPP, RRSP, super…"),
    dict(key="isa", label="Tax-free savings", kind="investments", icon="umbrella",
         tax="free", blurb="An ISA, TFSA and the like."),
    # cash
    dict(key="checking", label="Checking", kind="cash", icon="wallet2", tax="taxable",
         blurb="Everyday bank account."),
    dict(key="savings", label="Savings", kind="cash", icon="piggy-bank", tax="taxable",
         blurb="Savings or high-yield savings."),
    dict(key="cd", label="CD / fixed term", kind="cash", icon="lock", tax="taxable",
         blurb="Money locked for a term."),
    dict(key="money_market", label="Money market", kind="cash", icon="cash-coin",
         tax="taxable", blurb="A money-market account or fund held as cash."),
    # property
    dict(key="home", label="Home", kind="property", icon="house", tax="none",
         blurb="The home you live in."),
    dict(key="real_estate", label="Other real estate", kind="property", icon="building",
         tax="none", blurb="A rental, a second home, land."),
    dict(key="vehicle", label="Vehicle", kind="property", icon="truck", tax="none",
         blurb="A car, a boat."),
    dict(key="valuables", label="Other asset", kind="property", icon="gem", tax="none",
         blurb="Art, a business stake, anything else of value."),
    # debts
    dict(key="mortgage", label="Mortgage", kind="debt", icon="house", tax="none",
         blurb="A loan secured on property."),
    dict(key="heloc", label="Home equity loan", kind="debt", icon="house", tax="none",
         blurb="A HELOC or second mortgage."),
    dict(key="car_loan", label="Car loan", kind="debt", icon="truck", tax="none",
         blurb="A vehicle loan or lease."),
    dict(key="student_loan", label="Student loan", kind="debt", icon="mortarboard",
         tax="none", blurb="Education debt."),
    dict(key="credit_card", label="Credit card", kind="debt", icon="credit-card",
         tax="none", blurb="A balance carried from month to month."),
    dict(key="other_debt", label="Other loan", kind="debt", icon="receipt", tax="none",
         blurb="Any other money owed."),
]
BY_KEY = {t["key"]: t for t in TYPES}
TAX_LABEL = {"taxable": "Taxable", "deferred": "Tax-deferred", "free": "Tax-free",
             "none": "Not invested"}
OWNERS = [(0, "You"), (1, "Partner"), (-1, "Joint")]
OWNER_LABEL = dict(OWNERS)

# Typical rates for a new debt, before the owner types their own.
DEBT_DEFAULTS = {"mortgage": (0.065, 30), "heloc": (0.085, 10), "car_loan": (0.075, 5),
                 "student_loan": (0.055, 10), "credit_card": (0.22, 3),
                 "other_debt": (0.09, 5)}


def get(key: str) -> dict:
    return BY_KEY.get(key) or BY_KEY["brokerage"]


def of_kind(kind: str) -> list[dict]:
    return [t for t in TYPES if t["kind"] == kind]


# Words in an account's name that give its type away - most specific first.
_GUESSES = [
    (r"roth\s*401|roth\s*403|roth\s*457|designated\s+roth", "roth401k"),
    (r"roth", "roth_ira"),
    (r"401\s*\(?k|403\s*\(?b|457|\btsp\b|thrift|retirement\s+plan|workplace", "k401"),
    (r"\bira\b|rollover|sep\b|simple\s+ira|traditional", "ira"),
    (r"\bhsa\b|health\s+sav", "hsa"),
    (r"529|college|education", "edu529"),
    (r"\bisa\b|tfsa|tax[-\s]free", "isa"),
    (r"sipp|rrsp|super(annuation)?|pension", "pension_pot"),
    (r"money\s*market|\bmmf?\b|sweep", "money_market"),
    (r"\bcd\b|certificate|fixed\s+term", "cd"),
    (r"checking|current\s+account", "checking"),
    (r"savings|high[-\s]yield", "savings"),
    (r"brokerage|individual|joint|taxable|trading|investment", "brokerage"),
]


def guess(name: str) -> str:
    """The most likely type for an account called ``name`` (brokerage if nothing fits)."""
    text = (name or "").lower()
    for pattern, key in _GUESSES:
        if re.search(pattern, text):
            return key
    return "brokerage"


def monthly_payment(balance: float, rate: float, years: float) -> float:
    """The level payment that clears ``balance`` over ``years`` at ``rate`` a year."""
    n = max(1, round(years * 12))
    r = rate / 12
    if balance <= 0:
        return 0.0
    if r <= 0:
        return balance / n
    return balance * r / (1 - (1 + r) ** -n)


def amortised(balance: float, rate: float, payment: float, months: int) -> float:
    """What is owed ``months`` after a balance of ``balance``, paying ``payment`` a month."""
    b, r = float(balance), rate / 12
    for _ in range(max(0, months)):
        if b <= 0:
            return 0.0
        b = b * (1 + r) - payment
    return max(0.0, b)
