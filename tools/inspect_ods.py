#!/usr/bin/env python3
"""Open a built workbook headless, recalculate, and report errors and key values."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "build"))
import uno
import unohelp as U


def open_doc_ctx(path, port=U.PORT):
    """Open a document and keep the REMOTE component context.

    Services must be created in soffice's own context; creating them from the
    client context instantiates a second, half-initialised copy in this process
    and segfaults the bridge.
    """
    U.start_office(port)
    ctx, desktop = U.connect(port)
    url = uno.systemPathToFileUrl(os.path.abspath(path))
    return ctx, desktop.loadComponentFromURL(url, "_blank", 0, U.pv(Hidden=True))


def open_doc(path, port=U.PORT):
    return open_doc_ctx(path, port)[1]


def scan_errors(doc, limit=25):
    """Any cell showing an error value is a defect (NFR-6)."""
    bad = []
    for i in range(doc.Sheets.Count):
        sh = doc.Sheets.getByIndex(i)
        cur = sh.createCursor()
        cur.gotoEndOfUsedArea(False)
        ra = cur.RangeAddress
        rng = sh.getCellRangeByPosition(0, 0, ra.EndColumn, ra.EndRow)
        for r in range(ra.EndRow + 1):
            for c in range(ra.EndColumn + 1):
                cell = rng.getCellByPosition(c, r)
                if cell.getError() != 0:
                    bad.append((sh.Name, U.a1(c, r), cell.getError(), cell.getFormula()[:90]))
                    if len(bad) >= limit:
                        return bad
    return bad


def named(doc, name, idx=None):
    nr = doc.NamedRanges.getByName(name)
    ref = nr.ReferredCells
    if idx is None:
        return ref
    return ref.getCellByPosition(0, idx) if ref.Rows.Count > 1 else \
        ref.getCellByPosition(idx, 0)


def col_values(doc, name, n=None):
    ref = doc.NamedRanges.getByName(name).ReferredCells
    data = ref.getDataArray()
    if ref.Columns.Count == 1:
        vals = [row[0] for row in data]
    else:
        vals = list(data[0])
    return vals[:n] if n else vals


if __name__ == "__main__":
    path = sys.argv[1]
    doc = open_doc(path)
    doc.calculateAll()
    errs = scan_errors(doc)
    print(f"sheets: {[doc.Sheets.getByIndex(i).Name for i in range(doc.Sheets.Count)]}")
    print(f"error cells: {len(errs)}")
    for e in errs[:20]:
        print("   ", e)
    for nm in ("ENGC_INC", "ENGC_ESS", "ENGC_DISC", "ENGC_SPEND", "ENGC_TAXINC",
               "ENGC_NEED", "ENGC_WDTOT", "ENGC_TAXTOT", "ENGC_PORTOPEN",
               "ENGC_PORTCLOSE", "ENGC_NETWORTH", "ENGC_SHORTFALL", "ENGC_DEBTPAY"):
        try:
            v = col_values(doc, nm, 12)
            print(f"{nm:18s}", " ".join(f"{x:11,.0f}" if isinstance(x, float) else str(x)
                                        for x in v))
        except Exception as exc:
            print(nm, "ERR", exc)
    print("audit:", named(doc, "AUDIT_OVERALL").getString())
    doc.close(False)
