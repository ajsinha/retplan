"""The strategy optimiser: when to retire, when to claim, how to spend, draw,
convert and invest - chosen together.

Each decision interacts with the others: retiring earlier makes a later public
pension more valuable, which opens a window of low-income years for conversions,
which changes the best order to draw on the accounts and how much risk the
savings can carry. So they are searched together, on the whole plan, by the
same engine every other number in RetPlan comes from.

The search is staged, not exhaustive (every combination would be millions of
simulations):

1. timing   - each person's retirement age and public-pension claiming age, one
              at a time, repeated until nothing improves;
2. investing - the share in shares (the glide path moves with it);
3. spending  - fixed spending, or guardrails;
4. drawing   - every order of drawing on the accounts (web/levers.draw_orders);
5. converting - Roth-style conversions filling the lower tax bands, in the years
              between retiring and the pension starting;
6. timing again, now the rest is settled.

Every candidate is simulated on the same futures (one seed), so differences come
from the decisions, not from luck; results are cached. The objective is chosen:
the safest plan, the earliest retirement meeting a confidence target, the most
spending meeting it, or the most left after tax meeting it. The winner and the
plan as it stands are then run again with many more futures, and the strategy
reports what each change is worth on its own and which alternatives are within
the noise - a range to choose in, not a falsely precise point.

Settings come from ``strategy.*`` in config/retplan.yaml.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import copy
import logging
import math
import threading
import time
import uuid
from dataclasses import dataclass, field

import numpy as np

from retplan.engine import Projection
from retplan.metrics import kpis
from retplan.plan import JUST_BEFORE, Conversion, to_dict
from web import drawrate, levers

logger = logging.getLogger(__name__)
SEED = levers.SEED

OBJECTIVES = [
    ("odds", "Safest", "shield-check",
     "The highest chance the money lasts, whatever it takes."),
    ("earliest", "Retire earliest", "sunrise",
     "The earliest retirement that still meets your confidence target."),
    ("spend", "Spend the most", "cart",
     "The most you can spend in retirement at your confidence target."),
    ("legacy", "Leave the most", "gift",
     "The most left after tax, while meeting your confidence target."),
]
OBJECTIVE_KEYS = {k for k, *_ in OBJECTIVES}
AREAS = [("timing", "When to retire"), ("claiming", "When to claim public pensions"),
         ("investments", "How to invest"), ("withdrawals", "How to spend and draw"),
         ("conversions", "Roth-style conversions")]


@dataclass
class Settings:
    search_trials: int = 600
    final_trials: int = 3000
    max_seconds: float = 600
    earliest_shift: int = -5
    latest_age: float = 75
    claim_min: float = 62
    claim_max: float = 70
    claim_full: float = 67
    claim_early: float = 0.0667
    claim_late: float = 0.08
    equity_shifts: list = field(default_factory=lambda: [-0.3, -0.2, -0.1, 0.0, 0.1, 0.2])
    try_guardrails: bool = True
    try_draw_orders: bool = True
    conversions: bool = True
    heir_tax_rate: float = 0.25
    enough_odds: float = 0.97       # beyond this, more certainty is not worth more work

    @classmethod
    def from_config(cls, cfg) -> "Settings":
        s = cls()
        if cfg is None:
            return s
        g = cfg
        s.search_trials = max(100, g.get_int("strategy.search_trials", s.search_trials))
        s.final_trials = max(s.search_trials, g.get_int("strategy.final_trials", s.final_trials))
        s.max_seconds = max(10, g.get_float("strategy.max_seconds", s.max_seconds))
        s.earliest_shift = g.get_int("strategy.retire.earliest_shift", s.earliest_shift)
        s.latest_age = g.get_float("strategy.retire.latest_age", s.latest_age)
        s.claim_min = g.get_float("strategy.claiming.min_age", s.claim_min)
        s.claim_max = g.get_float("strategy.claiming.max_age", s.claim_max)
        s.claim_full = g.get_float("strategy.claiming.full_age", s.claim_full)
        s.claim_early = g.get_float("strategy.claiming.early_reduction", s.claim_early)
        s.claim_late = g.get_float("strategy.claiming.late_increase", s.claim_late)
        s.equity_shifts = g.get_float_list("strategy.investments.equity_shifts", s.equity_shifts)
        s.try_guardrails = g.get_bool("strategy.withdrawals.try_guardrails", s.try_guardrails)
        s.try_draw_orders = g.get_bool("strategy.withdrawals.try_draw_orders", s.try_draw_orders)
        s.conversions = g.get_bool("strategy.conversions.enabled", s.conversions)
        s.heir_tax_rate = g.get_float("strategy.conversions.heir_tax_rate", s.heir_tax_rate)
        s.enough_odds = g.get_float("strategy.enough_odds", s.enough_odds)
        return s


class Stop(Exception):
    """The search ran out of time or was cancelled."""


# --------------------------------------------------------------------------- #
# applying decisions to a copy of the plan
# --------------------------------------------------------------------------- #
def _claim_factor(years: float, early: float, late: float) -> float:
    return max(0.0, 1.0 + late * years) if years >= 0 else max(0.0, 1.0 + early * years)


def set_retire(q, base, i: int, age: float) -> None:
    """Person ``i`` retires at ``age``: their pay stops then, and spending rows that
    switch at person 1's retirement switch with it; their glide path moves too."""
    old = base.persons[i].retire_age
    new = max(q.persons[i].age, age)
    shift = new - old
    q.persons[i].retire_age = new
    for row in q.income:
        if row.category in ("employment", "self_employment") and row.owner == i \
                and abs(row.end_age - old) < 1e-3:
            row.end_age = new
    if i == 0:
        for e in q.expenses:
            if abs(e.end_age - old) < 1e-3:
                e.end_age = new - (old - e.end_age)
            if abs(e.start_age - old) < 1e-3:
                e.start_age = new
    for lg in q.ledgers:
        if lg.owner == i and lg.glide_start_age < 150:
            lg.glide_start_age += shift
            lg.glide_end_age += shift


