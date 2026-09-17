#!/usr/bin/env python3
"""RetPlan test suite - plain asserts, no test framework required.

    python3 tests/run_tests.py            # unit and engine tests
    python3 tests/run_tests.py --slow     # adds the statistical validation
"""
from __future__ import annotations

import math
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np

from retplan.engine import Projection, _amortise
from retplan.markets import (AssetClass, CrashSpec, InflationSpec, MarketModel,
                             MarketSpec, Regime, expected_durations,
                             stationary_distribution)
from retplan.metrics import kpis, reconcile
from retplan.plan import (ExpenseRow, IncomeRow, Ledger, Loan, Person, Plan, Policy,
                          Wrapper, load_plan, plan_from_dict, save_plan, to_dict)
from retplan.rng import (LEcuyer, cholesky_psd, norm_ppf, student_t, triangular_ppf)
from retplan.solvers import bisect, max_sustainable_spend, success_of
from retplan.tax import Schedule, TaxSystem

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f"   {detail}" if detail and not cond else ""))


def close(a, b, tol=1e-9):
    return abs(a - b) <= tol * max(1.0, abs(b))


# ------------------------------------------------------------------ helpers
def simple_plan(spend=40000, opening=1_000_000, ret=0.0, infl=0.0, T=40,
                taxable_fraction=0.0, bands=None, horizon_person=200):
    wr = Wrapper("W", withdrawal_taxable_fraction=taxable_fraction,
                 realises_capital_gains=False, growth_taxed_annually=False)
    tax = TaxSystem(ordinary=Schedule("o", *(bands or ([0.0], [0.0]))))
    return Plan(horizon=T, persons=[Person("A", 60, 60, horizon_person)],
                expenses=[ExpenseRow("L", spend, essential=True)],
                wrappers=[wr],
                ledgers=[Ledger("A", 0, 0, opening=opening, basis=opening,
                                weights=[1.0])],
                market=MarketSpec(mode="fixed",
                                  assets=[AssetClass("X", ret, 0, 0, 0, 0)],
                                  corr=[[1.0]],
                                  inflation=InflationSpec(mode="fixed", mean=infl)),
                tax=tax, platform_fee=0.0)


# ------------------------------------------------------------------ L1 unit
def test_rng():
    print("\nrandom numbers")
    g = LEcuyer(12345, 20000)
    u = g.uniforms(10)
    check("uniforms lie in (0,1)", u.min() > 0 and u.max() < 1)
    check("uniform mean ~ 0.5", abs(u.mean() - 0.5) < 0.005)
    check("uniform variance ~ 1/12", abs(u.var() - 1 / 12) < 0.001)
    check("reproducible from the same seed",
          np.array_equal(LEcuyer(12345, 20000).uniforms(10), u))
    check("different seeds differ", not np.array_equal(LEcuyer(999, 20000).uniforms(10), u))
    a = norm_ppf(LEcuyer(7, 50000, "asset").uniforms(1))[:, 0]
    b = norm_ppf(LEcuyer(7, 50000, "regime").uniforms(1))[:, 0]
    check("streams are independent", abs(np.corrcoef(a, b)[0, 1]) < 0.02,
          f"corr={np.corrcoef(a, b)[0, 1]:.4f}")
    check("norm_ppf(0.975) == 1.959963985",
          close(float(norm_ppf(np.array([0.975]))[0]), 1.959963985, 1e-8))
    check("norm_ppf is symmetric",
          close(float(norm_ppf(np.array([0.3]))[0]), -float(norm_ppf(np.array([0.7]))[0]), 1e-9))
    d = triangular_ppf(LEcuyer(3, 200000).uniforms(5), 0.2, 0.35, 0.6)
    check("triangular mean matches theory", abs(d.mean() - (0.2 + 0.35 + 0.6) / 3) < 0.002)
    check("triangular respects its bounds", d.min() >= 0.2 and d.max() <= 0.6)
    z = norm_ppf(LEcuyer(5, 100000, "asset").uniforms(1))[:, 0]
    cu = LEcuyer(5, 100000, "chi2").uniforms(5)
    t = student_t(z, cu, 5.0)
    check("student-t keeps unit variance", abs(t.std() - 1.0) < 0.08, f"sd={t.std():.4f}")
    check("student-t has fatter tails than normal",
          (np.abs(t) > 3).mean() > (np.abs(z) > 3).mean())
    L, lam = cholesky_psd(np.array([[1, .5], [.5, 1]]))
    check("cholesky reproduces the matrix", np.allclose(L @ L.T, [[1, .5], [.5, 1]]))
    check("valid matrix needs no shrinkage", lam == 0.0)
    _, lam2 = cholesky_psd(np.array([[1, .99, .99], [.99, 1, .99], [.99, .99, 1]]))
    check("near-singular matrix is repaired", lam2 >= 0.0)


