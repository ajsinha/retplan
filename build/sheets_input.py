"""Input sheets: the guided data-entry surface.

Every scalar input follows the same eight-column anatomy required by FR-UX-1
(item, value, unit, allowed range, default, status, help), and every table has
pre-formatted, pre-validated blank rows so a user never has to insert one
(FR-UX-8).
"""
from __future__ import annotations

import theme
import unohelp as U
from spec import ENUMS, SH, N_ASSET, N_BAND, N_REGIME, N_SMILE, N_MRD

# scalar sheet column layout
C_LABEL, C_VALUE, C_UNIT, C_RANGE, C_DEF, C_STAT, C_HELP = range(7)
ROW0 = 4


def _fmt_for(ctx, kind):
    return {"money": ctx.fmt["money"], "pct": ctx.fmt["pct2"], "num": ctx.fmt["num"],
            "int": ctx.fmt["int"], "age": ctx.fmt["age"]}.get(kind)


def build_lists(ctx):
    """Hidden sheet holding every enumeration, so no literal list is hard-coded."""
    sh = ctx.sheet(SH["lists"])
    U.put(sh, 0, 0, "Lookup lists - do not edit unless you are extending the model",
          style="rp_title")
    col = 0
    for name, values in ENUMS.items():
        U.put(sh, col, 2, name, style="rp_h2")
        for i, v in enumerate(values):
            U.put(sh, col, 3 + i, v, style="rp_calc")
        ctx.name(f"LST_{name}", SH["lists"], col, 3, col, 3 + len(values) - 1)
        col += 1
    sh.IsVisible = False
    return sh


def scalar_sheet(ctx, key, title, subtitle, rows):
    sh = ctx.sheet(SH[key])
    U.put(sh, 0, 0, title, style="rp_title")
    U.put(sh, 0, 1, subtitle, style="rp_note")
    hdr = ["Item", "Value", "Unit", "Allowed", "Default", "Status", "What it does"]
    for i, h in enumerate(hdr):
        U.put(sh, i, 3, h, style="rp_hdrcol")
    widths = [7200, 3200, 2600, 3400, 2600, 2600, 16000]
    for i, w in enumerate(widths):
        sh.Columns.getByIndex(i).Width = w
    sh.Rows.getByIndex(3).Height = 700

    r = ROW0
    for item in rows:
        k, label, default, kind, unit, lo, hi, help_ = item
        if k == "header":
            U.put(sh, 0, r, label, style="rp_h1")
            for c in range(1, 7):
                U.put(sh, c, r, "", style="rp_h1")
            r += 2
            continue
        U.put(sh, C_LABEL, r, label, style="rp_label")
        vcell = U.put(sh, C_VALUE, r, default,
                      style="rp_list" if str(kind).startswith("list") else "rp_input",
                      fmt=_fmt_for(ctx, kind))
        U.put(sh, C_UNIT, r, unit or "", style="rp_note")
        U.put(sh, C_DEF, r, default, style="rp_calc", fmt=_fmt_for(ctx, kind))
        U.put(sh, C_HELP, r, help_ or "", style="rp_note")
        vaddr = U.a1(C_VALUE, r)
        if str(kind).startswith("list"):
            enum = kind.split(":")[1]
            src = ctx.ref(f"LST_{enum}")
            U.validate_list(sh, C_VALUE, r, C_VALUE, r, src, label, help_ or "")
            U.put(sh, C_RANGE, r, " / ".join(ENUMS[enum][:4]) +
                  ("..." if len(ENUMS[enum]) > 4 else ""), style="rp_note")
            U.put(sh, C_STAT, r,
                  f'=IF(COUNTIF({src},{vaddr})=0,"INVALID","OK")', style="rp_calc")
        elif kind == "text":
            U.put(sh, C_RANGE, r, "text", style="rp_note")
            U.put(sh, C_STAT, r, f'=IF({vaddr}="","MISSING","OK")', style="rp_calc")
        else:
            lo_ = -1e15 if lo is None else lo
            hi_ = 1e15 if hi is None else hi
            U.validate_number(sh, C_VALUE, r, C_VALUE, r, lo_, hi_,
                              whole=(kind == "int"), help_title=label,
                              help_text=help_ or "", warn_only=True)
            shown = (f"{lo:g} to {hi:g}" if lo is not None and hi is not None else "any")
            if kind == "pct" and lo is not None:
                shown = f"{lo:.0%} to {hi:.0%}"
            U.put(sh, C_RANGE, r, shown, style="rp_note")
            U.put(sh, C_STAT, r,
                  f'=IF({vaddr}="","MISSING",IF(OR({vaddr}<{lo_},{vaddr}>{hi_}),'
                  f'"OUT OF RANGE","OK"))', style="rp_calc")
        ctx.name(f"IN_{k}", SH[key], C_VALUE, r)
        r += 1

    U.cond_format(sh, C_STAT, ROW0, C_STAT, r,
                  [(f'{U.a1(C_STAT, ROW0)}="OK"', "rp_good"),
                   (f'{U.a1(C_STAT, ROW0)}="MISSING"', "rp_warn"),
                   (f'{U.a1(C_STAT, ROW0)}<>"OK"', "rp_bad")],
                  base_addr=(C_STAT, ROW0))
    ctx.name(f"STAT_{key.upper()}", SH[key], C_STAT, ROW0, C_STAT, r)
    return sh, r