def set_claim(q, base, row: int, age: float, s: Settings) -> None:
    """A public pension claimed at ``age``: the plan's amount is taken to be the
    amount at its own start age, and rescaled by the claiming rules."""
    b = base.income[row]
    r = q.income[row]
    at_full = b.amount / max(1e-9, _claim_factor(b.start_age - s.claim_full,
                                                 s.claim_early, s.claim_late))
    r.start_age = age
    r.amount = at_full * _claim_factor(age - s.claim_full, s.claim_early, s.claim_late)


def pension_rows(plan) -> list[int]:
    """Public-pension rows not yet being paid - the ones whose claiming age is open."""
    out = []
    for i, r in enumerate(plan.income):
        if r.category != "state_pension" or not r.enabled:
            continue
        owner = plan.persons[min(r.owner, len(plan.persons) - 1)]
        if owner.age < r.start_age:
            out.append(i)
    return out


def working(plan) -> list[int]:
    return [i for i, p in enumerate(plan.persons) if p.age < p.retire_age]


def _equity_share(plan, age_of: int = 0, at_age: float | None = None) -> float | None:
    """The share in shares across the liquid accounts, now or at an age."""
    labels = [a.label.lower() for a in plan.market.assets]
    eq = [i for i, lab in enumerate(labels) if any(w in lab for w in ("equity", "stock", "share"))]
    if not eq:
        return None
    tot = w_eq = 0.0
    for lg in plan.ledgers:
        if not lg.enabled or not plan.wrappers[lg.wrapper].liquid or lg.opening <= 0:
            continue
        w = lg.weights
        if at_age is not None and lg.glide_to and lg.glide_end_age < 150:
            a0, a1 = lg.glide_start_age, lg.glide_end_age
            f = 0.0 if at_age <= a0 else 1.0 if at_age >= a1 else (at_age - a0) / max(1e-9, a1 - a0)
            w = [x + f * (y - x) for x, y in zip(lg.weights, lg.glide_to)]
        tot += lg.opening
        w_eq += lg.opening * sum(w[i] for i in eq if i < len(w))
    return w_eq / tot if tot else None