def test_tax():
    print("\ntax engine")
    s = Schedule("o", [0, 12570, 50270, 100000, 125140], [0.0, 0.20, 0.40, 0.60, 0.45])
    check("no tax below the first band", s.tax_on_taxable(10000) == 0.0)
    check("first band is exact", close(float(s.tax_on_taxable(20000)), 0.20 * (20000 - 12570)))
    check("second band is exact",
          close(float(s.tax_on_taxable(60000)),
                0.20 * (50270 - 12570) + 0.40 * (60000 - 50270)))
    check("marginal rate is read correctly", s.marginal_rate(60000) == 0.40)
    rng = np.random.default_rng(0)
    x0 = rng.uniform(0, 200000, 5000)
    need = rng.uniform(1, 150000, 5000)
    worst = 0.0
    for f in (0.0, 0.25, 0.5, 0.75, 1.0):
        g = s.gross_up(need, x0, f)
        delivered = g - (s.tax_on_taxable(x0 + f * g) - s.tax_on_taxable(x0))
        worst = max(worst, float(np.abs(delivered - need).max()))
    check("gross-up is exact for every taxable fraction", worst < 1e-6,
          f"worst error {worst:.2e}")
    for sc in (0.5, 1.0, 2.0, 7.3):
        b = Schedule("s", list(np.array(s.lowers) * sc), list(s.rates))
        check(f"tax is homogeneous at scale {sc}",
              close(float(b.tax_on_taxable(60000 * sc)),
                    sc * float(s.tax_on_taxable(60000)), 1e-12))
    try:
        Schedule("bad", [100, 0], [0.1, 0.2])
        check("ascending bands are enforced", False)
    except ValueError:
        check("ascending bands are enforced", True)
    try:
        Schedule("bad", [0, 10], [0.1, 1.5])
        check("rates outside [0,1] are rejected", False)
    except ValueError:
        check("rates outside [0,1] are rejected", True)


def test_amortisation():
    print("\ndebt")
    ln = Loan("m", 200000, 0.05, 20, "amortising")
    pay, interest, bal = _amortise(ln, 40)
    ann = 200000 * 0.05 / (1 - 1.05 ** -20)
    check("level payment matches the annuity formula", close(pay[0], ann, 1e-9))
    check("interest in year 1 is balance x rate", close(interest[0], 10000.0, 1e-12))
    check("loan is cleared on schedule", bal[20] < 1e-6 and bal[19] > 0)
    check("principal repaid equals the balance",
          close(float(sum(pay) - sum(interest)), 200000.0, 1e-9))
    io = _amortise(Loan("io", 100000, 0.04, 10, "interest_only"), 20)
    check("interest-only never amortises", close(io[2][9], 100000.0, 1e-9))
    ex = _amortise(Loan("x", 200000, 0.05, 20, "amortising", extra_payment=10000), 40)
    check("overpayment shortens the term", np.argmax(ex[2] <= 1e-6) < 20


                                          )


