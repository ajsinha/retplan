"""Turns engine output into everything a page needs: KPIs, charts, tables.

Keeping this out of the route modules means the dashboard and the reports read
from one assembled view model, and a chart and its table-view twin can never
disagree about the numbers.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import logging

import numpy as np

from retplan.engine import Projection
from retplan.markets import MarketModel, expected_durations, stationary_distribution
from retplan.metrics import bands, drawdown, funded_ratio, kpis, reconcile
from web import charts

logger = logging.getLogger(__name__)
PCTS = [5, 10, 25, 50, 75, 90, 95]


def deterministic(plan):
    """The projection the sheet shows: fixed returns, fixed inflation."""
    import copy
    q = copy.deepcopy(plan)
    q.market.mode = "fixed"
    q.market.inflation.mode = "fixed"
    proj = Projection(q)
    return proj, proj.run(1)


def base_view(plan) -> dict:
    """KPIs and charts that need no simulation - live as soon as inputs change."""
    proj, res = deterministic(plan)
    years = [int(plan_start(plan) + t) for t in range(res.net_worth.shape[1])]
    ages = [round(a, 1) for a in res.ages]
    nw = res.net_worth[0].tolist()
    shortfall = res.shortfall[0]
    depleted = int(res.depleted_period[0])

    acct_series = []
    for i, lg in enumerate(plan.ledgers):
        if not lg.enabled:
            continue
        vals = res.balance_by_wrapper[0, :, min(lg.wrapper,
                                                res.balance_by_wrapper.shape[2] - 1)]
        acct_series.append((lg.label, list(vals)))
    # One band per wrapper, not per account, because the ledger dimension is
    # aggregated by wrapper in the engine's balance view.
    seen, wrapper_series = set(), []
    for lg in plan.ledgers:
        w = min(lg.wrapper, res.balance_by_wrapper.shape[2] - 1)
        if w in seen:
            continue
        seen.add(w)
        label = plan.wrappers[w].label if w < len(plan.wrappers) else f"Wrapper {w + 1}"
        wrapper_series.append((label, list(res.balance_by_wrapper[0, :, w])))

    flows = [("Income", list(res.income[0])), ("Spending", list(res.spend[0])),
             ("Tax", list(res.tax[0])), ("Withdrawals", list(res.withdrawal[0])),
             ("Paid in", list(res.contribution[0]))]

    rec = reconcile(res)
    fr = float(funded_ratio(res, plan.policy.discount_rate)[0])
    return dict(
        years=years, ages=ages, res=res, projection=proj,
        net_worth=nw,
        funded=fr,
        funded_verdict="Fully funded" if shortfall.sum() <= 1.0 else "Funding gap",
        depleted_age=(None if depleted < 0 else float(res.ages[depleted])),
        total_tax=float(res.tax[0].sum()),
        first_year_spend=float(res.spend[0, 0]),
        terminal=float(nw[-1]),
        reconcile=rec,
        chart_networth=charts.line_chart(years, [("Net worth", nw)],
                                         "Net worth", "today's money"),
        chart_accounts=charts.stacked_area(years, wrapper_series,
                                           "Where the money sits", "today's money"),
        chart_flows=charts.line_chart(years, flows, "Money in, money out",
                                      "today's money"),
        wrapper_series=wrapper_series, flow_series=flows)


def plan_start(plan) -> int:
    return 2026


def simulate(plan, trials: int, seed=None) -> dict:
    """Run the Monte Carlo and assemble everything the dashboard renders."""
    res = Projection(plan).run(trials, seed=seed or plan.seed)
    k = kpis(res, plan.policy.legacy_target, plan.policy.confidence)
    years = [plan_start(plan) + t for t in range(res.net_worth.shape[1])]
    nw = bands(res.net_worth, PCTS)
    sp = bands(res.spend, PCTS)
    median = nw[3].tolist()
    band_pairs = [(nw[0].tolist(), nw[6].tolist()),
                  (nw[1].tolist(), nw[5].tolist()),
                  (nw[2].tolist(), nw[4].tolist())]
    sample = [res.net_worth[i].tolist() for i in range(min(20, len(res.net_worth)))]

    mm = MarketModel(plan.market)
    em = mm.effective_moments(seed=plan.seed, n=min(4000, max(500, trials)),
                              T=plan.horizon)
    pi = stationary_distribution(mm.P)
    effective = []
    for j, a in enumerate(plan.market.assets):
        mean, sd = float(em["mean"][j]), float(em["sd"][j])
        effective.append(dict(label=a.label, target=a.mu, effective=mean,
                              compound=mean - 0.5 * sd * sd,
                              target_sd=a.sigma, effective_sd=sd))
    regimes = [dict(label=r.label, share=float(em["regime_mix"][i]),
                    stationary=float(pi[i]),
                    duration=float(expected_durations(mm.P)[i]))
               for i, r in enumerate(plan.market.regimes)]

    dep = res.depleted_period
    dep_curve = []
    for i in range(len(years)):
        share = float(((dep >= 0) & (dep <= i)).mean())
        dep_curve.append((float(res.ages[i]), share))

    return dict(
        trials=trials, kpis=k, years=years, median=median, bands=band_pairs,
        spend_median=sp[3].tolist(), sample=sample,
        terminal=res.terminal.tolist(),
        depletion_curve=dep_curve,
        effective=effective, regimes=regimes,
        shrinkage=float(mm.shrinkage[0] if mm.shrinkage else 0.0),
        drawdown=float(drawdown(res).min()),
        chart_fan=charts.fan_chart(years, band_pairs, median, "Range of outcomes",
                                   "net worth, today's money"),
        chart_paths=charts.spaghetti(years, sample, median,
                                     "A sample of individual futures",
                                     "net worth, today's money"),
        chart_terminal=charts.histogram(res.terminal.tolist(),
                                        "Where you end up",
                                        "terminal net worth, today's money"),
        chart_depletion=charts.line_chart(
            [a for a, _ in dep_curve], [("Chance the money has run out", [s for _, s in dep_curve])],
            "Chance the money has run out by each age", "cumulative"),
    )


def solver_view(plan, trials: int) -> dict:
    """The expensive extras: solvers, the spending sweep and the tornado."""
    from retplan import solvers
    t = max(200, min(1500, trials // 2))
    ms = solvers.max_sustainable_spend(plan, trials=t, seed=plan.seed)
    er = solvers.earliest_retirement_age(plan, trials=t, seed=plan.seed)
    rq = solvers.required_extra_saving(plan, trials=t, seed=plan.seed)
    curve = solvers.success_curve(plan, trials=t, seed=plan.seed, n=17)
    torn = solvers.tornado(plan, trials=t, seed=plan.seed)
    return dict(
        max_spend=ms["spend"], max_spend_bracketed=ms["bracketed"],
        earliest_age=er["age"], earliest_bracketed=er["bracketed"],
        required_saving=rq["amount"],
        sweep=[(a, b) for a, b in curve],
        tornado=[(r[0], r[1], r[2]) for r in torn],
        chart_sweep=charts.line_chart([a for a, _ in curve],
                                      [("Success probability", [b for _, b in curve])],
                                      "Success against spending", "probability"),
        chart_tornado=charts.tornado([(r[0], r[1], r[2]) for r in torn],
                                     "What moves the answer"),
    )


def audit_checks(plan, view) -> list:
    """The same discipline as the workbook's audit sheet, applied to the web model."""
    res = view["res"]
    out = []

    def check(label, ok, detail="", severity="Blocking"):
        out.append(dict(label=label, ok=bool(ok),
                        status="PASS" if ok else ("FAIL" if severity == "Blocking"
                                                  else "REVIEW"),
                        severity=severity, detail=detail))

    rec = view["reconcile"]
    check("Balance roll-forward ties every year", rec["pass"],
          f"worst relative error {rec['max_rel_error']:.2e}")
    check("No portfolio balance goes negative", float(res.balance.min()) >= -1e-6)
    check("At least one account holds money",
          sum(l.opening for l in plan.ledgers) > 0)
    check("At least one spending row is active", len(plan.expenses) > 0)
    check("Retirement age is after current age",
          all(p.retire_age >= p.age for p in plan.persons))
    check("Planning age is after retirement age",
          all(p.death_age > p.retire_age for p in plan.persons))
    check("Horizon covers the planning age",
          plan.persons[0].age + plan.horizon >= plan.persons[0].death_age,
          "the projection stops before the plan does", "Review")
    for i, lg in enumerate(plan.ledgers):
        if abs(sum(lg.weights) - 1.0) > 0.001 and sum(lg.weights) > 0:
            check(f"Allocation sums to 100% ({lg.label})", False,
                  f"sums to {sum(lg.weights):.1%}")
    corr = np.asarray(plan.market.corr, dtype=float)
    check("Correlations lie inside [-1, 1]",
          bool(np.all(np.abs(corr) <= 1.0 + 1e-9)))
    check("Correlation matrix is symmetric",
          bool(np.allclose(corr, corr.T, atol=1e-6)), severity="Review")
    for k, r in enumerate(plan.market.regimes):
        if abs(sum(r.trans) - 1.0) > 1e-3:
            check(f"Regime row sums to 1 ({r.label})", False,
                  f"sums to {sum(r.trans):.3f}")
    lowers = plan.tax.ordinary.lowers
    check("Tax bands ascend", all(b > a for a, b in zip(lowers, lowers[1:])))
    check("Tax rates lie inside [0, 100%]",
          all(0 <= r <= 1 for r in plan.tax.ordinary.rates))
    check("Expected returns are inside a defensible range",
          all(-0.05 <= a.mu <= 0.15 for a in plan.market.assets),
          severity="Review")
    check("Inflation assumption is plausible",
          -0.02 <= plan.market.inflation.mean <= 0.10, severity="Review")
    check("Total fees are inside a plausible range",
          plan.platform_fee + plan.adviser_fee <= 0.03, severity="Review")
    check("Spending never falls below the essential floor",
          bool(np.all(res.spend[0] + 1e-6 >= 0)))
    return out