def table_sheet(ctx, key, title, subtitle, columns, nrows, sample=(), notes=()):
    """columns: list of dicts(header, kind, width, lo, hi, enum, help, formula, fmt)."""
    sh = ctx.sheet(SH[key])
    U.put(sh, 0, 0, title, style="rp_title")
    U.put(sh, 0, 1, subtitle, style="rp_note")
    for i, n in enumerate(notes):
        U.put(sh, 0, 2 + i, n, style="rp_note")
    hrow = 2 + max(1, len(notes))
    drow = hrow + 1
    for i, col in enumerate(columns):
        U.put(sh, i, hrow, col["header"], style="rp_hdrcol")
        sh.Columns.getByIndex(i).Width = col.get("width", 2400)
    sh.Rows.getByIndex(hrow).Height = 900

    for j in range(nrows):
        r = drow + j
        for i, col in enumerate(columns):
            kind = col["kind"]
            if kind == "calc":
                f = col["formula"].format(r=r + 1, R=r)
                U.put(sh, i, r, f, style="rp_calc", fmt=ctx.fmt.get(col.get("fmt", "num")))
                continue
            if kind == "id":
                U.put(sh, i, r, j + 1, style="rp_calc", fmt=ctx.fmt["int"])
                continue
            style = "rp_list" if col.get("enum") else "rp_input"
            U.put(sh, i, r, None, style=style, fmt=ctx.fmt.get(col.get("fmt")))
        if j % 2 == 1:
            for i in range(len(columns)):
                c = sh.getCellByPosition(i, r)
                if c.CellStyle in ("rp_input", "rp_list"):
                    pass
    # validation applied to the whole column at once
    for i, col in enumerate(columns):
        if col.get("enum"):
            src = ctx.ref(f"LST_{col['enum']}")
            U.validate_list(sh, i, drow, i, drow + nrows - 1, src,
                            col["header"], col.get("help", ""))
        elif col["kind"] in ("money", "pct", "num", "int", "age"):
            lo = col.get("lo", -1e15)
            hi = col.get("hi", 1e15)
            U.validate_number(sh, i, drow, i, drow + nrows - 1, lo, hi,
                              whole=(col["kind"] == "int"), help_title=col["header"],
                              help_text=col.get("help", ""), warn_only=True)
    # sample data
    for j, row in enumerate(sample):
        for i, v in enumerate(row):
            if v is None:
                continue
            c = sh.getCellByPosition(i, drow + j)
            if isinstance(v, str):
                c.setString(v)
            else:
                c.setValue(float(v))
    for i, col in enumerate(columns):
        nm = col.get("name")
        if nm:
            ctx.name(nm, SH[key], i, drow, i, drow + nrows - 1)
    ctx.name(f"TBL_{key.upper()}", SH[key], 0, drow, len(columns) - 1, drow + nrows - 1)
    return sh, drow