# ------------------------------------------------------------- L2 engine
def test_golden():
    print("\ngolden scenarios")
    r = Projection(simple_plan(40000, 400000, 0.0, 0.0, 40)).run(1)
    check("G1 zero return: depletion is exactly P0/spend",
          int(r.depleted_period[0]) == 10, f"got {r.depleted_period[0]}")
    check("G1 balances step down by the spend",
          close(r.balance[0, 5], 400000 - 5 * 40000, 1e-9))

    rate, N = 0.05, 30
    W = 1e6 * rate / (1 - (1 + rate) ** -N) / (1 + rate)
    r = Projection(simple_plan(W, 1e6, rate, 0.0, 35)).run(1)
    check("G2 annuity identity: the portfolio lands exactly on zero",
          abs(r.balance[0, 30]) < 1e-6, f"balance {r.balance[0, 30]:.6f}")

    bands = ([0, 12570, 50270], [0.0, 0.20, 0.40])
    r = Projection(simple_plan(45000, 3e6, 0.0, 0.0, 15, 1.0, bands)).run(1)
    net = r.withdrawal[0, 0] - r.tax[0, 0]
    check("G3 net of tax exactly meets the need", close(net, 45000, 1e-9),
          f"delivered {net:.6f}")
    check("G3 no shortfall while money remains", r.shortfall[0, :10].sum() == 0)

    p = simple_plan(45000, 3e6, 0.0, 0.0, 15, 1.0, bands)
    p.wrappers[0].early_penalty = 0.10
    p.wrappers[0].early_age = 200
    r = Projection(p).run(1)
    g, t = r.withdrawal[0, 0], r.tax[0, 0]
    check("G3b penalty is handled inside the same inversion",
          close(g * 0.9 - t, 45000, 1e-8), f"delivered {g * 0.9 - t:.6f}")

    p = simple_plan(30000, 1e6, 0.03, 0.02, 30, 1.0, bands)
    p.income = [IncomeRow("pension", 0, "db_pension", 12000, "real", 0.0, False, 0, 200, 1.0)]
    p.loans = [Loan("m", 150000, 0.04, 12, "amortising")]
    r = Projection(p).run(1)
    rec = reconcile(r)
    check("G6 reconciliation ties every period", rec["pass"],
          f"max rel error {rec['max_rel_error']:.2e}")
    check("G6 debt is cleared", r.debt_balance[0, 12] < 1e-6)

    p = simple_plan(20000, 1e6, 0.02, 0.0, 30, 1.0, bands)
    p.wrappers[0].mrd_age = 70
    p.wrappers[0].mrd_divisors = [(70, 25.0), (80, 18.0), (90, 11.0)]
    r = Projection(p).run(1)
    check("G7 forced draws start at the stated age",
          r.mrd[0, 9] == 0 and r.mrd[0, 10] > 0)
    check("G7 forced draw equals balance / divisor",
          close(r.mrd[0, 10], r.balance[0, 10] / 25.0, 1e-9))
    check("G7 unspent forced draws are reinvested, not lost",
          r.contribution[0, 10] > 0)

    p = simple_plan(40000, 1e6, 0.0, 0.0, 20)
    p.policy = Policy(method="fixed_real", legacy_target=500000)
    r = Projection(p).run(1)
    check("G9 legacy target redefines success", not r.success(500000)[0])
    check("G9 the same plan succeeds without a legacy target", r.success(0.0)[0])


def test_policies():
    print("\nwithdrawal policies")
    for method in ("fixed_real", "fixed_nominal", "pct_portfolio", "vpw", "guardrails",
                   "table"):
        p = simple_plan(40000, 1e6, 0.04, 0.02, 30, 1.0,
                        ([0, 20000], [0.0, 0.25]))
        p.policy = Policy(method=method)
        r = Projection(p).run(1)
        ok = (np.all(np.isfinite(r.balance)) and np.all(r.balance >= -1e-9)
              and np.all(r.spend >= -1e-9))
        check(f"{method} produces a finite, non-negative path", ok)
        check(f"{method} never spends below the essential floor",
              bool(np.all(r.spend[0, :-1] + r.shortfall[0, :-1] >= 0)))
    # A pure percentage of the portfolio is self-limiting and cannot run out.
    # With an essential floor it can, because the floor overrides the percentage -
    # which is the whole point of having a floor.
    p = simple_plan(40000, 1e6, 0.0, 0.0, 30)
    p.expenses[0].essential = False
    p.policy = Policy(method="pct_portfolio", pct=0.05)
    r = Projection(p).run(1)
    check("percentage of portfolio alone never exhausts it", r.balance[0, -1] > 0)
    p.expenses[0].essential = True
    r = Projection(p).run(1)
    check("an essential floor can still exhaust a percentage policy",
          r.balance[0, -1] <= r.balance[0, 0])


