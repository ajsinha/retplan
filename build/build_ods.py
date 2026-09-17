#!/usr/bin/env python3
"""Build RetPlan.ods from source.

Run:  python3 build/build_ods.py [-o RetPlan.ods]

Nothing in the delivered file is hand-edited: the workbook is a build artefact,
so a rebuild from the same source produces the same file (CR-16).
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sheets_engine
import sheets_input as SI
import sheets_misc as SM
import sheets_output as SO
import spec
import tables
import theme
import unohelp as U
from context import Ctx
from spec import (N_ASSET, N_EXPENSE, N_INCOME, N_LEDGER, N_LOAN, N_WRAPPER, SH, T)

VERSION = "1.0.0"


def _calc_cols(ctx, sh_key, columns, calc, nrows, drow, refs):
    """Append the derived helper columns a table needs, and register their names."""
    sh = ctx.sheet(SH[sh_key])
    base = len(columns)
    for i, (name, tmpl, fmt) in enumerate(calc):
        col = base + i
        U.put(sh, col, drow - 1, name.split("_", 1)[1], style="rp_hdrcol")
        sh.Columns.getByIndex(col).Width = 1700
        letter = U.a1(col, 0).rstrip("1")
        for j in range(nrows):
            r = drow + j
            sub = dict(refs)
            sub["r"] = r + 1
            U.put(sh, col, r, tmpl.format(**sub), style="rp_calc",
                  fmt=ctx.fmt.get(fmt))
        ctx.name(name, SH[sh_key], col, drow, col, drow + nrows - 1)
        refs[name.split("_", 1)[1].lower()] = letter
    return base + len(calc)


def build(path):
    proc = U.start_office()
    ctx_uno, desktop = U.connect()
    doc = U.new_calc(desktop)
    ctx = Ctx(doc=doc).setup()
    t0 = time.time()

    # remove the default sheet once ours exist
    default = doc.Sheets.getByIndex(0).Name

    SI.build_lists(ctx)
    SI.scalar_sheet(ctx, "house", "Household", "Who the plan covers and how results "
                    "are presented.", spec.HOUSEHOLD)
    SI.scalar_sheet(ctx, "policy", "Spending and withdrawal policy",
                    "How much you take out, how it flexes, and what counts as success.",
                    spec.POLICY)
    mk_sh, _ = SI.scalar_sheet(ctx, "market", "Markets, inflation and fees",
                               "Assumptions about returns, inflation, costs, crashes "
                               "and market regimes.", spec.MARKETS)
    tx_sh, _ = SI.scalar_sheet(ctx, "tax", "Tax system",
                               "Nothing here is country-specific: it is all just bands.",
                               spec.TAXCFG)

    # --- tables -------------------------------------------------------------
    inc_cols, inc_calc = tables.income_columns()
    _, inc_drow = SI.table_sheet(ctx, "income", "Income",
                                 "Every stream of money coming in, for either person.",
                                 inc_cols, N_INCOME, tables.INCOME_SAMPLE,
                                 notes=["Amounts are per year and gross of tax. "
                                        "'real' basis keeps pace with inflation."])
    refs = {"en": 1, "own": 3, "cat": 4, "amt": 5, "bas": 6, "g": 7, "gf": 8,
            "a0": 9, "a1": 10, "txf": 11, "sv": 12, "prob": 13}
    refs = {k: U.a1(v, 0).rstrip("1") for k, v in refs.items()}
    refs["catlist"] = "LST_CATEGORY"
    _calc_cols(ctx, "income", inc_cols, inc_calc, N_INCOME, inc_drow, refs)

    exp_cols, exp_calc = tables.expense_columns()
    _, exp_drow = SI.table_sheet(ctx, "expense", "Spending",
                                 "What the money is for. Essential rows form a floor "
                                 "that no flexible policy may cut.",
                                 exp_cols, N_EXPENSE, tables.EXPENSE_SAMPLE)
    refs = {k: U.a1(v, 0).rstrip("1") for k, v in
            {"en": 1, "amt": 3, "bas": 4, "ess": 5, "d": 6, "sm": 7, "a0": 8,
             "a1": 9, "rec": 10, "own": 11, "prob": 12}.items()}
    _calc_cols(ctx, "expense", exp_cols, exp_calc, N_EXPENSE, exp_drow, refs)

    ln_cols, ln_calc = tables.loan_columns()
    _, ln_drow = SI.table_sheet(ctx, "debt", "Debt",
                                "Mortgages and loans, amortised year by year.",
                                ln_cols, N_LOAN, tables.LOAN_SAMPLE)
    refs = {k: U.a1(v, 0).rstrip("1") for k, v in
            {"en": 1, "bal": 3, "rate": 4, "n": 5, "kind": 6, "ex": 7, "st": 8}.items()}
    _calc_cols(ctx, "debt", ln_cols, ln_calc, N_LOAN, ln_drow, refs)

    wr_cols, _ = tables.wrapper_columns()
    SI.table_sheet(ctx, "wrap", "Tax wrappers",
                   "The generic part of the model. A wrapper says when money is taxed: "
                   "going in, while it grows, or coming out.",
                   wr_cols, N_WRAPPER, tables.WRAPPER_SAMPLE,
                   notes=["EET, TEE, TTE and ETT are all just settings of these columns.",
                          "Add a wrapper by filling a blank row - no formula changes."])

    lg_cols, lg_calc = tables.ledger_columns()
    _, lg_drow = SI.table_sheet(ctx, "acct", "Accounts",
                                "Balances and how they are invested. Each account "
                                "points at a wrapper for its tax treatment.",
                                lg_cols, N_LEDGER, tables.LEDGER_SAMPLE)
    wcols = {f"w{i+1}": 7 + i for i in range(N_ASSET)}
    vcols = {f"v{i+1}": 7 + N_ASSET + i for i in range(N_ASSET)}
    base = {"en": 1, "own": 3, "wr": 4, "open": 5, "basis": 6}
    base.update(wcols)
    base.update(vcols)
    refs = {k: U.a1(v, 0).rstrip("1") for k, v in base.items()}
    _calc_cols(ctx, "acct", lg_cols, lg_calc, N_LEDGER, lg_drow, refs)

    SM.markets_tables(ctx, mk_sh, 42)
    SM.tax_tables(ctx, tx_sh, 18)
    SM.lookup_tables(ctx)
    SM.debt_sheet(ctx)

    sheets_engine.build(ctx)

    SO.readme(ctx, VERSION)
    SO.start_here(ctx)
    SO.scenarios(ctx)
    SO.sim_control(ctx)
    SO.sim_paths(ctx)
    SO.sim_results(ctx)
    SO.chart_data(ctx)
    dash, next_row = SO.dashboard(ctx)
    SO.reports(ctx)
    SO.audit(ctx)
    SO.charts_and_controls(ctx, dash, next_row)

    if doc.Sheets.hasByName(default):
        doc.Sheets.removeByName(default)
    doc.calculateAll()
    U.save_as(doc, path)
    elapsed = time.time() - t0
    print(f"built {path} in {elapsed:.1f}s  "
          f"sheets={doc.Sheets.Count} names={doc.NamedRanges.ElementNames.__len__()}")
    return doc


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="RetPlan.ods")
    a = ap.parse_args()
    d = build(a.out)
    d.close(False)
