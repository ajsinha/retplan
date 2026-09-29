"""The suggested draw rate: how much of your savings to take in the first year of
retirement.

A "4% rule" is a draw rate someone else worked out for someone else's plan. This
one is worked out for yours: RetPlan scales your *retirement* spending up and down
(what you spend while working, and so what you save, stays as it is), runs your
whole plan at each level, and finds the level at which the chance of success meets
your confidence target. The draw rate is the first retired year's withdrawal from
savings at that level - spending, plus the tax on the withdrawal, less pensions and
other income - divided by what your savings are worth at the start of that
year, both taken from the typical (fixed-return) future. "Retirement" here is the
first year nobody in the household is paid for work. Because pensions often start
a few years later, the average draw over the first ten years is given too.

A cautious and a bolder rate come from the guardrail odds either side of the
target, so the answer is a range to start in rather than a single figure to trust
to the decimal.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import copy

import numpy as np

from retplan.engine import Projection
from retplan.plan import JUST_BEFORE
from web import levers

GRID = [0.4, 0.55, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.35, 1.5, 1.7, 2.0]


def retirement_index(plan) -> int:
    """The first year in which the whole household is retired and nobody is paid
    for work - the first year lived on savings and pensions (0 if already)."""
    proj = Projection(plan)
    on_savings = np.asarray(proj.hh_retired) & (np.asarray(proj.pensionable) <= 0)
    return int(np.argmax(on_savings)) if on_savings.any() else len(on_savings) - 1


def scale_retirement(plan, mult: float, at_age: float):
    """A copy with every spending row from `at_age` (person 1's age) scaled by
    `mult`; a row that spans that age is split so its working years are kept."""
    q = copy.deepcopy(plan)
    extra = []
    for e in q.expenses:
        if e.end_age <= at_age:
            continue
        if e.start_age < at_age:
            later = copy.deepcopy(e)
            later.start_age = at_age
            later.amount *= mult
            extra.append(later)
            e.end_age = at_age - JUST_BEFORE
        else:
            e.amount *= mult
    q.expenses.extend(extra)
    return q


def _typical(plan, k: int) -> tuple[float, float, float, float]:
    """Liquid savings at the start of year k, that year's draw from savings, its
    spending, and the average draw over the ten years from k, on the fixed-return
    path."""
    from web.viewmodel import deterministic
    _, res = deterministic(plan)
    liquid = [w for w, wr in enumerate(plan.wrappers) if wr.liquid]
    savings = float(sum(res.balance_by_wrapper[0, k, w] for w in liquid
                        if w < res.balance_by_wrapper.shape[2]))
    draws = res.withdrawal[0] + res.mrd[0]
    return savings, float(draws[k]), float(res.spend[0, k]), float(np.mean(draws[k:k + 10]))


def suggest(plan, trials: int = levers.QUICK, target: float | None = None,
            cautious: float | None = None, bold: float | None = None) -> dict:
    """The draw rate that meets the confidence target, with a cautious and a bold one."""
    target = plan.policy.confidence if target is None else target
    cautious = min(0.99, target + 0.10) if cautious is None else cautious
    bold = max(0.05, target - 0.15) if bold is None else bold
    k = retirement_index(plan)
    at_age = float(plan.persons[0].age + k)
    savings, draw_now, spend_now, avg_now = _typical(plan, k)

    rows = []
    for m in GRID:
        q = scale_retirement(plan, m, at_age)
        r = levers.run(q, trials)
        s, d, sp, avg = _typical(q, k)
        rows.append(dict(mult=m, success=r["success"], draw=d, spend=sp, avg=avg,
                         rate=d / s if s > 0 else None))

    def at(level):
        """Interpolate the row where success crosses `level` (it falls as spending rises)."""
        for a, b in zip(rows, rows[1:]):
            if a["success"] >= level >= b["success"] and a["success"] != b["success"]:
                t = (a["success"] - level) / (a["success"] - b["success"])
                return {key: a[key] + t * (b[key] - a[key])
                        for key in ("mult", "draw", "spend", "avg", "success")}
        if rows[0]["success"] < level:          # even the lowest spending falls short
            return None
        return {key: rows[-1][key] for key in ("mult", "draw", "spend", "avg", "success")}

    def pick(level):
        hit = at(level)
        if hit is None:
            return None
        return dict(level=level, mult=hit["mult"], spend=hit["spend"], draw=hit["draw"],
                    rate=hit["draw"] / savings if savings > 0 else None,
                    avg_rate=hit["avg"] / savings if savings > 0 else None,
                    capped=hit["mult"] >= GRID[-1] - 1e-9)

    current = rows[GRID.index(1.0)]
    return dict(
        age=at_age, years_away=k, savings=savings,
        now=dict(spend=spend_now, draw=draw_now,
                 rate=draw_now / savings if savings > 0 else None,
                 avg_rate=avg_now / savings if savings > 0 else None,
                 success=current["success"]),
        suggested=pick(target), cautious=pick(cautious), bold=pick(bold),
        target=target, trials=trials,
        se=float(np.sqrt(max(target * (1 - target), 1e-9) / trials)),
        rows=rows)