def test_determinism():
    print("\ndeterminism")
    p = simple_plan(40000, 1e6, 0.06, 0.02, 40, 1.0, ([0, 20000], [0.0, 0.25]))
    p.market.mode = "mc"
    p.market.assets[0].sigma = 0.16
    a = Projection(p).run(500, seed=4242)
    b = Projection(p).run(500, seed=4242)
    check("same seed gives identical results",
          np.array_equal(a.net_worth, b.net_worth))
    c = Projection(p).run(500, seed=4243)
    check("a different seed gives different results",
          not np.array_equal(a.net_worth, c.net_worth))
    check("trial 0 is unchanged by the trial count",
          np.allclose(Projection(p).run(50, seed=4242).net_worth[0], a.net_worth[0]))


def test_serialisation():
    print("\nconfiguration")
    p = simple_plan(40000, 1e6, 0.05, 0.02, 30, 1.0, ([0, 20000], [0.0, 0.25]))
    path = "/tmp/claude-1000/_plan_roundtrip.json"
    save_plan(p, path)
    q = load_plan(path)
    check("plan survives a JSON round trip", to_dict(p) == to_dict(q))
    check("reloaded plan projects identically",
          np.allclose(Projection(p).run(1).net_worth, Projection(q).run(1).net_worth))


def test_edges():
    print("\nedge cases")
    cases = {
        "zero portfolio": simple_plan(40000, 0.0),
        "zero spending": simple_plan(0.0, 1e6),
        "one period": simple_plan(40000, 1e6, T=1),
        "100% tax band": simple_plan(40000, 1e6, T=10, taxable_fraction=1.0,
                                     bands=([0.0], [1.0])),
        "all illiquid": simple_plan(40000, 1e6),
        "huge spending": simple_plan(10_000_000, 1e6),
    }
    cases["all illiquid"].wrappers[0].liquid = False
    for name, p in cases.items():
        try:
            r = Projection(p).run(3)
            ok = np.all(np.isfinite(r.net_worth)) and np.all(r.balance >= -1e-9)
            check(f"{name} runs without error", ok)
        except Exception as exc:
            check(f"{name} runs without error", False, repr(exc))
    p = simple_plan(40000, 1e6, 0.05, 0.02, 30)
    p.market.mode = "mc"
    p.market.nu = 2.01
    p.market.dist = "t"
    try:
        Projection(p).run(20, seed=1)
        check("degrees of freedom just above 2 is accepted", True)
    except Exception as exc:
        check("degrees of freedom just above 2 is accepted", False, repr(exc))


def test_solvers():
    print("\nsolvers")
    f, iters, ok = bisect(lambda x: x * x, 0.0, 4.0, 4.0, tol=1e-9)
    check("bisection finds a known root", ok and abs(f - 2.0) < 1e-4, f"got {f}")
    f, _, ok = bisect(lambda x: 5.0, 0.0, 1.0, 9.0)
    check("an unbracketed target is reported", not ok)
    p = simple_plan(40000, 1e6, 0.05, 0.02, 30, 1.0, ([0, 20000], [0.0, 0.25]))
    p.market.mode = "mc"
    p.market.assets[0].sigma = 0.15
    p.policy.confidence = 0.80
    out = max_sustainable_spend(p, trials=300, seed=77)
    check("max sustainable spend is bracketed", out["bracketed"])
    lower = success_of(_scale(p, out["factor"] * 0.8), 300, 77)
    higher = success_of(_scale(p, out["factor"] * 1.2), 300, 77)
    check("spending less succeeds more often", lower >= higher - 1e-9,
          f"{lower:.3f} vs {higher:.3f}")


def _scale(plan, f):
    import copy
    q = copy.deepcopy(plan)
    for row in q.expenses:
        row.amount *= f
    return q


