"""Planning tools: what-if adjustments, the levers that matter, pension claiming
ages and account conversions.

Everything here is a *transformation of a plan* followed by a simulation with a
fixed seed and trial count, so two answers differ only because the plans differ -
never because the dice fell differently. Nothing here saves anything; the routes
decide whether a transformed plan becomes a new scenario.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

import numpy as np

from retplan.engine import Projection
from retplan.metrics import kpis
from retplan.plan import Conversion

SEED = 20260916
QUICK = 800            # trials for a slider move - fast, error bar about +/-1.5 pts
TOOL = 1500            # trials for the explorers and the lever ranking


# --------------------------------------------------------------------------- #
# adjustments
# --------------------------------------------------------------------------- #
@dataclass
class Adjust:
    retire: float = 0.0          # years later (+) or earlier (-), everyone
    spend: float = 0.0           # fraction, e.g. -0.10 = spend 10% less
    save: float = 0.0            # save this much more a year until retirement (spend it less)
    equity: float = 0.0          # shift of the mix toward shares, e.g. +0.10
    fee: float = 0.0             # change in the platform fee, e.g. -0.0025
    claim: float = 0.0           # years later public pensions start
    claim_early: float = 0.0667  # reduction per year claimed early
    claim_late: float = 0.08     # increase per year claimed late

    @classmethod
    def from_dict(cls, d: dict) -> "Adjust":
        out = cls()
        for k in cls.__dataclass_fields__:
            try:
                if d.get(k) not in (None, ""):
                    setattr(out, k, float(d[k]))
            except (TypeError, ValueError):
                pass
        out.retire = max(-15.0, min(15.0, out.retire))
        out.spend = max(-0.9, min(2.0, out.spend))
        out.save = max(0.0, min(1e7, out.save))
        out.equity = max(-1.0, min(1.0, out.equity))
        out.fee = max(-0.05, min(0.05, out.fee))
        out.claim = max(-10.0, min(10.0, out.claim))
        return out

    def is_zero(self) -> bool:
        return not any((self.retire, self.spend, self.save, self.equity, self.fee, self.claim))

    def describe(self) -> str:
        parts = []
        if self.retire:
            parts.append(f"retire {abs(self.retire):g} year{'s' if abs(self.retire) != 1 else ''} "
                         f"{'later' if self.retire > 0 else 'earlier'}")
        if self.spend:
            parts.append(f"spend {abs(self.spend):.0%} {'more' if self.spend > 0 else 'less'}")
        if self.save:
            parts.append(f"save {self.save:,.0f} more a year until retiring")
        if self.equity:
            parts.append(f"{abs(self.equity):.0%} {'more' if self.equity > 0 else 'less'} in shares")
        if self.fee:
            parts.append(f"fees {abs(self.fee) * 100:.2f} pts {'higher' if self.fee > 0 else 'lower'}")
        if self.claim:
            parts.append(f"public pension {abs(self.claim):g} year{'s' if abs(self.claim) != 1 else ''} "
                         f"{'later' if self.claim > 0 else 'earlier'}")
        return ", ".join(parts) or "no change"


def _asset_index(plan, *words):
    for i, a in enumerate(plan.market.assets):
        lab = a.label.lower()
        if any(w in lab for w in words):
            return i
    return None


def claim_factor(years: float, early: float, late: float) -> float:
    """Multiplier on a pension claimed `years` after (+) or before (-) its usual age."""
    return max(0.0, 1.0 + late * years) if years >= 0 else max(0.0, 1.0 + early * years)


def apply(plan, adj: Adjust):
    """A deep copy of `plan` with the adjustments made."""
    q = copy.deepcopy(plan)
    if adj.retire:
        old = [pp.retire_age for pp in q.persons]
        for pp in q.persons:
            pp.retire_age = max(pp.age, pp.retire_age + adj.retire)
        for row in q.income:
            if row.category in ("employment", "self_employment") and row.owner < len(old) \
                    and abs(row.end_age - old[row.owner]) < 1e-9:
                row.end_age = q.persons[row.owner].retire_age
        for e in q.expenses:              # spending that switches at retirement moves too
            if abs(e.end_age - old[0]) < 1e-9:
                e.end_age = q.persons[0].retire_age
            if abs(e.start_age - old[0]) < 1e-9:
                e.start_age = q.persons[0].retire_age
    if adj.spend:
        for e in q.expenses:
            e.amount *= (1.0 + adj.spend)
    if adj.save:
        # Unspent income is already swept into savings, so saving more means
        # spending less before retirement: cut the working-years spending rows
        # pro rata by the amount, and the engine saves the difference.
        ret = q.persons[0].retire_age
        now = q.persons[0].age
        before = [e for e in q.expenses if e.enabled and e.start_age <= now < e.end_age and now < ret
                  and not e.recur_years and e.amount > 0]
        total = sum(e.amount for e in before)
        if total > 0:
            cut = min(adj.save, 0.9 * total)
            for e in before:
                if e.end_age > ret:
                    # a row running past retirement: keep the retirement part as is
                    later = copy.deepcopy(e)
                    later.start_age = ret
                    q.expenses.append(later)
                    e.end_age = ret
                e.amount -= cut * e.amount / total
    if adj.equity:
        eq = _asset_index(q, "equity", "stock", "share")
        bd = _asset_index(q, "government", "bond", "credit", "gilt", "treasur")
        if eq is not None and bd is not None:
            for lg in q.ledgers:
                for w in (lg.weights, lg.glide_to):
                    if not w or len(w) <= max(eq, bd):
                        continue
                    if adj.equity > 0:
                        move = min(adj.equity, w[bd])
                    else:
                        move = -min(-adj.equity, w[eq])
                    if w[eq] + w[bd] <= 0:
                        continue
                    w[eq] += move
                    w[bd] -= move
    if adj.fee:
        q.platform_fee = max(0.0, q.platform_fee + adj.fee)
    if adj.claim:
        for row in q.income:
            if row.category == "state_pension":
                owner = q.persons[row.owner] if row.owner < len(q.persons) else q.persons[0]
                new = max(owner.age, row.start_age + adj.claim)
                row.amount *= claim_factor(new - row.start_age, adj.claim_early, adj.claim_late)
                row.start_age = new
    return q


def run(plan, trials: int = QUICK) -> dict:
    """The numbers a slider needs: odds, error bar, median and bad-luck wealth,
    the age the money runs out in the median failing future, lifetime tax."""
    res = Projection(plan).run(trials, seed=SEED)
    k = kpis(res, plan.policy.legacy_target, plan.policy.confidence)
    return dict(success=k["success_probability"], se=k["success_se"],
                p50=k["terminal_real_p50"], p5=k["terminal_real_p5"],
                depletion_age=(None if np.isnan(k["depletion_age_p50"])
                               else k["depletion_age_p50"]),
                tax=k["total_tax_p50"], trials=trials)


# --------------------------------------------------------------------------- #
# the levers that matter
# --------------------------------------------------------------------------- #
def levers(plan, trials: int = TOOL) -> dict:
    """Try each common change on its own and rank them by what they do to the odds."""
    base = run(plan, trials)
    has_pension = any(r.category == "state_pension" for r in plan.income)
    retiring = any(pp.retire_age > pp.age for pp in plan.persons)
    save_step = round(max(2000.0, 0.05 * sum(r.amount for r in plan.income
                                             if r.category == "employment")), -3)
    cands = []
    if retiring:
        cands += [("Retire a year later", Adjust(retire=1)), ("Retire two years later", Adjust(retire=2)),
                  ("Retire a year earlier", Adjust(retire=-1))]
    cands += [("Spend 5% less", Adjust(spend=-0.05)), ("Spend 10% less", Adjust(spend=-0.10)),
              ("Spend 5% more", Adjust(spend=0.05))]
    if retiring:
        cands.append((f"Save {save_step:,.0f} more a year until retiring", Adjust(save=save_step)))
    cands += [("10% more in shares", Adjust(equity=0.10)), ("10% less in shares", Adjust(equity=-0.10))]
    if plan.platform_fee + plan.adviser_fee > 0.002:
        cands.append(("Cut fees by 0.25 points", Adjust(fee=-0.0025)))
    if has_pension:
        cands += [("Claim public pension 2 years later", Adjust(claim=2)),
                  ("Claim public pension 2 years earlier", Adjust(claim=-2))]
    rows = []
    for label, adj in cands:
        r = run(apply(plan, adj), trials)
        rows.append(dict(label=label, adjust=adj.__dict__, success=r["success"],
                         delta=r["success"] - base["success"], p50=r["p50"],
                         delta_p50=r["p50"] - base["p50"], tax=r["tax"]))
    rows.sort(key=lambda x: (-x["delta"], -x["delta_p50"]))
    return dict(base=base, rows=rows, trials=trials,
                noise=2 * base["se"])        # a difference smaller than this is noise


# --------------------------------------------------------------------------- #
# public pension claiming age
# --------------------------------------------------------------------------- #
def claiming(plan, row_index: int, ages, early: float = 0.0667, late: float = 0.08,
             trials: int = TOOL) -> dict:
    """Odds and wealth for each claiming age of one public-pension income row.
    The row's current start age and amount are taken as the usual age and amount."""
    row = plan.income[row_index]
    usual, amount = row.start_age, row.amount
    owner = plan.persons[row.owner] if row.owner < len(plan.persons) else plan.persons[0]
    out = []
    for a in ages:
        q = copy.deepcopy(plan)
        r = q.income[row_index]
        r.start_age = max(owner.age, a)
        r.amount = amount * claim_factor(r.start_age - usual, early, late)
        res = run(q, trials)
        # lifetime pension: from the claiming age to the owner's planning age
        years = max(0.0, owner.death_age - r.start_age)
        out.append(dict(age=a, amount=r.amount, lifetime=r.amount * years, **res))
    for x in out:
        # the age by which a later, larger pension has paid out as much in total as
        # claiming at the usual age (ignoring growth and tax): the longevity bet
        gain = x["amount"] - amount
        x["breakeven"] = (x["age"] + amount * (x["age"] - usual) / gain
                          if x["age"] > usual and gain > 0 else None)
    best = max(out, key=lambda x: (round(x["success"], 3), x["p50"]))
    return dict(row=row.label, usual=usual, amount=amount, rows=out, best=best,
                early=early, late=late, trials=trials)


