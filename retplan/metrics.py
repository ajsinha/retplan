"""Key metrics, percentile bands and reconciliation checks."""
from __future__ import annotations

import numpy as np

from .engine import Results

PCTS = [5, 10, 25, 50, 75, 90, 95]


def kpis(res: Results, legacy_target=0.0, confidence=0.85):
    """Headline numbers, including the honest error bar on success probability."""
    ok = res.success(legacy_target)
    n = len(ok)
    p = float(ok.mean())
    se = float(np.sqrt(max(p * (1 - p), 1e-12) / max(n, 1)))
    dep = res.depleted_period
    failed = dep[dep >= 0]
    term = res.terminal
    dd = drawdown(res)
    return {
        "trials": n,
        "success_probability": p,
        "success_se": se,
        "success_ci95": (max(0.0, p - 1.96 * se), min(1.0, p + 1.96 * se)),
        "trials_for_1pct": int(np.ceil(1.96 ** 2 * max(p * (1 - p), 0.01) / 0.01 ** 2)),
        "terminal_real_p5": float(np.percentile(term, 5)),
        "terminal_real_p50": float(np.percentile(term, 50)),
        "terminal_real_p95": float(np.percentile(term, 95)),
        "terminal_real_mean": float(term.mean()),
        "depletion_age_p10": (float(res.ages[int(np.percentile(failed, 10))])
                              if failed.size else float("nan")),
        "depletion_age_p50": (float(res.ages[int(np.percentile(failed, 50))])
                              if failed.size else float("nan")),
        "failure_rate": float((dep >= 0).mean()),
        "worst_drawdown": float(dd.min()),
        "median_drawdown": float(np.median(dd)),
        "total_real_spend_p50": float(np.percentile(res.spend.sum(axis=1), 50)),
        "total_shortfall_p50": float(np.percentile(res.shortfall.sum(axis=1), 50)),
        "total_tax_p50": float(np.percentile(res.tax.sum(axis=1), 50)),
        "confidence": confidence,
    }


def drawdown(res: Results):
    """Worst peak-to-trough fall in real net worth, per trial."""
    nw = res.net_worth
    peak = np.maximum.accumulate(np.maximum(nw, 1e-9), axis=1)
    return (nw / peak - 1.0).min(axis=1)


def bands(arr, pcts=PCTS):
    """Percentile bands over trials -> (len(pcts), T+1)."""
    return np.percentile(arr, pcts, axis=0)


def funded_ratio(res: Results, discount_rate=0.03):
    """PV(assets + future non-portfolio income) / PV(future spending), real."""
    T = res.spend.shape[1]
    d = (1.0 + discount_rate) ** -np.arange(T)
    pv_spend = (res.spend * d).sum(axis=1)
    pv_income = (res.income * d).sum(axis=1)
    return (res.balance[:, 0] + pv_income) / np.maximum(pv_spend, 1e-9)


def reconcile(res: Results, tol=1e-6):
    """Sources = uses, period by period.

    closing = opening + contributions - withdrawals - fees + return
    The return is inferred from the reported rate, so a mismatch means a flow was
    dropped somewhere rather than that the arithmetic of one line is wrong.
    """
    b = res.balance
    open_, close = b[:, :-1], b[:, 1:]
    flow = (open_ - res.withdrawal[:, :-1] - res.mrd[:, :-1]
            + res.contribution[:, :-1] - res.fees[:, :-1])
    implied = flow * (1.0 + res.ret_rate[:, :-1])
    err = np.abs(close - implied)
    scale = np.maximum(1.0, np.abs(close))
    rel = err / scale
    return {"max_abs_error": float(err.max()), "max_rel_error": float(rel.max()),
            "pass": bool(rel.max() < tol)}


def summarise_paths(res: Results):
    """Everything the charts need, in one place."""
    return {
        "net_worth": bands(res.net_worth),
        "spend": bands(res.spend),
        "tax": bands(res.tax),
        "income": bands(res.income),
        "withdrawal": bands(res.withdrawal),
        "wrapper_median": np.percentile(res.balance_by_wrapper, 50, axis=0),
        "ages": res.ages,
    }
