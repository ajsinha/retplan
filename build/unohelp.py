"""Thin, well-behaved wrapper over the UNO API for building a Calc document.

Everything the workbook builder needs - cells, styles, named ranges, validation,
conditional formatting, charts and macro-bound buttons - goes through here, so
the layout code stays readable and the UNO incantations live in one place.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time

import uno
from com.sun.star.beans import PropertyValue
from com.sun.star.awt import Rectangle
from com.sun.star.table import BorderLine2
from com.sun.star.table.CellHoriJustify import LEFT, CENTER, RIGHT
from com.sun.star.sheet.ValidationType import LIST, DECIMAL, WHOLE
from com.sun.star.sheet.ValidationAlertStyle import STOP, WARNING, INFO
from com.sun.star.sheet.ConditionOperator import GREATER, LESS, EQUAL, BETWEEN, FORMULA
from com.sun.star.script import ScriptEventDescriptor

PORT = 2103
SOFFICE = shutil.which("soffice") or "/usr/bin/soffice"


def _port_open(port, host="127.0.0.1"):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) == 0


def start_office(port=PORT, profile=None):
    """Start a private headless soffice instance and return once it answers."""
    if _port_open(port):
        return None
    prof = profile or f"/tmp/claude-1000/retplan-lo-profile-{port}"
    os.makedirs(prof, exist_ok=True)
    cmd = [SOFFICE, "--headless", "--invisible", "--nologo", "--nodefault",
           "--norestore", "--nolockcheck",
           f"-env:UserInstallation=file://{prof}",
           f"--accept=socket,host=127.0.0.1,port={port};urp;"]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        if _port_open(port):
            return proc
        time.sleep(0.5)
    raise RuntimeError("soffice did not start")


def connect(port=PORT):
    ctx = uno.getComponentContext()
    resolver = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", ctx)
    last = None
    for _ in range(40):
        try:
            rc = resolver.resolve(
                f"uno:socket,host=127.0.0.1,port={port};urp;StarOffice.ComponentContext")
            return rc, rc.ServiceManager.createInstanceWithContext(
                "com.sun.star.frame.Desktop", rc)
        except Exception as exc:                       # bridge not up yet
            last = exc
            time.sleep(0.5)
    raise RuntimeError(f"cannot connect to soffice: {last}")


def pv(**kw):
    out = []
    for k, v in kw.items():
        p = PropertyValue()
        p.Name, p.Value = k, v
        out.append(p)
    return tuple(out)


def new_calc(desktop):
    return desktop.loadComponentFromURL("private:factory/scalc", "_blank", 0,
                                        pv(Hidden=True))


def save_as(doc, path, fmt="calc8"):
    url = uno.systemPathToFileUrl(os.path.abspath(path))
    doc.storeToURL(url, pv(FilterName=fmt, Overwrite=True))
    return path


# ---------------------------------------------------------------- sheets
def sheet(doc, name, index=None):
    sheets = doc.Sheets
    if not sheets.hasByName(name):
        sheets.insertNewByName(name, index if index is not None else sheets.Count)
    return sheets.getByName(name)


def cell(sh, col, row):
    return sh.getCellByPosition(col, row)


def put(sh, col, row, value, style=None, fmt=None, formula=False):
    c = sh.getCellByPosition(col, row)
    if value is None:
        pass
    elif formula or (isinstance(value, str) and value.startswith("=")):
        c.setFormula(value)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        c.setValue(float(value))
    else:
        c.setString(str(value))
    if style:
        c.CellStyle = style
    if fmt is not None:
        c.NumberFormat = fmt
    return c


def put_row(sh, col, row, values, style=None, fmt=None):
    for i, v in enumerate(values):
        put(sh, col + i, row, v, style=style, fmt=fmt)


def rng(sh, c1, r1, c2, r2):
    return sh.getCellRangeByPosition(c1, r1, c2, r2)


def addr(sh_name, col, row, abs_col=True, abs_row=True):
    """A1-style address, sheet-qualified, for use inside generated formulas.

    The sheet name is always single-quoted: names like "In-Income" otherwise
    parse as a subtraction and every reference to them silently becomes #NAME?.
    """
    s = ""
    c = col
    while True:
        s = chr(ord("A") + c % 26) + s
        c = c // 26 - 1
        if c < 0:
            break
    return (f"$'{sh_name}'.{'$' if abs_col else ''}{s}"
            f"{'$' if abs_row else ''}{row + 1}")


def a1(col, row, abs_col=False, abs_row=False):
    s = ""
    c = col
    while True:
        s = chr(ord("A") + c % 26) + s
        c = c // 26 - 1
        if c < 0:
            break
    return f"{'$' if abs_col else ''}{s}{'$' if abs_row else ''}{row + 1}"


# ---------------------------------------------------------------- formats
def number_format(doc, code, locale=None):
    fmts = doc.NumberFormats
    loc = locale or uno.createUnoStruct("com.sun.star.lang.Locale")
    key = fmts.queryKey(code, loc, False)
    if key == -1:
        key = fmts.addNew(code, loc)
    return key


def make_style(doc, name, **props):
    styles = doc.StyleFamilies.getByName("CellStyles")
    if styles.hasByName(name):
        st = styles.getByName(name)
    else:
        st = doc.createInstance("com.sun.star.style.CellStyle")
        styles.insertByName(name, st)
    for k, v in props.items():
        try:
            st.setPropertyValue(k, v)
        except Exception:
            pass
    return st


def border(width=26, color=0xBBBBBB):
    b = BorderLine2()
    b.Color = color
    b.LineWidth = width
    b.OuterLineWidth = width
    return b


# ---------------------------------------------------------------- names
def add_name(doc, name, sh_name, c1, r1, c2=None, r2=None):
    c2 = c1 if c2 is None else c2
    r2 = r1 if r2 is None else r2
    content = (f"{addr(sh_name, c1, r1)}:{addr(sh_name, c2, r2)}"
               if (c1, r1) != (c2, r2) else addr(sh_name, c1, r1))
    names = doc.NamedRanges
    if names.hasByName(name):
        names.removeByName(name)
    pos = uno.createUnoStruct("com.sun.star.table.CellAddress")
    pos.Sheet, pos.Column, pos.Row = 0, 0, 0
    names.addNewByName(name, content, pos, 0)
    return name


# ---------------------------------------------------------------- validation
def validate_list(sh, c1, r1, c2, r2, source_formula, help_title="", help_text=""):
    r = rng(sh, c1, r1, c2, r2)
    v = r.Validation
    v.Type = LIST
    v.ShowErrorMessage = True
    v.ErrorAlertStyle = STOP
    v.ErrorTitle = "Not a valid choice"
    v.ErrorMessage = "Pick one of the listed values."
    v.ShowInputMessage = bool(help_text)
    v.InputTitle = help_title
    v.InputMessage = help_text
    v.setFormula1(source_formula)
    r.Validation = v


def validate_number(sh, c1, r1, c2, r2, lo, hi, whole=False, help_title="", help_text="",
                    warn_only=False):
    r = rng(sh, c1, r1, c2, r2)
    v = r.Validation
    v.Type = WHOLE if whole else DECIMAL
    v.Operator = BETWEEN
    v.ShowErrorMessage = True
    v.ErrorAlertStyle = WARNING if warn_only else STOP
    v.ErrorTitle = "Outside the allowed range"
    v.ErrorMessage = f"Enter a value between {lo} and {hi}."
    v.ShowInputMessage = bool(help_text)
    v.InputTitle = help_title
    v.InputMessage = help_text
    v.setFormula1(str(lo))
    v.setFormula2(str(hi))
    r.Validation = v


# ------------------------------------------------------- conditional format
def cond_format(sh, c1, r1, c2, r2, rules, base_addr=None):
    """rules: list of (formula, style_name).  Formula is relative to base_addr."""
    r = rng(sh, c1, r1, c2, r2)
    cf = r.ConditionalFormat
    cf.clear()
    src = uno.createUnoStruct("com.sun.star.table.CellAddress")
    src.Sheet = sh.RangeAddress.Sheet
    src.Column, src.Row = (base_addr or (c1, r1))
    for formula, style in rules:
        cf.addNew(pv(Operator=FORMULA, Formula1=formula, StyleName=style,
                     SourcePosition=src))
    r.ConditionalFormat = cf


# ---------------------------------------------------------------- charts
def add_chart(doc, sh, name, x, y, w, h, ranges, col_headers=True, row_headers=True,
              diagram="com.sun.star.chart.LineDiagram", title=None, subtitle=None,
              stacked=False, deep=False, percent=False, symbols=False, lines=True):
    charts = sh.Charts
    rect = Rectangle()
    rect.X, rect.Y, rect.Width, rect.Height = x, y, w, h
    addrs = []
    for spec in ranges:
        # (c1, r1, c2, r2) reads from this sheet; a 5-tuple names the source sheet,
        # which is how a chart on the Dashboard plots data held elsewhere.
        if len(spec) == 5:
            src, c1, r1, c2, r2 = spec
        else:
            src, (c1, r1, c2, r2) = sh.RangeAddress.Sheet, spec
        ra = uno.createUnoStruct("com.sun.star.table.CellRangeAddress")
        ra.Sheet = src
        ra.StartColumn, ra.StartRow, ra.EndColumn, ra.EndRow = c1, r1, c2, r2
        addrs.append(ra)
    if charts.hasByName(name):
        charts.removeByName(name)
    charts.addNewByName(name, rect, tuple(addrs), col_headers, row_headers)
    ch = charts.getByName(name).EmbeddedObject
    ch.Diagram = ch.createInstance(diagram)
    if title is not None:
        ch.HasMainTitle = True
        ch.Title.String = title
    if subtitle is not None:
        ch.HasSubTitle = True
        ch.SubTitle.String = subtitle
    d = ch.Diagram
    for prop, val in (("Stacked", stacked), ("Deep", deep), ("Percent", percent),
                      ("SymbolType", 0 if symbols else -3), ("Lines", lines)):
        try:
            d.setPropertyValue(prop, val)
        except Exception:
            pass
    try:
        ch.HasLegend = True
        d.getYAxis().setPropertyValue("TextRotation", 0)
    except Exception:
        pass
    return ch


def style_series(ch, colors, transparent_first=False):
    """Apply the colour-blind-safe palette; optionally hide the fan chart's base."""
    d = ch.Diagram
    i = 0
    while True:
        try:
            row = d.getDataRowProperties(i)
        except Exception:
            break
        try:
            if transparent_first and i == 0:
                row.setPropertyValue("FillStyle", uno.Enum(
                    "com.sun.star.drawing.FillStyle", "NONE"))
                row.setPropertyValue("LineStyle", uno.Enum(
                    "com.sun.star.drawing.LineStyle", "NONE"))
            else:
                col = colors[(i - (1 if transparent_first else 0)) % len(colors)]
                row.setPropertyValue("FillColor", col)
                row.setPropertyValue("LineColor", col)
        except Exception:
            pass
        i += 1
        if i > 40:
            break


