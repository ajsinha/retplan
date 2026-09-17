#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "build"))
import unohelp as U
from inspect_ods import open_doc

path, k = sys.argv[1], int(sys.argv[2])
filt = sys.argv[3] if len(sys.argv) > 3 else ""
doc = open_doc(path); doc.calculateAll()
sh = doc.Sheets.getByName("Eng-Core")
HDR, DATA = 11, 12
cur = sh.createCursor(); cur.gotoEndOfUsedArea(False)
ncol = cur.RangeAddress.EndColumn
for c in range(ncol + 1):
    h = sh.getCellByPosition(c, HDR).getString()
    g = sh.getCellByPosition(c, HDR - 1).getString()
    cell = sh.getCellByPosition(c, DATA + k)
    label = f"{g}|{h}"
    if filt and filt.lower() not in label.lower():
        continue
    v = cell.getValue() if cell.getError() == 0 else float("nan")
    print(f"{U.a1(c,DATA+k):>6} {label:48s} {v:16,.4f}   {cell.getFormula()[:80]}")
doc.close(False)
