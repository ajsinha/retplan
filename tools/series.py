#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "build"))
from inspect_ods import open_doc, col_values
path = sys.argv[1]; lo = int(sys.argv[2]); hi = int(sys.argv[3])
names = sys.argv[4].split(",")
doc = open_doc(path); doc.calculateAll()
print("k   " + "".join(f"{n.replace('ENGC_',''):>14}" for n in names))
cols = {n: col_values(doc, n) for n in names}
for k in range(lo, hi):
    print(f"{k:<4}" + "".join(f"{cols[n][k]:14,.0f}" if isinstance(cols[n][k], float)
                              else f"{str(cols[n][k]):>14}" for n in names))
print("max |recon| =", max(abs(v) for v in col_values(doc, "ENGC_RECON")))
doc.close(False)