def conversion_setup(plan):
    """(source, target) ledger indices for a conversion - the largest account taxed
    on the way out, into the largest never taxed again - or None."""
    src = dst = None
    for i, lg in enumerate(plan.ledgers):
        wr = plan.wrappers[lg.wrapper]
        if not lg.enabled or not wr.liquid:
            continue
        if wr.withdrawal_taxable_fraction >= 0.99 and not wr.realises_capital_gains:
            if src is None or lg.opening > plan.ledgers[src].opening:
                src = i
        elif wr.withdrawal_taxable_fraction <= 0.01 and not wr.realises_capital_gains \
                and not wr.growth_taxed_annually:
            if dst is None or lg.opening > plan.ledgers[dst].opening:
                dst = i
    return (src, dst) if src is not None and dst is not None else None


# --------------------------------------------------------------------------- #
# the search
# --------------------------------------------------------------------------- #
class Optimiser:
    def __init__(self, plan, objective: str = "odds", target: float | None = None,
                 settings: Settings | None = None, areas=None, latest_age: float | None = None,
                 progress=None, cancel: threading.Event | None = None):
        self.base = copy.deepcopy(plan)
        self.objective = objective if objective in OBJECTIVE_KEYS else "odds"
        self.target = target if target is not None else plan.policy.confidence
        self.s = settings or Settings()
        if latest_age:
            self.s.latest_age = min(self.s.latest_age, latest_age)
        self.areas = set(areas) if areas else {a for a, _ in AREAS}
        self._progress = progress or (lambda frac, stage: None)
        self.cancel = cancel or threading.Event()
        self.cache: dict = {}
        self.t0 = time.time()
        self.evaluations = 0
        self.timed_out = False

    # -- state and evaluation --------------------------------------------------
    def initial_state(self) -> dict:
        b = self.base
        return dict(retire=tuple(p.retire_age for p in b.persons),
                    claim=tuple((i, b.income[i].start_age) for i in pension_rows(b)),
                    equity=0.0, policy=b.policy.method, order=None, conversion=None,
                    spend=1.0)

    def build(self, st: dict):
        q = copy.deepcopy(self.base)
        for i, age in enumerate(st["retire"]):
            if abs(age - self.base.persons[i].retire_age) > 1e-9:
                set_retire(q, self.base, i, age)
        for row, age in st["claim"]:
            if abs(age - self.base.income[row].start_age) > 1e-9:
                set_claim(q, self.base, row, age, self.s)
        if st["equity"]:
            q = levers.apply(q, levers.Adjust(equity=st["equity"]))
        if st["policy"] != q.policy.method:
            q.policy.method = st["policy"]
        if st["order"]:
            q = levers.apply_draw_order(q, list(st["order"]))
        if st["conversion"]:
            mode, value, start, end, src, dst = st["conversion"]
            q.conversions = list(q.conversions) + [
                Conversion("Strategy conversion", src, dst, mode, value, start, end)]
        if st["spend"] != 1.0:
            q = drawrate.scale_retirement(q, st["spend"], retirement_start(q))
        return q

    @staticmethod
    def key(st: dict) -> tuple:
        return (st["retire"], st["claim"], round(st["equity"], 4), st["policy"],
                tuple(st["order"]) if st["order"] else None, st["conversion"],
                round(st["spend"], 4))

    def evaluate(self, st: dict, trials: int | None = None) -> dict:
        trials = trials or self.s.search_trials
        k = (self.key(st), trials)
        if k in self.cache:
            return self.cache[k]
        if self.cancel.is_set():
            raise Stop("cancelled")
        q = self.build(st)
        res = Projection(q).run(trials, seed=SEED)
        kp = kpis(res, q.policy.legacy_target, q.policy.confidence)
        after = levers._after_tax(res, q, self.s.heir_tax_rate)
        m = dict(success=kp["success_probability"], se=kp["success_se"],
                 p50=kp["terminal_real_p50"], p5=kp["terminal_real_p5"],
                 after_tax=float(np.median(after)), tax=kp["total_tax_p50"],
                 depletion=None if math.isnan(kp["depletion_age_p50"]) else kp["depletion_age_p50"],
                 trials=trials)
        self.cache[k] = m
        self.evaluations += 1
        return m

    def extra_work(self, st: dict) -> float:
        """Years worked beyond what the plan intends - a cost to the person, not
        just money."""
        return sum(max(0.0, a - p.retire_age) for a, p in zip(st["retire"], self.base.persons))

    def score(self, m: dict, st: dict) -> tuple:
        """Bigger is better. Odds are compared to half a point, so the search does not
        chase noise, and count only up to ``enough_odds`` - more certainty than that
        is not worth more years of work. Then less extra work, then more left after
        tax."""
        raw = round(m["success"] * 200) / 200
        odds = min(raw, self.s.enough_odds)
        work = -self.extra_work(st)
        if self.objective == "legacy":
            meets = m["success"] >= self.target - 1e-9
            return (1, work, m["after_tax"]) if meets else (0, odds, work, raw, m["after_tax"])
        # the ceiling spares years of work; it never trades certainty for wealth
        return (odds, work, raw, m["after_tax"])

    def better(self, a: dict, sa: dict, b: dict, sb: dict) -> bool:
        return self.score(a, sa) > self.score(b, sb)

    def _check_time(self):
        if time.time() - self.t0 > self.s.max_seconds:
            self.timed_out = True
            raise Stop("time")

    def _coordinate(self, st: dict, field_name: str, index, candidates, earliest=False):
        """Try each candidate value of one decision, the rest fixed; keep the best."""
        best_st, best_m = st, self.evaluate(st)
        options = []
        for v in candidates:
            self._check_time()
            cand = copy.deepcopy(st)
            if field_name == "retire":
                r = list(cand["retire"])
                r[index] = v
                cand["retire"] = tuple(r)
            elif field_name == "claim":
                cand["claim"] = tuple((row, v if row == index else a) for row, a in cand["claim"])
            else:
                cand[field_name] = v
            m = self.evaluate(cand)
            options.append((v, cand, m))
        if earliest:
            meeting = [o for o in options if o[2]["success"] >= self.target]
            if meeting:
                v, cand, m = min(meeting, key=lambda o: o[0])
                return cand, m
        for v, cand, m in options:
            if self.better(m, cand, best_m, best_st):
                best_st, best_m = cand, m
        return best_st, best_m

    def _timing_pass(self, st: dict) -> dict:
        b = self.base
        if "timing" in self.areas:
            for i in working(b):
                p = b.persons[i]
                lo = max(math.ceil(p.age), p.retire_age + self.s.earliest_shift)
                # working longer than planned is on the table only when the plan
                # falls short of the target (or the question is how early)
                short = self.evaluate(st)["success"] < self.target
                longest = p.retire_age + 5 if (short or self.objective == "earliest") \
                    else p.retire_age
                hi = max(lo, min(self.s.latest_age, longest))
                cands = [float(a) for a in range(int(lo), int(hi) + 1)]
                st, _ = self._coordinate(st, "retire", i, cands,
                                         earliest=self.objective == "earliest")
        if "claiming" in self.areas:
            for row, _age in st["claim"]:
                owner = b.persons[min(b.income[row].owner, len(b.persons) - 1)]
                lo = max(self.s.claim_min, math.ceil(owner.age))
                cands = [float(a) for a in range(int(lo), int(self.s.claim_max) + 1)]
                st, _ = self._coordinate(st, "claim", row, cands)
        return st

    def run(self) -> dict:
        st = self.initial_state()
        base_state = copy.deepcopy(st)
        stages = []
        steps = 7
        try:
            self._progress(0.02, "Your plan as it stands")
            self.evaluate(st)
            for n in (1, 2):
                if {"timing", "claiming"} & self.areas:
                    self._progress(0.05 + 0.2 * (n - 1), f"When to retire and claim (pass {n})")
                    before = self.key(st)
                    st = self._timing_pass(st)
                    stages.append("timing")
                    if self.key(st) == before and n > 1:
                        break
            if "investments" in self.areas and self.s.equity_shifts:
                self._progress(0.45, "How to invest")
                st, _ = self._coordinate(st, "equity", None, self.s.equity_shifts)
            if "withdrawals" in self.areas:
                self._progress(0.55, "How to spend")
                pols = ["fixed_real"] + (["guardrails"] if self.s.try_guardrails else [])
                if st["policy"] not in pols:
                    pols.append(st["policy"])
                st, _ = self._coordinate(st, "policy", None, pols)
                if self.s.try_draw_orders:
                    self._progress(0.62, "Which account to draw from first")
                    self._check_time()
                    d = levers.draw_orders(self.build(st), heir_rate=self.s.heir_tax_rate,
                                           finalists=3, trials=self.s.search_trials)
                    if d.get("rows"):
                        cand = dict(st, order=tuple(d["best"]["order"]))
                        if self.better(self.evaluate(cand), cand, self.evaluate(st), st):
                            st = cand
            if "conversions" in self.areas and self.s.conversions:
                self._progress(0.72, "Roth-style conversions")
                st = self._conversions(st)
            if {"timing", "claiming"} & self.areas:
                self._progress(0.8, "When to retire and claim, with the rest settled")
                st = self._timing_pass(st)
            if self.objective == "spend":
                self._progress(0.88, "How much you can spend")
                st = self._max_spend(st)
        except Stop:
            pass
        self._progress(0.92, "Confirming with more futures")
        final = self.evaluate(st, self.s.final_trials)
        baseline = self.evaluate(base_state, self.s.final_trials)
        out = self._report(base_state, st, baseline, final)
        self._progress(1.0, "Done")
        return out

    def _conversions(self, st: dict) -> dict:
        q = self.build(st)
        pair = conversion_setup(q)
        if not pair:
            return st
        p0 = q.persons[0]
        start = max(math.ceil(p0.age), p0.retire_age)
        own_claims = [a for row, a in st["claim"] if q.income[row].owner == 0]
        rmd = min((w.mrd_age for w in q.wrappers if w.mrd_age < 150), default=73)
        end = min([rmd] + [a for a in own_claims if a > start + 1] + [start + 10])
        if end <= start + 1:
            return st
        lowers = sorted(set(q.tax.ordinary.lowers))
        levels = [lv for lv in lowers[2:5] if lv > 0]         # tops of the lower bands
        best_st, best_m = st, self.evaluate(st)
        for lv in levels:
            self._check_time()
            cand = dict(st, conversion=("fill_to", float(lv), float(start), float(end),
                                        pair[0], pair[1]))
            m = self.evaluate(cand)
            if self.better(m, cand, best_m, best_st):
                best_st, best_m = cand, m
        return best_st

    def _max_spend(self, st: dict) -> dict:
        """The largest retirement spending that keeps the odds at the target."""
        lo, hi = 0.3, 2.5
        if self.evaluate(dict(st, spend=lo))["success"] < self.target:
            return st
        for _ in range(9):
            self._check_time()
            mid = (lo + hi) / 2
            if self.evaluate(dict(st, spend=round(mid, 4)))["success"] >= self.target:
                lo = mid
            else:
                hi = mid
        return dict(st, spend=round(lo, 4))

    # -- the report ------------------------------------------------------------
    def _report(self, base_st, st, baseline, final) -> dict:
        b = self.base
        best = self.build(st)
        decisions = []
        names = [p.label for p in b.persons]

        def worth(single):
            """What one change is worth on its own, applied to the plan as it is."""
            try:
                m = self.evaluate(single)
            except Stop:
                return None
            base_m = self.evaluate(base_st)
            return dict(success=m["success"] - base_m["success"],
                        after_tax=m["after_tax"] - base_m["after_tax"])

        for i, (was, now) in enumerate(zip(base_st["retire"], st["retire"])):
            if i in working(b):
                r = list(base_st["retire"])
                r[i] = now
                decisions.append(dict(area="timing", icon="sunrise",
                                      label=f"{names[i]} retires", current=f"at {was:g}",
                                      recommended=f"at {now:g}", changed=abs(now - was) > 1e-9,
                                      worth=worth(dict(base_st, retire=tuple(r))) if abs(now - was) > 1e-9 else None))
        for (row, was), (_, now) in zip(base_st["claim"], st["claim"]):
            r = b.income[row]
            owner = names[min(r.owner, len(names) - 1)]
            amount = best.income[row].amount
            decisions.append(dict(area="claiming", icon="bank",
                                  label=f"{owner} claims {r.label.lower()}", current=f"at {was:g}",
                                  recommended=f"at {now:g}, about {amount:,.0f} a year",
                                  changed=abs(now - was) > 1e-9,
                                  worth=worth(dict(base_st, claim=tuple((rw, now if rw == row else a)
                                                                        for rw, a in base_st["claim"])))
                                  if abs(now - was) > 1e-9 else None))
        eq_now, eq_new = _equity_share(b), _equity_share(best)
        if eq_now is not None:
            decisions.append(dict(area="investments", icon="pie-chart", label="Share in shares",
                                  current=f"{eq_now:.0%}", recommended=f"{eq_new:.0%}",
                                  changed=abs(st["equity"]) > 1e-9,
                                  worth=worth(dict(base_st, equity=st["equity"])) if st["equity"] else None))
        pol = {"fixed_real": "Fixed spending, rising with prices",
               "guardrails": "Guardrails: trim in bad years, raise in good ones"}
        decisions.append(dict(area="withdrawals", icon="sliders", label="Spending policy",
                              current=pol.get(base_st["policy"], base_st["policy"].replace("_", " ")),
                              recommended=pol.get(st["policy"], st["policy"].replace("_", " ")),
                              changed=st["policy"] != base_st["policy"],
                              worth=worth(dict(base_st, policy=st["policy"]))
                              if st["policy"] != base_st["policy"] else None))
        if st["order"]:
            order_names = [b.wrappers[w].label for w in st["order"]]
            decisions.append(dict(area="withdrawals", icon="sort-down", label="Draw order",
                                  current=", then ".join(_current_order(b)),
                                  recommended=", then ".join(order_names), changed=True,
                                  worth=worth(dict(base_st, order=st["order"]))))
        if st["conversion"]:
            mode, value, start, end, src, dst = st["conversion"]
            decisions.append(dict(area="conversions", icon="arrow-left-right",
                                  label="Roth-style conversions", current="none",
                                  recommended=(f"from age {start:g} to {end:g}, move enough from "
                                               f"{b.ledgers[src].label} to {b.ledgers[dst].label} "
                                               f"to fill taxable income to {value:,.0f} a year"),
                                  changed=True, worth=worth(dict(base_st, conversion=st["conversion"]))))
        if st["spend"] != 1.0:
            start = retirement_start(best)
            k = int(round(start - best.persons[0].age))
            tl = timeline(best, b)
            first = tl[min(k, len(tl) - 1)]["spend"] if tl else 0.0
            decisions.append(dict(area="withdrawals", icon="cart", label="Spending in retirement",
                                  current="as planned",
                                  recommended=(f"about {first:,.0f} a year from age {start:g} - "
                                               f"{st['spend']:.0%} of what is planned"),
                                  changed=True, worth=None))
        alternatives = self._alternatives(st, final)
        return dict(objective=self.objective, target=self.target, baseline=baseline,
                    strategy=final, meets_target=final["success"] >= self.target, decisions=decisions, alternatives=alternatives,
                    timeline=timeline(best, b), rules=rules(best, st),
                    plan=to_dict(best), evaluations=self.evaluations,
                    seconds=round(time.time() - self.t0, 1), timed_out=self.timed_out,
                    search_trials=self.s.search_trials, final_trials=self.s.final_trials)

    def _alternatives(self, st, final) -> list:
        """Timing choices whose odds are within the noise of the recommended ones."""
        out = []
        best_m = self.evaluate(st)
        noise = 2 * best_m["se"] + 0.005
        for (k, trials), m in self.cache.items():
            if trials != self.s.search_trials:
                continue
            retire, claim, eq, pol, order, conv, spend = k
            if (eq, pol, order, conv, spend) != (round(st["equity"], 4), st["policy"],
                                                 tuple(st["order"]) if st["order"] else None,
                                                 st["conversion"], round(st["spend"], 4)):
                continue
            if (retire, claim) == (st["retire"], st["claim"]):
                continue
            if sum(retire) > sum(st["retire"]) + 1e-9:
                continue                     # never an alternative that means more work
            if m["success"] >= best_m["success"] - noise and (
                    self.objective != "earliest" or m["success"] >= self.target):
                changes = []
                for i, (a, b2) in enumerate(zip(retire, st["retire"])):
                    if a != b2:
                        changes.append(f"{self.base.persons[i].label} retires at {a:g}")
                for (row, a), (_, b2) in zip(claim, st["claim"]):
                    if a != b2:
                        owner = self.base.persons[min(self.base.income[row].owner,
                                                      len(self.base.persons) - 1)].label
                        changes.append(f"{owner} claims at {a:g}")
                if changes:
                    out.append(dict(changes=changes, success=m["success"],
                                    after_tax=m["after_tax"],
                                    delta=m["success"] - best_m["success"]))
        out.sort(key=lambda x: (-x["success"], -x["after_tax"]))
        return out[:6]


