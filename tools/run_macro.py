#!/usr/bin/env python3
"""Invoke a RetPlan macro against a workbook, headless - used by the test harness."""
from __future__ import annotations

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "build"))
import unohelp as U
from inspect_ods import open_doc_ctx

URL = "vnd.sun.star.script:retplan_macros.py${fn}?language=Python&location=user"


def invoke(ctx, doc, fn):
    """Resolve the user-location script through a document-scoped provider.

    `ctx` must be soffice's own context, so the provider - and the macro - run
    inside LibreOffice rather than in this process.
    """
    factory = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.script.provider.MasterScriptProviderFactory", ctx)
    provider = factory.createScriptProvider(doc)
    script = provider.getScript(URL.format(fn=fn))
    return script.invoke((), (), ())


if __name__ == "__main__":
    path, fn = sys.argv[1], sys.argv[2]
    save = len(sys.argv) > 3
    ctx, doc = open_doc_ctx(path)
    doc.calculateAll()
    t0 = time.time()
    invoke(ctx, doc, fn)
    doc.calculateAll()
    print(f"{fn} finished in {time.time() - t0:.1f}s")
    print("status :", doc.NamedRanges.getByName("SIM_STATUS").ReferredCells
          .getCellByPosition(0, 0).getString())
    print("stale  :", doc.NamedRanges.getByName("SIM_STALE").ReferredCells
          .getCellByPosition(0, 0).getString())
    for k in ("SIMK_TRIALS", "SIMK_SUCCESS", "SIMK_SE", "SIMK_TERM50",
              "SIMK_DEPAGE50", "SIMK_DD", "SIMK_MAXSPEND", "SIMK_SWR",
              "SIMK_EARLIEST", "SIMK_REQSAVE", "SIMK_SECONDS"):
        v = doc.NamedRanges.getByName(k).ReferredCells.getCellByPosition(0, 0).getValue()
        print(f"  {k:16s} {v:,.4f}")
    band = doc.NamedRanges.getByName("SIMP_NW").ReferredCells.getDataArray()
    print("  net worth P10/P50/P90 at year 30:",
          [f"{band[30][i]:,.0f}" for i in (1, 3, 5)])
    if save:
        U.save_as(doc, path)
    doc.close(False)