# --------------------------------------------------------------------------- #
# conversions between accounts
# --------------------------------------------------------------------------- #
def conversions(plan, src: int, dst: int, start_age: float, end_age: float,
                amounts, fill_levels, heir_rate: float = 0.25, trials: int = TOOL) -> dict:
    """Compare no conversion with converting fixed amounts a year, and with filling
    taxable income up to each level, between two ages.

    Money left in an untaxed-on-the-way-in account at the end still owes tax, so the
    comparison uses *after-tax* final wealth: balances in wrappers that tax
    withdrawals are cut by `heir_rate` on their taxable share.
    """
    def after_tax_terminal(q):
        res = Projection(q).run(trials, seed=SEED)
        k = kpis(res, q.policy.legacy_target, q.policy.confidence)
        bw = res.balance_by_wrapper[:, -1, :]
        owed = np.zeros(bw.shape[0])
        for wi, wr in enumerate(q.wrappers):
            owed += bw[:, wi] * wr.withdrawal_taxable_fraction * heir_rate
        net = res.terminal - owed
        return dict(success=k["success_probability"], se=k["success_se"],
                    p50=k["terminal_real_p50"], after_tax_p50=float(np.median(net)),
                    tax=float(np.median(res.tax.sum(axis=1))),
                    converted=float(np.median(res.conversion.sum(axis=1)))
                    if res.conversion is not None else 0.0)

    strategies = [("No conversion", None)]
    strategies += [(f"Convert {a:,.0f} a year", ("amount", a)) for a in amounts if a > 0]
    strategies += [(f"Fill taxable income to {lv:,.0f}", ("fill_to", lv)) for lv in fill_levels if lv > 0]
    rows = []
    for label, spec in strategies:
        q = copy.deepcopy(plan)
        if spec:
            q.conversions = list(q.conversions) + [
                Conversion(label, src, dst, spec[0], spec[1], start_age, end_age)]
        rows.append(dict(label=label, mode=spec[0] if spec else "", value=spec[1] if spec else 0,
                         **after_tax_terminal(q)))
    base = rows[0]
    for r in rows:
        r["delta_after_tax"] = r["after_tax_p50"] - base["after_tax_p50"]
        r["delta_tax"] = r["tax"] - base["tax"]
        r["delta_success"] = r["success"] - base["success"]
    best = max(rows, key=lambda r: (round(r["success"], 2), r["after_tax_p50"]))
    return dict(rows=rows, best=best, heir_rate=heir_rate, trials=trials,
                start_age=start_age, end_age=end_age)


