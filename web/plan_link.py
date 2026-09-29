"""A plan linked to a portfolio: its accounts and debts come from the portfolio.

A portfolio knows what you own and owe today; a plan knows what a portfolio
cannot - ages, income, spending, what you will save and in which order you will
spend. When a plan is linked (``plan.portfolio_id``), every time it is read:

- each investment, cash and property account becomes (or updates) a plan account
  with ``account_id`` set: its name, owner, today's value, cost basis and - for
  investments - the mix of what it holds; its tax wrapper follows its type;
- each debt becomes (or updates) a loan: what is owed today, the rate, the years
  left;
- accounts and debts removed from the portfolio leave the plan.

What the plan adds to a linked account - contributions, employer match, draw and
pay-in order, a glide path, rebalancing, paused or not - is kept, because it
lives on the plan's copy and a sync never touches it. Plan accounts with no
``account_id`` are the plan's own and are left alone.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import logging
import math

from portfolio import account_types as at
from portfolio.repository import NotFound
from retplan.plan import Ledger, Loan

logger = logging.getLogger(__name__)

# portfolio account type -> the wizard's wrapper key (web/wizard.account_wrappers)
WRAPPER_OF = {"brokerage": "brokerage", "k401": "k401", "roth401k": "roth401k",
              "ira": "ira", "roth_ira": "roth_ira", "hsa": "hsa", "edu529": "isa",
              "pension_pot": "pension_pot", "isa": "isa", "checking": "cash",
              "savings": "cash", "cd": "cash", "money_market": "cash", "home": "property",
              "real_estate": "property", "vehicle": "property", "valuables": "property"}
# accounts that are not retirement money start paused in the plan
PAUSED_BY_DEFAULT = {"edu529", "vehicle", "valuables"}
# a holding's asset class -> the plan's asset-class slot (web/wizard._weights)
SLOT = {"equity": "equity", "intl_equity": "equity", "em_equity": "equity",
        "crypto": "alternatives", "other": "equity", "bond": "government",
        "cash": "cash", "property": "property", "commodity": "alternatives"}


def _wrapper_index(plan, key: str) -> int:
    """The plan's wrapper for a wizard wrapper key, added if the plan lacks it."""
    from web.wizard import account_wrappers
    template = account_wrappers({"age": plan.persons[0].age if plan.persons else 45},
                                len(plan.persons) > 1)[key]
    for i, w in enumerate(plan.wrappers):
        if w.label == template.label:
            return i
    plan.wrappers.append(template)
    return len(plan.wrappers) - 1


def _order(key: str) -> tuple[int, int]:
    from web.wizard import ACCOUNT_BY_KEY
    t = ACCOUNT_BY_KEY.get(key)
    if t:
        return t["draw"], t["pay"]
    return (9, 9) if key == "property" else (5, 7)


def _mix(plan, v, account) -> list[float]:
    from web.wizard import RISK, _weights
    if account.kind == "cash":
        return _weights(plan, {"cash": 1.0})
    if account.kind == "property":
        return _weights(plan, {"property": 1.0})
    mix: dict[str, float] = {}
    total = 0.0
    for p in v.positions:
        if p.account_id == account.id and p.value > 0:
            k = SLOT.get(p.asset_class, "equity")
            mix[k] = mix.get(k, 0.0) + p.value
            total += p.value
    if total <= 0:
        return _weights(plan, RISK["balanced"]["mix"])
    return _weights(plan, {k: x / total for k, x in mix.items()})


def _basis(v, account) -> float:
    """Cost basis: holdings with a known cost at cost, the rest at today's value
    (no gain assumed) - never zero, which would overstate the gain to be taxed.
    Accounts taxed in full on the way out have no basis to speak of."""
    if account.tax == "deferred":
        return 0.0
    if account.kind != "investments":
        return account.value
    return account.cost + (account.value - account.cost_value)


def _remove_ledgers(plan, drop: set[int]) -> None:
    """Remove ledgers by index, re-pointing conversions and the sweep account."""
    if not drop:
        return
    keep = [i for i in range(len(plan.ledgers)) if i not in drop]
    new_index = {old: new for new, old in enumerate(keep)}
    plan.ledgers = [plan.ledgers[i] for i in keep]
    plan.conversions = [c for c in plan.conversions
                        if c.from_ledger in new_index and c.to_ledger in new_index]
    for c in plan.conversions:
        c.from_ledger, c.to_ledger = new_index[c.from_ledger], new_index[c.to_ledger]
    plan.policy.sweep_ledger = new_index.get(plan.policy.sweep_ledger, 0)