# ---------------------------------------------------------------- buttons
def add_button(doc, sh, label, x, y, w, h, script, name=None, tooltip=""):
    """A push button on the sheet bound to a user-level Python macro."""
    dp = sh.DrawPage
    forms = dp.Forms
    if forms.Count == 0:
        f = doc.createInstance("com.sun.star.form.component.Form")
        forms.insertByName("RetPlan", f)
    form = forms.getByIndex(0)
    model = doc.createInstance("com.sun.star.form.component.CommandButton")
    model.Label = label
    model.Name = name or label.replace(" ", "_")
    model.HelpText = tooltip
    form.insertByIndex(form.Count, model)
    shape = doc.createInstance("com.sun.star.drawing.ControlShape")
    size = uno.createUnoStruct("com.sun.star.awt.Size")
    size.Width, size.Height = w, h
    pos = uno.createUnoStruct("com.sun.star.awt.Point")
    pos.X, pos.Y = x, y
    shape.setSize(size)
    shape.setPosition(pos)
    shape.Control = model
    dp.add(shape)
    ev = ScriptEventDescriptor()
    ev.ListenerType = "XActionListener"
    ev.EventMethod = "actionPerformed"
    ev.ScriptType = "Script"
    ev.ScriptCode = script
    idx = form.Count - 1
    form.registerScriptEvent(idx, ev)
    return model