# --------------------------------------------------------------------------- #
# spending check: guardrails on the odds
# --------------------------------------------------------------------------- #
def scale_savings(plan, new_total: float):
    """A copy with every liquid account scaled so the total equals `new_total` -
    "my savings are worth this today", after the markets have moved."""
    q = copy.deepcopy(plan)
    liquid = [lg for lg in q.ledgers if lg.enabled and q.wrappers[lg.wrapper].liquid]
    now = sum(lg.opening for lg in liquid)
    if now > 0 and new_total >= 0:
        f = new_total / now
        for lg in liquid:
            lg.opening *= f
            lg.basis *= f
    return q


def spending_now(plan) -> float:
    """What the household spends this year (or, before retiring, in its first
    retired year) in today's money - regular spending rows only."""
    p0 = plan.persons[0]
    at = p0.age if p0.age >= p0.retire_age else p0.retire_age
    return sum(e.amount for e in plan.expenses
               if e.enabled and not e.recur_years and e.start_age <= at < e.end_age)


def spending_check(plan, target: float | None = None, lower: float | None = None,
                   upper: float | None = None, savings: float | None = None,
                   trials: int = QUICK) -> dict:
    """Risk-based guardrails: the chance of success across a range of spending
    levels, the spending that meets the target, and whether today's spending is
    inside the band where no change is needed."""
    target = plan.policy.confidence if target is None else target
    lower = max(0.0, target - 0.15) if lower is None else lower
    upper = min(0.99, target + 0.10) if upper is None else upper
    base = scale_savings(plan, savings) if savings is not None else plan
    now = spending_now(base)
    grid = [0.3, 0.4, 0.5] + [round(x, 2) for x in np.arange(0.60, 1.401, 0.05)] + [1.5, 1.6]
    rows = []
    for m in grid:
        r = run(apply(base, Adjust(spend=m - 1.0)), trials)
        rows.append(dict(mult=m, spend=now * m, success=r["success"], p50=r["p50"], p5=r["p5"]))

    def spend_at(level):
        """Spending at which success crosses `level` (success falls as spending rises)."""
        for a, b in zip(rows, rows[1:]):
            if a["success"] >= level >= b["success"] and a["success"] != b["success"]:
                t = (a["success"] - level) / (a["success"] - b["success"])
                return a["spend"] + t * (b["spend"] - a["spend"])
        return None if rows[0]["success"] < level else rows[-1]["spend"]

    current = next(r for r in rows if abs(r["mult"] - 1.0) < 1e-9)
    at_target = spend_at(target)
    raise_above, trim_below = spend_at(upper), spend_at(lower)
    s = current["success"]
    if s > upper:
        verdict, change = "raise", (at_target - now) if at_target else None
    elif s < lower:
        verdict, change = "trim", (at_target - now) if at_target else None
    else:
        verdict, change = "hold", 0.0
    return dict(rows=rows, now=now, success=s, se=np.sqrt(max(s * (1 - s), 1e-9) / trials),
                target=target, lower=lower, upper=upper, at_target=at_target,
                raise_when_below=raise_above, trim_when_above=trim_below,
                verdict=verdict, change=change, trials=trials,
                savings=sum(lg.opening for lg in base.ledgers if lg.enabled
                            and base.wrappers[lg.wrapper].liquid))