def retirement_start(plan) -> float:
    """Person 1's age when retirement spending starts: their retirement age, or
    now if already retired."""
    p0 = plan.persons[0]
    return float(max(math.ceil(p0.age), p0.retire_age))


def _current_order(plan) -> list[str]:
    seen, out = set(), []
    for lg in sorted([lg for lg in plan.ledgers if lg.enabled and plan.wrappers[lg.wrapper].liquid],
                     key=lambda lg: lg.withdraw_priority):
        if lg.wrapper not in seen:
            seen.add(lg.wrapper)
            out.append(plan.wrappers[lg.wrapper].label)
    return out


def timeline(plan, base) -> list[dict]:
    """The strategy year by year on the fixed-return path: ages, events, income,
    spending, draws, conversions, tax and savings."""
    from web.viewmodel import deterministic
    _, res = deterministic(plan)
    p = plan.persons
    events: dict[int, list] = {}
    for i, person in enumerate(p):
        if person.age < person.retire_age:
            events.setdefault(int(round(person.retire_age - person.age)), []).append(
                f"{person.label} retires")
    for row in plan.income:
        if row.category == "state_pension" and row.enabled:
            owner = p[min(row.owner, len(p) - 1)]
            if owner.age < row.start_age:
                events.setdefault(int(round(row.start_age - owner.age)), []).append(
                    f"{owner.label} claims {row.label.lower()} ({row.amount:,.0f} a year)")
    for w in plan.wrappers:
        if w.mrd_age < 150:
            for i, person in enumerate(p):
                if person.age < w.mrd_age and any(lg.owner == i and plan.wrappers[lg.wrapper] is w
                                                   and lg.enabled for lg in plan.ledgers):
                    events.setdefault(int(round(w.mrd_age - person.age)), []).append(
                        f"{person.label}: required withdrawals from {w.label} begin")
    rows = []
    conv = res.conversion[0] if res.conversion is not None else np.zeros(res.spend.shape[1])
    T = res.spend.shape[1]
    for k in range(T):
        rows.append(dict(year=k, ages=[round(person.age + k) for person in p],
                         events=events.get(k, []), income=float(res.income[0, k]),
                         spend=float(res.spend[0, k]), withdrawal=float(res.withdrawal[0, k]),
                         conversion=float(conv[k]), tax=float(res.tax[0, k]),
                         savings=float(res.balance[0, k]),
                         net_worth=float(res.net_worth[0, k])))
    return rows


