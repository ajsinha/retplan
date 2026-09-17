#!/usr/bin/env python3
"""TR-4: prove the workbook's formulas and the Python engine agree exactly."""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "build"))
sys.path.insert(0, os.path.join(HERE, ".."))

import numpy as np
from inspect_ods import col_values, open_doc

from retplan.engine import Projection
from retplan.reader import read_plan

# The engine reports income including forced draws, and spending including debt
# service; the sheet keeps those on separate columns, so sum them to compare.
PAIRS = [
    ("income", "ENGC_INC+ENGC_MRDTOT"), ("spend", "ENGC_SPEND+ENGC_DEBTPAY"),
    ("tax", "ENGC_TAXTOT"),
    ("withdrawal+mrd", "ENGC_WDTOT"), ("contribution", "ENGC_CONTRTOT"),
    ("fees", "ENGC_FEETOT"), ("balance", "ENGC_PORTOPEN"),
    ("shortfall", "ENGC_SHORTFALL"), ("net_worth", "ENGC_NETWORTH"),
]


def main(path, tol=1e-9):
    doc = open_doc(path)
    doc.calculateAll()
    plan = read_plan(doc)
    plan.market.mode = "fixed"
    res = Projection(plan).run(1)
    print(f"plan: horizon={plan.horizon} income={len(plan.income)} "
          f"expenses={len(plan.expenses)} loans={len(plan.loans)} "
          f"wrappers={len(plan.wrappers)} accounts={len(plan.ledgers)} "
          f"bands={len(plan.tax.ordinary.lowers)}")
    worst = 0.0
    fails = []
    for attr, name in PAIRS:
        sheet = None
        for part in name.split("+"):
            vec = np.array([v if isinstance(v, float) else 0.0
                            for v in col_values(doc, part)], dtype=float)
            sheet = vec if sheet is None else sheet + vec
        py = None
        for a in attr.split("+"):
            v = getattr(res, a)[0]
            py = v if py is None else py + v
        n = min(len(sheet), len(py))
        a, b = sheet[:n], py[:n]
        scale = np.maximum(1.0, np.abs(b))
        rel = np.abs(a - b) / scale
        worst = max(worst, rel.max())
        flag = "OK " if rel.max() < tol else "FAIL"
        if rel.max() >= tol:
            k = int(rel.argmax())
            fails.append((name, k, a[k], b[k]))
        print(f"  {flag} {name:20s} max rel diff {rel.max():.2e}   "
              f"worst at k={int(rel.argmax())}")
    print(f"\nworst relative difference overall: {worst:.3e}  "
          f"({'PASS' if worst < tol else 'FAIL'})")
    for name, k, a, b in fails:
        print(f"   {name} k={k}: sheet={a:,.6f} python={b:,.6f} diff={a-b:,.6f}")
    doc.close(False)
    return 0 if worst < tol else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
