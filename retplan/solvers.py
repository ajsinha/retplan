"""Solvers: the questions people actually ask, answered by bisection.

Every solver re-runs the whole model, so the answer respects tax, forced draws,
sequencing and policy rather than a closed-form approximation of them.
"""
from __future__ import annotations

import copy

import numpy as np

from .engine import Projection
from .metrics import kpis


def _scaled(plan, factor):
    q = copy.deepcopy(plan)
    for row in q.expenses:
        row.amount *= factor
    return q


def success_of(plan, trials=1000, seed=None):
    res = Projection(plan).run(trials, seed=seed)
    ok = res.success(plan.policy.legacy_target)
    return float(ok.mean())


def bisect(fn, lo, hi, target, tol=1e-4, max_iter=24, increasing=False):
    """Find x where fn(x) == target.  Returns (x, iterations, bracketed)."""
    f_lo, f_hi = fn(lo), fn(hi)
    if (f_lo - target) * (f_hi - target) > 0:
        # No root in the bracket.  Ties go to the low end: "no extra saving is
        # needed" is the right answer when the plan already clears the target.
        best = lo if abs(f_lo - target) <= abs(f_hi - target) else hi
        return best, 0, False
    for i in range(max_iter):
        mid = 0.5 * (lo + hi)
        f_mid = fn(mid)
        if abs(hi - lo) <= tol * max(1.0, abs(mid)):
            return mid, i + 1, True
        if (f_lo - target) * (f_mid - target) <= 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return 0.5 * (lo + hi), max_iter, True


def max_sustainable_spend(plan, trials=1000, seed=None, confidence=None):
    """Highest first-year spending that still meets the confidence target."""
    conf = plan.policy.confidence if confidence is None else confidence
    base = Projection(plan)
    first_year = float(base.ess_real[0] + base.disc_real[0])

    def fn(f):
        return success_of(_scaled(plan, f), trials, seed)

    f, iters, ok = bisect(fn, 0.1, 3.0, conf, tol=2e-3)
    return dict(factor=f, spend=first_year * f, iterations=iters, bracketed=ok,
                first_year_base=first_year)


def earliest_retirement_age(plan, trials=1000, seed=None, confidence=None):
    conf = plan.policy.confidence if confidence is None else confidence
    lo = plan.persons[0].age + 0.5
    hi = min(85.0, plan.persons[0].death_age - 1)

    def fn(age):
        q = copy.deepcopy(plan)
        for pp in q.persons:
            pp.retire_age = age
        for row in q.income:
            if row.category in ("employment", "self_employment"):
                row.end_age = min(row.end_age, age)
        return success_of(q, trials, seed)

    age, iters, ok = bisect(fn, lo, hi, conf, tol=1e-2)
    return dict(age=age, iterations=iters, bracketed=ok)


def required_extra_saving(plan, trials=1000, seed=None, confidence=None):
    """Extra real saving per year, into the sweep account, to hit the target."""
    conf = plan.policy.confidence if confidence is None else confidence
    idx = min(max(0, plan.policy.sweep_ledger), max(0, len(plan.ledgers) - 1))

    def fn(extra):
        q = copy.deepcopy(plan)
        if q.ledgers:
            q.ledgers[idx].contribution += extra
        return success_of(q, trials, seed)

    if fn(0.0) >= conf:
        return dict(amount=0.0, iterations=1, bracketed=True)
    amt, iters, ok = bisect(fn, 0.0, 200000.0, conf, tol=1e-2)
    return dict(amount=max(0.0, amt), iterations=iters, bracketed=ok)


def success_curve(plan, trials=800, seed=None, n=21, lo=0.5, hi=1.5):
    """Success probability against spending level - the single most useful chart."""
    base = Projection(plan)
    first_year = float(base.ess_real[0] + base.disc_real[0])
    out = []
    for f in np.linspace(lo, hi, n):
        out.append((first_year * f, success_of(_scaled(plan, f), trials, seed)))
    return out


DRIVERS = [
    ("Expected returns", "ret", 0.01),
    ("Inflation", "infl", 0.01),
    ("Spending", "spend", 0.10),
    ("Retirement age", "retage", 2.0),
    ("Fees", "fees", 0.005),
    ("Longevity", "death", 5.0),
    ("Volatility", "vol", 0.03),
    ("Crash frequency", "crash", 0.03),
]


def _perturb(plan, key, delta):
    q = copy.deepcopy(plan)
    if key == "ret":
        for a in q.market.assets:
            a.mu += delta
    elif key == "infl":
        q.market.inflation.mean += delta
    elif key == "spend":
        q = _scaled(q, 1.0 + delta)
    elif key == "retage":
        for pp in q.persons:
            pp.retire_age += delta
        for row in q.income:
            if row.category in ("employment", "self_employment"):
                row.end_age += delta
    elif key == "fees":
        q.platform_fee += delta
    elif key == "death":
        for pp in q.persons:
            pp.death_age += delta
    elif key == "vol":
        for a in q.market.assets:
            a.sigma = max(0.0, a.sigma + delta)
    elif key == "crash":
        q.market.crash.prob = max(0.0, q.market.crash.prob + delta)
    return q


def tornado(plan, trials=800, seed=None):
    """Rank the drivers by how much they move the success probability."""
    rows = []
    for label, key, delta in DRIVERS:
        down = success_of(_perturb(plan, key, -delta), trials, seed)
        up = success_of(_perturb(plan, key, +delta), trials, seed)
        rows.append((label, down, up, abs(up - down)))
    rows.sort(key=lambda r: -r[3])
    return rows