# --------------------------------------------------------------------------- #
# draw order
# --------------------------------------------------------------------------- #
def _after_tax(res, plan, heir_rate):
    bw = res.balance_by_wrapper[:, -1, :]
    owed = np.zeros(bw.shape[0])
    for wi, wr in enumerate(plan.wrappers):
        owed += bw[:, wi] * wr.withdrawal_taxable_fraction * heir_rate
    return res.terminal - owed


def draw_orders(plan, heir_rate: float = 0.25, finalists: int = 4,
                trials: int = TOOL) -> dict:
    """Every order of drawing on the plan's wrappers, screened on the fixed-return
    path and the best few simulated in full.

    Accounts are grouped by wrapper (the tax treatment is what matters); within a
    wrapper they keep their current relative order. Illiquid accounts stay last.
    """
    import itertools
    from retplan.engine import Projection as P
    liquid = [i for i, lg in enumerate(plan.ledgers)
              if lg.enabled and plan.wrappers[lg.wrapper].liquid]
    wrappers = []
    for i in sorted(liquid, key=lambda i: plan.ledgers[i].withdraw_priority):
        w = plan.ledgers[i].wrapper
        if w not in wrappers:
            wrappers.append(w)
    if len(wrappers) < 2:
        return dict(rows=[], note="There is only one kind of account to draw from.")

    def with_order(order):
        q = copy.deepcopy(plan)
        rank = 1
        for w in order:
            for i in sorted([i for i in liquid if q.ledgers[i].wrapper == w],
                            key=lambda i: plan.ledgers[i].withdraw_priority):
                q.ledgers[i].withdraw_priority = rank
                rank += 1
        for i, lg in enumerate(q.ledgers):
            if i not in liquid:
                lg.withdraw_priority = 100 + i
        return q

    def fixed(q):
        f = copy.deepcopy(q)
        f.market.mode = "fixed"
        f.market.inflation.mode = "fixed"
        return f

    current = tuple(wrappers)
    screened = []
    for order in itertools.permutations(wrappers):
        q = with_order(order)
        res = P(fixed(q)).run(1)
        screened.append((float(_after_tax(res, q, heir_rate)[0]), float(res.tax[0].sum()),
                         int(res.depleted_period[0]), order))
    screened.sort(key=lambda r: (r[2] < 0, r[0]), reverse=True)
    picks = [r[3] for r in screened[:finalists]]
    if current not in picks:
        picks.append(current)
    rows = []
    for order in picks:
        q = with_order(order)
        res = P(q).run(trials, seed=SEED)
        k = kpis(res, q.policy.legacy_target, q.policy.confidence)
        net = _after_tax(res, q, heir_rate)
        rows.append(dict(order=list(order), names=[plan.wrappers[w].label for w in order],
                         current=order == current, success=k["success_probability"],
                         se=k["success_se"], after_tax_p50=float(np.median(net)),
                         tax=float(np.median(res.tax.sum(axis=1)))))
    rows.sort(key=lambda r: (round(r["success"], 2), r["after_tax_p50"]), reverse=True)
    cur = next(r for r in rows if r["current"])
    for r in rows:
        r["delta_after_tax"] = r["after_tax_p50"] - cur["after_tax_p50"]
        r["delta_tax"] = r["tax"] - cur["tax"]
        r["delta_success"] = r["success"] - cur["success"]
    return dict(rows=rows, best=rows[0], current=cur, screened=len(screened),
                heir_rate=heir_rate, trials=trials)


