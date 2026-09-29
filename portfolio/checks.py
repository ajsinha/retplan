"""Portfolio checks ("X-ray") and rebalancing against target weights.

Each check is a small rule that returns a severity (ok / warn / bad / info), a
one-line title and a plain-language explanation of *why it matters*. They are
prompts to look, not advice: a 60% position in a total-market fund is not the
same risk as 60% in one company, which is why single stocks and funds are
judged differently.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from datetime import date

from .assets import CLASSES
from .repository import Valuation

FUND_TYPES = {"ETF", "MUTUALFUND", "INDEX", "MONEYMARKET"}


def run_checks(val: Valuation, securities: dict[str, dict]) -> list[dict]:
    out = []

    def add(sev, title, detail):
        out.append(dict(severity=sev, title=title, detail=detail))

    if not val.positions:
        return out
    total = val.total or 1.0

    # -- prices
    if val.unpriced:
        add("bad", f"{len(val.unpriced)} holding(s) have no price",
            f"{', '.join(val.unpriced)} could not be priced, so they count as zero in "
            "every total and projection. Check the symbol, or press Refresh prices.")
    if val.fx_missing:
        add("bad", "Exchange rates missing",
            f"No rate yet for {', '.join(val.fx_missing)} into {val.currency}; those "
            "holdings are shown unconverted. Press Refresh prices.")
    if val.as_of:
        age = (date.today() - date.fromisoformat(val.as_of)).days
        if age > 5:
            add("warn", f"Prices are {age} days old",
                "The daily collector has not run recently. It runs on a schedule while "
                "RetPlan is running; you can also refresh now.")

    # -- concentration
    # only what Yahoo says is a single company; an unpriced symbol is unknown
    single = [(p, p.weight) for p in val.positions
              if not p.is_cash and (securities.get(p.symbol, {}).get("quote_type") or "")
              .upper() == "EQUITY"]
    agg: dict[str, float] = {}
    for p, w in single:
        agg[p.symbol] = agg.get(p.symbol, 0.0) + w
    big = sorted(((s, w) for s, w in agg.items() if w > 0.10), key=lambda r: -r[1])
    if big:
        worst = big[0][1]
        add("bad" if worst > 0.25 else "warn",
            f"Concentrated in {len(big)} single compan{'y' if len(big) == 1 else 'ies'}",
            ", ".join(f"{s} {w:.0%}" for s, w in big) + " of the portfolio. One "
            "company's bad news can do lasting damage; a fund spreads that risk.")
    else:
        add("ok", "No single company above 10%",
            "Company-specific risk is spread across holdings or funds.")

    by_class: dict[str, float] = {}
    for p in val.positions:
        by_class[p.asset_class] = by_class.get(p.asset_class, 0.0) + p.value / total
    eq = sum(by_class.get(k, 0.0) for k in ("equity", "intl_equity", "em_equity"))
    cash = by_class.get("cash", 0.0)
    if cash > 0.25:
        add("warn", f"{cash:.0%} in cash",
            "Cash is safe from markets but not from inflation. Over ten years or more, "
            "a large cash share usually loses purchasing power - fine if it is an "
            "emergency fund or money needed soon.")
    if by_class.get("crypto", 0.0) > 0.10:
        add("warn", f"{by_class['crypto']:.0%} in crypto",
            "Crypto has fallen more than 70% several times. Size it so that a fall "
            "like that would not change your plans.")
    intl = by_class.get("intl_equity", 0.0) + by_class.get("em_equity", 0.0)
    if eq > 0.3 and intl / eq < 0.15:
        add("info", "Little international diversification",
            f"{intl / eq if eq else 0:.0%} of your shares are outside your home market. "
            "Many long-run investors hold 20-40% abroad; home bias is a choice worth "
            "making on purpose.")
    add("info", f"{eq:.0%} shares, {1 - eq:.0%} everything else",
        "Roughly: more shares means more growth and deeper falls. A 60/40 mix fell "
        "about 20-30% in 2008; an all-share portfolio about 50%.")

    # -- bookkeeping
    no_basis = [p.symbol for p in val.positions if p.cost_basis is None and not p.is_cash]
    if no_basis:
        add("info", f"{len(no_basis)} holding(s) without a cost basis",
            "Gains can't be shown for " + ", ".join(no_basis[:6])
            + ("…" if len(no_basis) > 6 else "") + ". Add what you paid to see them.")
    other = [p.symbol for p in val.positions if p.asset_class == "other"]
    if other:
        add("info", "Some holdings are unclassified",
            f"{', '.join(other)} are 'Other', which projects with a generic assumption. "
            "Set the asset class so the projection uses the right one.")
    order = {"bad": 0, "warn": 1, "info": 2, "ok": 3}
    return sorted(out, key=lambda c: order[c["severity"]])


def rebalance(val: Valuation, targets: dict[str, float], new_money: float = 0.0,
              band: float = 0.05) -> dict:
    """Trades, by asset class, that bring the portfolio to ``targets``.

    ``new_money`` (positive to invest, negative to withdraw) is included, and a
    "cash-flow only" plan is also offered: direct new money to the underweight
    classes first so nothing need be sold - the tax-friendly way to rebalance.
    """
    targets = {k: float(v) for k, v in targets.items() if k in CLASSES and v and v > 0}
    tsum = sum(targets.values())
    if tsum <= 0:
        return dict(rows=[], total=val.total, ok=False)
    targets = {k: v / tsum for k, v in targets.items()}
    now: dict[str, float] = {}
    for p in val.positions:
        now[p.asset_class] = now.get(p.asset_class, 0.0) + p.value
    total_after = val.total + new_money
    keys = sorted(set(now) | set(targets), key=lambda k: -targets.get(k, 0.0))
    rows = []
    for k in keys:
        cur = now.get(k, 0.0)
        cw = cur / val.total if val.total else 0.0
        tw = targets.get(k, 0.0)
        rows.append(dict(key=k, label=CLASSES.get(k, CLASSES["other"])["label"],
                         value=cur, weight=cw, target=tw, drift=cw - tw,
                         trade=tw * total_after - cur,
                         out_of_band=abs(cw - tw) > band))
    # cash-flow only: fill the gaps in proportion, never selling
    if new_money > 0:
        gaps = {r["key"]: max(0.0, r["trade"]) for r in rows}
        g = sum(gaps.values())
        for r in rows:
            r["cashflow_trade"] = (new_money * gaps[r["key"]] / g) if g > 0 else \
                new_money * r["target"]
    return dict(rows=rows, total=val.total, total_after=total_after, ok=True, band=band,
                needs=any(r["out_of_band"] for r in rows))