# ----------------------------------------------------- L4 statistical
def test_market_statistics(trials=40000):
    print("\nmarket engine (statistical)")
    eq = AssetClass("Equity", 0.07, 0.17, 0.02, 0.002, 1.0)
    bd = AssetClass("Bonds", 0.03, 0.06, 0.03, 0.001, -0.15)
    regs = [Regime("Bear", -0.22, 1.9, 0.55, [0.50, 0.45, 0.05]),
            Regime("Normal", 0.0, 1.0, 0.0, [0.10, 0.80, 0.10]),
            Regime("Bull", 0.08, 0.8, 0.0, [0.04, 0.26, 0.70])]
    P = np.array([r.trans for r in regs])
    pi = stationary_distribution(P)
    check("stationary distribution sums to 1", close(float(pi.sum()), 1.0, 1e-12))
    check("expected bear duration is 1/(1-p)",
          close(float(expected_durations(P)[0]), 2.0, 1e-9))

    sp = MarketSpec(mode="mc", assets=[eq, bd], corr=[[1, 0.15], [0.15, 1]],
                    regimes=regs, crash=CrashSpec(),
                    inflation=InflationSpec(mode="stochastic"))
    m = MarketModel(sp)
    out = m.generate(trials, 40, 31337)
    occ = np.bincount(out["regime"].ravel(), minlength=3) / out["regime"].size
    check("regime occupancy matches the stationary mix",
          np.abs(occ - pi).max() < 0.01, f"{occ} vs {pi}")
    cr = out["crash"]
    freq = float((cr > 0).mean())
    check("crash frequency matches lambda", abs(freq - 0.04) < 0.004, f"{freq:.4f}")
    check("crash depth mean matches the triangular mean",
          abs(cr[cr > 0].mean() - (0.20 + 0.35 + 0.60) / 3) < 0.005)
    em = m.effective_moments(seed=99, n=min(8000, trials), T=40)
    check("calibration holds the stated mean return",
          abs(em["mean"][0] - 0.07) < 0.004, f"{em['mean'][0]:.4f}")
    check("regimes and crashes raise realised volatility above the input",
          em["sd"][0] > 0.17)
    check("bonds gain in a crash (negative beta works)",
          float(np.corrcoef(out["returns"][:, :, 0].ravel(),
                            out["returns"][:, :, 1].ravel())[0, 1]) < 0.9)
    check("inflation mean is on target",
          abs(out["inflation"].mean() - 0.025) < 0.002)

    sp2 = MarketSpec(mode="mc", assets=[eq, bd], corr=[[1, 0.15], [0.15, 1]],
                     regimes=[Regime("N", 0, 1, 0, [1.0])],
                     crash=CrashSpec(enabled=False),
                     inflation=InflationSpec(mode="fixed", mean=0.0))
    r2 = MarketModel(sp2).generate(trials, 40, 5)["returns"]
    check("without regimes, realised volatility matches the input",
          abs(r2[:, :, 0].std() - 0.17) < 0.004, f"{r2[:, :, 0].std():.4f}")
    check("without regimes, realised correlation matches the input",
          abs(np.corrcoef(r2[:, :, 0].ravel(), r2[:, :, 1].ravel())[0, 1] - 0.15) < 0.01)
    p0 = 1e6
    med = p0 * np.exp(np.log1p(0.07) - 0.5 * np.log1p((0.17 / 1.07) ** 2) * 1) ** 1
    grown = p0 * np.prod(1 + r2[:, :20, 0], axis=1)
    theory = p0 * np.exp(20 * (np.log1p(0.07) - 0.5 * np.log1p((0.17 / 1.07) ** 2)))
    check("median terminal wealth matches the lognormal closed form",
          abs(np.median(grown) / theory - 1) < 0.03,
          f"{np.median(grown):,.0f} vs {theory:,.0f}")


def test_convergence():
    print("\nsimulation convergence")
    p = simple_plan(45000, 1e6, 0.06, 0.02, 30, 1.0, ([0, 20000], [0.0, 0.25]))
    p.market.mode = "mc"
    p.market.assets[0].sigma = 0.16
    vals = []
    for n in (1000, 4000, 16000):
        r = Projection(p).run(n, seed=8)
        k = kpis(r, 0.0)
        vals.append(k["success_probability"])
        check(f"standard error shrinks with {n} trials",
              k["success_se"] < 0.02 if n >= 4000 else True)
    check("success probability is stable as trials grow",
          abs(vals[-1] - vals[-2]) < 0.03, f"{vals}")


def main():
    slow = "--slow" in sys.argv
    t0 = time.time()
    test_rng(); test_tax(); test_amortisation()
    test_golden(); test_policies(); test_determinism()
    test_serialisation(); test_edges(); test_solvers()
    test_convergence()
    test_market_statistics(200000 if slow else 40000)
    dt = time.time() - t0
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed in {dt:.1f}s")
    for f in FAIL:
        print("  FAILED:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
