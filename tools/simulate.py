#!/usr/bin/env python3
"""Run the simulation against a workbook from outside LibreOffice.

The in-document buttons need the `libreoffice-script-provider-python` package.
This runner needs only `python3-uno`, which is what ships with LibreOffice, so
it always works:

    python3 tools/simulate.py RetPlan.ods --trials 10000 --full

It drives exactly the same code the buttons drive, so the results are identical.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "build"))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import unohelp as U
from inspect_ods import open_doc_ctx


def _macros():
    spec = importlib.util.spec_from_file_location(
        "retplan_macros", os.path.join(ROOT, "macros", "retplan_macros.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


KPIS = ["SIMK_TRIALS", "SIMK_SUCCESS", "SIMK_SE", "SIMK_TERM5", "SIMK_TERM50",
        "SIMK_TERM95", "SIMK_DEPAGE50", "SIMK_DD", "SIMK_MAXSPEND", "SIMK_SWR",
        "SIMK_EARLIEST", "SIMK_REQSAVE", "SIMK_SECONDS"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workbook")
    ap.add_argument("--trials", type=int, default=None)
    ap.add_argument("--full", action="store_true",
                    help="also run the solvers, spending sweep and tornado")
    ap.add_argument("--no-save", action="store_true")
    a = ap.parse_args()

    m = _macros()
    _, doc = open_doc_ctx(a.workbook)
    doc.calculateAll()
    t0 = time.time()
    auto = doc.isAutomaticCalculationEnabled()
    doc.enableAutomaticCalculation(False)
    try:
        m._simulate(doc, trials=a.trials, with_extras=a.full)
    finally:
        doc.enableAutomaticCalculation(auto)
        doc.calculateAll()

    get = lambda n: doc.NamedRanges.getByName(n).ReferredCells \
        .getCellByPosition(0, 0).getValue()
    txt = lambda n: doc.NamedRanges.getByName(n).ReferredCells \
        .getCellByPosition(0, 0).getString()
    print(f"status : {txt('SIM_STATUS')}")
    print(f"results: {txt('SIM_STALE')}")
    for k in KPIS:
        print(f"  {k:16s} {get(k):>16,.4f}")
    if not a.no_save:
        U.save_as(doc, a.workbook)
        print(f"saved   {a.workbook}")
    print(f"wall clock {time.time() - t0:.1f}s")
    doc.close(False)


if __name__ == "__main__":
    main()