def rules(plan, st) -> list[str]:
    """The strategy's standing rules, in words."""
    out = []
    order = _current_order(plan)
    if len(order) > 1:
        out.append("Spend from " + ", then ".join(order) + ".")
    if st["policy"] == "guardrails":
        pol = plan.policy
        out.append(f"Guardrails: when your withdrawal has grown to more than "
                   f"{1 + pol.guard_up:.0%} of its starting share of your savings, cut "
                   f"discretionary spending by {pol.guard_cut:.0%}; when it has fallen below "
                   f"{1 - pol.guard_down:.0%} of it, raise spending by {pol.guard_raise:.0%}. "
                   f"Essentials are never cut.")
    eq_now = _equity_share(plan)
    p0 = plan.persons[0]
    eq_ret = _equity_share(plan, at_age=p0.retire_age)
    eq_late = _equity_share(plan, at_age=p0.retire_age + 10)
    if eq_now is not None:
        text = f"Hold about {eq_now:.0%} in shares now"
        if eq_ret is not None and abs(eq_ret - eq_now) > 0.02:
            text += f", {eq_ret:.0%} when you retire"
        if eq_late is not None and abs(eq_late - (eq_ret or eq_now)) > 0.02:
            text += f" and {eq_late:.0%} ten years on"
        out.append(text + ", rebalancing once a year.")
    if st["conversion"]:
        mode, value, start, end, src, dst = st["conversion"]
        out.append(f"Each year from {start:g} to {end:g}, convert enough from "
                   f"{plan.ledgers[src].label} to {plan.ledgers[dst].label} to bring taxable "
                   f"income up to {value:,.0f} - paying the tax from other savings.")
    out.append("Check the plan once a year against your real balances, and after any large "
               "market move.")
    return out