def apply_draw_order(plan, order: list[int]):
    """Set withdraw priorities so wrappers are drawn in `order`."""
    q = copy.deepcopy(plan)
    liquid = [i for i, lg in enumerate(q.ledgers) if lg.enabled and q.wrappers[lg.wrapper].liquid]
    rank = 1
    for w in order:
        for i in sorted([i for i in liquid if q.ledgers[i].wrapper == w],
                        key=lambda i: plan.ledgers[i].withdraw_priority):
            q.ledgers[i].withdraw_priority = rank
            rank += 1
    for i, lg in enumerate(q.ledgers):
        if i not in liquid:
            lg.withdraw_priority = 100 + i
    return q


# --------------------------------------------------------------------------- #
# health and care
# --------------------------------------------------------------------------- #
def health_rows(plan, bridge: float, bridge_to: float, later: float, later_from: float,
                later_growth: float):
    """Spending rows for health cover until public cover starts, and for health
    costs in later life (both essential)."""
    from retplan.plan import ExpenseRow
    p0 = plan.persons[0]
    rows = []
    if bridge > 0 and bridge_to > p0.retire_age:
        rows.append(ExpenseRow("Health cover until public cover", bridge, "real", True,
                               later_growth, False, max(p0.age, p0.retire_age), bridge_to,
                               -1, 0, 1.0))
    if later > 0:
        rows.append(ExpenseRow("Health costs in later life", later, "real", True,
                               later_growth, False, max(p0.age, later_from), 200, -1, 0, 1.0))
    return rows
