"""Turns a stored projection result into the page's charts and tables.

The projection itself (portfolio.projection.simulate) returns plain JSON-able
numbers, which is what the database keeps; this module draws from them, so a
saved run re-renders exactly - including in a theme that did not exist when it
was run.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import csv
import io

from web import charts


def _money(v):
    return charts._fmt_compact(v)


def projection_view(result: dict, basis: str = "real") -> dict:
    """basis: 'real' (today's money) or 'nominal'."""
    periods = result["periods"]
    s = result["summary"]
    key = "real" if basis == "real" else "nominal"
    labels = [p["label"] for p in periods]
    b = [p[key] for p in periods]
    infl = result["settings"]["inflation"]
    expected = result.get("expected") or []
    if basis == "real":
        expected = [v / (1 + infl) ** p["years"] for v, p in zip(expected, periods)]
    tips = []
    for p, v in zip(periods, b):
        lines = [p["label"],
                 f"P90 {_money(v['p90'])} · P75 {_money(v['p75'])}",
                 f"Median {_money(v['p50'])}",
                 f"P25 {_money(v['p25'])} · P10 {_money(v['p10'])}",
                 f"Median return {p['ret']['p50'] * 100:+.1f}%"]
        if "p_target" in p:
            lines.append(f"Goal reached by now: {p['p_target']:.0%}")
        if p["p_depleted"] > 0:
            lines.append(f"Run out by now: {p['p_depleted']:.0%}")
        tips.append("\n".join(lines))
    fan = charts.projection_fan(
        labels, [([x["p10"] for x in b], [x["p90"] for x in b]),
                 ([x["p25"] for x in b], [x["p75"] for x in b])],
        [x["p50"] for x in b], start=s["start"], expected=expected or None,
        target=(s["target"] or None) if basis == "real" else None, tips=tips,
        title="Portfolio value, range of outcomes",
        desc=f"{'today' if basis == 'real' else 'future'}'s money; bands are P10-P90 "
             "and P25-P75 across all trials")
    rtips = [f"{p['label']}\nP90 {p['ret']['p90'] * 100:+.1f}%\n"
             f"Median {p['ret']['p50'] * 100:+.1f}%\nP10 {p['ret']['p10'] * 100:+.1f}%\n"
             f"Chance of a loss: {p['p_loss_period']:.0%}" for p in periods]
    returns = charts.range_bars(labels, [p["ret"]["p10"] for p in periods],
                                [p["ret"]["p50"] for p in periods],
                                [p["ret"]["p90"] for p in periods], tips=rtips,
                                title="Return in each period",
                                desc="time-weighted, after fees, P10 to P90")
    he = result["hist_end"]
    hist = charts.binned_histogram(
        he["counts"], he["edges"], marker=s["target"] or None,
        marker_label="goal" if s["target"] else "",
        title="Where the portfolio ends up", desc="final value, today's money")
    hd = result["hist_dd"]
    dd = charts.binned_histogram(
        hd["counts"], hd["edges"], x_fmt=lambda v: f"{v * 100:.0f}%",
        title="Worst fall along the way", desc="maximum peak-to-trough decline per trial")
    return dict(fan=fan, returns=returns, hist=hist, dd=dd, basis=basis, key=key)


def projection_csv(result: dict) -> str:
    """The period table, both bases, for a spreadsheet."""
    out = io.StringIO()
    w = csv.writer(out)
    has_target = any("p_target" in p for p in result["periods"])
    head = ["period", "years"]
    for basis in ("nominal", "real"):
        head += [f"{basis}_p{k}" for k in (5, 10, 25, 50, 75, 90, 95)]
    head += ["mean_nominal", "return_p10", "return_p50", "return_p90", "return_mean",
             "median_cagr_to_date", "contributions", "withdrawals_median",
             "contributions_real", "withdrawals_median_real",
             "p_loss_in_period", "p_depleted_by_end", "p_above_start_real"]
    if has_target:
        head.append("p_goal_by_end")
    w.writerow(head)
    for p in result["periods"]:
        row = [p["label"], p["years"]]
        for basis in ("nominal", "real"):
            row += [round(p[basis][f"p{k}"], 2) for k in (5, 10, 25, 50, 75, 90, 95)]
        row += [round(p["mean"], 2), round(p["ret"]["p10"], 6), round(p["ret"]["p50"], 6),
                round(p["ret"]["p90"], 6), round(p["ret_mean"], 6), round(p["cagr_p50"], 6),
                round(p["contrib"], 2), round(p["withdraw"], 2),
                round(p.get("contrib_real", 0.0), 2), round(p.get("withdraw_real", 0.0), 2),
                round(p["p_loss_period"], 4),
                round(p["p_depleted"], 4), round(p["p_above_start"], 4)]
        if has_target:
            row.append(round(p.get("p_target", 0.0), 4))
        w.writerow(row)
    return out.getvalue()