# --------------------------------------------------------------------------- #
# background jobs
# --------------------------------------------------------------------------- #
class Jobs:
    """Optimiser runs in background threads, one per workspace at a time."""

    def __init__(self, keep: int = 50):
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self.keep = keep

    def start(self, owner: str, plan, **kw) -> str:
        with self._lock:
            for j in self._jobs.values():
                if j["owner"] == owner and j["status"] == "running":
                    j["cancel"].set()
            jid = uuid.uuid4().hex[:12]
            cancel = threading.Event()
            job = dict(id=jid, owner=owner, status="running", progress=0.0,
                       stage="Starting", result=None, error=None, cancel=cancel,
                       started=time.time(), plan_label=plan.label,
                       objective=kw.get("objective", "odds"))
            self._jobs[jid] = job
            if len(self._jobs) > self.keep:
                for old in sorted(self._jobs.values(), key=lambda j: j["started"])[:-self.keep]:
                    self._jobs.pop(old["id"], None)

        def progress(frac, stage):
            job["progress"], job["stage"] = frac, stage

        def work():
            try:
                job["result"] = Optimiser(plan, progress=progress, cancel=cancel, **kw).run()
                job["status"] = "done"
            except Exception as exc:  # noqa: BLE001 - reported on the page
                logger.exception("strategy optimiser failed")
                job["status"], job["error"] = "failed", str(exc)

        threading.Thread(target=work, name=f"strategy-{jid}", daemon=True).start()
        return jid

    def get(self, owner: str, jid: str) -> dict | None:
        j = self._jobs.get(jid)
        return j if j and j["owner"] == owner else None

    def latest(self, owner: str) -> dict | None:
        mine = [j for j in self._jobs.values() if j["owner"] == owner]
        return max(mine, key=lambda j: j["started"]) if mine else None