def sync(plan, repo, owner: str) -> dict:
    """Bring a linked plan's accounts and loans into line with its portfolio.
    Returns what happened: {linked, missing, name, added, removed}."""
    out = dict(linked=bool(plan.portfolio_id), missing=False, name="", added=0, removed=0)
    if not plan.portfolio_id:
        return out
    try:
        pf = repo.get(owner, plan.portfolio_id)
        v = repo.valuation(owner, plan.portfolio_id)
    except NotFound:
        out["missing"] = True
        return out
    out["name"] = pf["name"]
    two = len(plan.persons) > 1
    accounts = {a.id: a for a in v.accounts}

    # -- accounts: update, remove, add
    drop = {i for i, lg in enumerate(plan.ledgers)
            if lg.account_id and (lg.account_id not in accounts
                                  or accounts[lg.account_id].kind == "debt")}
    out["removed"] += len(drop)
    _remove_ledgers(plan, drop)
    have = {lg.account_id: lg for lg in plan.ledgers if lg.account_id}
    for a in v.accounts:
        if a.kind == "debt":
            continue
        key = WRAPPER_OF.get(a.type, "brokerage")
        lg = have.get(a.id)
        if lg is None:
            draw, pay = _order(key)
            lg = Ledger(a.name, 0, 0, weights=[], withdraw_priority=draw,
                        contribute_priority=pay, account_id=a.id,
                        enabled=a.type not in PAUSED_BY_DEFAULT,
                        rebalance="none" if a.kind == "property" else "annual")
            plan.ledgers.append(lg)
            out["added"] += 1
        lg.label = a.name
        lg.wrapper = _wrapper_index(plan, key)
        lg.owner = 1 if (a.owner_person == 1 and two) else 0
        lg.opening = round(a.value, 2)
        lg.basis = round(_basis(v, a), 2)
        lg.weights = _mix(plan, v, a)
        if a.kind != "investments":
            lg.glide_to = []

    # -- debts: update, remove, add
    before = len(plan.loans)
    plan.loans = [ln for ln in plan.loans
                  if not ln.account_id or (ln.account_id in accounts
                                           and accounts[ln.account_id].kind == "debt")]
    out["removed"] += before - len(plan.loans)
    have_loans = {ln.account_id: ln for ln in plan.loans if ln.account_id}
    for a in v.accounts:
        if a.kind != "debt":
            continue
        ln = have_loans.get(a.id)
        if ln is None:
            ln = Loan(a.name, account_id=a.id)
            plan.loans.append(ln)
            out["added"] += 1
        rate, years = at.DEBT_DEFAULTS.get(a.type, (0.07, 10))
        ln.label = a.name
        ln.balance = round(a.value, 2)
        ln.rate = a.rate if a.rate is not None else rate
        ln.term_years = max(1, math.ceil(a.months_left / 12)) if a.months_left else years
        ln.kind = "amortising"
        ln.start_year = 0

    # -- the plan still needs somewhere to save unspent income
    if not plan.ledgers:
        plan.ledgers.append(Ledger("Savings from unspent income",
                                   _wrapper_index(plan, "brokerage"), 0, weights=[],
                                   withdraw_priority=1, contribute_priority=9))
        from web.wizard import RISK, _weights
        plan.ledgers[-1].weights = _weights(plan, RISK["balanced"]["mix"])
    if not 0 <= plan.policy.sweep_ledger < len(plan.ledgers) or \
            not plan.ledgers[plan.policy.sweep_ledger].enabled:
        taxable = [i for i, lg in enumerate(plan.ledgers) if lg.enabled
                   and plan.wrappers[lg.wrapper].realises_capital_gains
                   and plan.wrappers[lg.wrapper].liquid]
        plan.policy.sweep_ledger = taxable[0] if taxable else 0
    return out


def link(plan, repo, owner: str, pid: int, replace: bool = True) -> dict:
    """Link a plan to a portfolio. With ``replace``, the plan's own accounts and
    loans go (the portfolio is now the record of them); otherwise they stay
    alongside the linked ones."""
    repo.get(owner, pid)                               # NotFound if not theirs
    if replace:
        _remove_ledgers(plan, {i for i, lg in enumerate(plan.ledgers) if not lg.account_id})
        plan.loans = [ln for ln in plan.loans if ln.account_id]
    plan.portfolio_id = int(pid)
    return sync(plan, repo, owner)


def unlink(plan) -> None:
    """Freeze the plan: its accounts and loans keep today's figures and become its own."""
    plan.portfolio_id = 0
    for lg in plan.ledgers:
        lg.account_id = 0
    for ln in plan.loans:
        ln.account_id = 0
