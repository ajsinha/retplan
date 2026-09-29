"""Server-rendered SVG charts.

No charting library and no CDN: every figure is an inline ``<svg>`` built here,
so the app renders identically offline and the markup is inspectable. Colours are
emitted as ``var(--viz-*)`` custom properties rather than literal hex, so the
light and dark palettes swap with the theme without re-rendering anything.

Design rules applied throughout (and why):
  - one y-axis, never two - a second scale invents a correlation that is not in
    the data;
  - hairline solid gridlines, 2px marks, generous padding;
  - a 2px surface gap between stacked fills instead of a border around them;
  - a legend whenever there are two or more series, plus selective direct labels
    on the endpoint that matters - never a number on every point;
  - every chart ships a table-view twin in the template, so no value is
    reachable only by hovering.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import html
import math
from dataclasses import dataclass, field

# Categorical slots, validated for CVD separation against both app surfaces.
SERIES = [f"var(--viz-{i})" for i in range(1, 9)]
# Sequential blue ramp, light -> dark, for magnitude and confidence bands.
SEQ = [f"var(--viz-seq-{s})" for s in (150, 250, 350, 450, 550, 650)]


def _e(text) -> str:
    return html.escape(str(text), quote=True)


def nice_ticks(lo: float, hi: float, count: int = 5):
    """Round axis ticks a human would have chosen."""
    if not math.isfinite(lo) or not math.isfinite(hi):
        return [0.0, 1.0]
    if hi - lo < 1e-9:
        hi = lo + 1.0
    raw = (hi - lo) / max(1, count)
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    for mult in (1, 2, 2.5, 5, 10):
        if raw / mag <= mult:
            step = mult * mag
            break
    else:
        step = 10 * mag
    start = math.floor(lo / step) * step
    ticks, v = [], start
    # keep going until a tick covers the maximum, so no mark rises above the grid
    while not ticks or ticks[-1] < hi - 1e-9 * max(1.0, abs(hi)):
        ticks.append(round(v, 10) + 0.0)          # + 0.0 turns -0.0 into 0.0
        v += step
    return ticks


@dataclass
class Frame:
    """Plot geometry. The container includes the axis band, so nothing clips."""
    width: int = 720
    height: int = 320
    pad_left: int = 62
    pad_right: int = 18
    pad_top: int = 14
    pad_bottom: int = 34
    x_lo: float = 0.0
    x_hi: float = 1.0
    y_lo: float = 0.0
    y_hi: float = 1.0

    @property
    def plot_w(self):
        return self.width - self.pad_left - self.pad_right

    @property
    def plot_h(self):
        return self.height - self.pad_top - self.pad_bottom

    def x(self, v):
        span = (self.x_hi - self.x_lo) or 1.0
        return self.pad_left + (v - self.x_lo) / span * self.plot_w

    def y(self, v):
        span = (self.y_hi - self.y_lo) or 1.0
        return self.pad_top + (1 - (v - self.y_lo) / span) * self.plot_h


def _fmt_compact(v):
    a = abs(v)
    sign = "-" if v < 0 else ""
    for cut, suf in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if a >= cut:
            t = f"{a / cut:.1f}".rstrip("0").rstrip(".")
            return f"{sign}{t}{suf}"
    return f"{sign}{a:,.0f}"


def _fmt_x(v):
    """Calendar years without a thousands separator; everything else with one."""
    if 1800 <= v <= 2400 and abs(v - round(v)) < 1e-9:
        return f"{v:.0f}"
    return _fmt_compact(v) if abs(v) >= 10000 else f"{v:,.0f}"


def _pct_fmt(v):
    return f"{v * 100:.0f}%"


def _axes(f: Frame, x_ticks, y_ticks, x_fmt=None, y_fmt=None) -> str:
    """Hairline grid + axis labels. Solid, never dashed; one shade off surface."""
    x_fmt = x_fmt or _fmt_x
    y_fmt = y_fmt or _fmt_compact
    out = []
    for t in y_ticks:
        if not (f.y_lo - 1e-9 <= t <= f.y_hi + 1e-9):
            continue
        y = f.y(t)
        out.append(f'<line class="viz-grid" x1="{f.pad_left:.1f}" y1="{y:.1f}" '
                   f'x2="{f.width - f.pad_right:.1f}" y2="{y:.1f}"/>')
        out.append(f'<text class="viz-tick viz-tick-y" x="{f.pad_left - 8:.1f}" '
                   f'y="{y + 3.5:.1f}" text-anchor="end">{_e(y_fmt(t))}</text>')
    for t in x_ticks:
        if not (f.x_lo - 1e-9 <= t <= f.x_hi + 1e-9):
            continue
        x = f.x(t)
        out.append(f'<text class="viz-tick" x="{x:.1f}" '
                   f'y="{f.height - f.pad_bottom + 18:.1f}" '
                   f'text-anchor="middle">{_e(x_fmt(t))}</text>')
    out.append(f'<line class="viz-axis" x1="{f.pad_left:.1f}" '
               f'y1="{f.height - f.pad_bottom:.1f}" '
               f'x2="{f.width - f.pad_right:.1f}" '
               f'y2="{f.height - f.pad_bottom:.1f}"/>')
    return "".join(out)


def _svg(f: Frame, body: str, title: str, desc: str = "") -> str:
    return (f'<svg class="viz" viewBox="0 0 {f.width} {f.height}" '
            f'preserveAspectRatio="xMidYMid meet" role="img" '
            f'aria-label="{_e(title)}">'
            f'<title>{_e(title)}</title>'
            + (f'<desc>{_e(desc)}</desc>' if desc else "")
            + body + '</svg>')


def _path(points) -> str:
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in points)


def _legend(items) -> str:
    """items: [(label, colour)]. Identity is never carried by colour alone."""
    if len(items) < 2:
        return ""
    cells = "".join(
        f'<span class="viz-key"><span class="viz-swatch" '
        f'style="background:{c}"></span>{_e(l)}</span>' for l, c in items)
    return f'<div class="viz-legend">{cells}</div>'


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
def fan_chart(years, bands, median, title="", y_label="", deterministic=None):
    """Percentile bands as nested areas of ONE hue - confidence is magnitude.

    `bands` is a list of (lower, upper) series ordered outermost first.
    """
    if not years:
        return '<p class="viz-empty">No data yet.</p>'
    f = Frame(height=340)
    f.x_lo, f.x_hi = years[0], years[-1]
    hi = max([max(u) for _, u in bands] + ([max(deterministic)] if deterministic else [0]))
    lo = min([min(l) for l, _ in bands] + [0])
    ticks_y = nice_ticks(lo, hi)
    f.y_lo, f.y_hi = min(ticks_y), max(ticks_y)

    parts = [_axes(f, nice_ticks(f.x_lo, f.x_hi, 6), ticks_y)]
    shades = [SEQ[1], SEQ[2], SEQ[3]]
    for i, (low, up) in enumerate(bands):
        top = [(f.x(y), f.y(v)) for y, v in zip(years, up)]
        bot = [(f.x(y), f.y(v)) for y, v in zip(years, low)][::-1]
        d = _path(top) + " L" + " L".join(f"{x:.1f},{y:.1f}" for x, y in bot) + " Z"
        parts.append(f'<path d="{d}" fill="{shades[i % len(shades)]}" '
                     f'fill-opacity="{0.55 if i else 0.40}" stroke="none"/>')
    parts.append(f'<path d="{_path([(f.x(y), f.y(v)) for y, v in zip(years, median)])}" '
                 f'class="viz-line" stroke="{SEQ[5]}" fill="none"/>')
    if deterministic:
        parts.append(
            f'<path d="{_path([(f.x(y), f.y(v)) for y, v in zip(years, deterministic)])}" '
            f'class="viz-line viz-line-alt" stroke="{SERIES[1]}" fill="none"/>')
    # Selective direct label: the endpoint of the median, the value people quote.
    parts.append(f'<text class="viz-label" x="{f.x(years[-1]) - 4:.1f}" '
                 f'y="{f.y(median[-1]) - 8:.1f}" text-anchor="end">'
                 f'{_e(_fmt_compact(median[-1]))}</text>')
    keys = [("Median outcome", SEQ[5]), ("Middle 50%", SEQ[3]),
            ("Middle 80%", SEQ[2]), ("Full 5-95% range", SEQ[1])]
    if deterministic:
        keys.append(("Deterministic projection", SERIES[1]))
    names = ["P5-P95", "P10-P90", "P25-P75"]
    tips = []
    for i, y in enumerate(years):
        rows = [f"Year {_fmt_x(y)}", f"Median {_fmt_compact(median[i])}"]
        rows += [f"{names[k] if k < 3 else 'band'}: {_fmt_compact(lo[i])} to {_fmt_compact(up[i])}"
                 for k, (lo, up) in enumerate(bands)]
        tips.append("\n".join(rows))
    parts.append(_crosshair(f) + _hover(f, years, tips))
    return (_legend(keys) + '<div class="viz-wrap">' + _svg(f, "".join(parts), title, y_label)
            + '</div>')


def line_chart(years, series, title="", y_label="", highlight=None, y_fmt=None,
               x_name="Year"):
    """Multi-series lines on ONE axis. series: [(label, values)]."""
    if not years or not series:
        return '<p class="viz-empty">No data yet.</p>'
    y_fmt = y_fmt or _fmt_compact
    f = Frame(height=300)
    f.x_lo, f.x_hi = years[0], years[-1]
    flat = [v for _, vals in series for v in vals]
    ticks_y = nice_ticks(min(min(flat), 0), max(flat))
    f.y_lo, f.y_hi = min(ticks_y), max(ticks_y)
    parts = [_axes(f, nice_ticks(f.x_lo, f.x_hi, 6), ticks_y, y_fmt=y_fmt)]
    keys = []
    for i, (label, vals) in enumerate(series):
        colour = SERIES[i % len(SERIES)]
        dim = highlight is not None and label != highlight
        parts.append(
            f'<path d="{_path([(f.x(y), f.y(v)) for y, v in zip(years, vals)])}" '
            f'class="viz-line" stroke="{colour}" fill="none" '
            f'{"stroke-opacity=\'0.35\'" if dim else ""}/>')
        keys.append((label, colour))
    tips = [f"{x_name} {_fmt_x(y)}\n" + "\n".join(f"{l}: {y_fmt(v[i])}" for l, v in series)
            for i, y in enumerate(years)]
    parts.append(_crosshair(f) + _hover(f, years, tips))
    return (_legend(keys) + '<div class="viz-wrap">' + _svg(f, "".join(parts), title, y_label)
            + '</div>')


def _crosshair(f: Frame) -> str:
    return ('<line class="viz-hover" x1="0" x2="0" '
            f'y1="{f.pad_top}" y2="{f.height - f.pad_bottom}" visibility="hidden"/>')


def stacked_area(years, series, title="", y_label=""):
    """Composition over time. A 2px surface gap separates the bands."""
    if not years or not series:
        return '<p class="viz-empty">No data yet.</p>'
    f = Frame(height=320)
    f.x_lo, f.x_hi = years[0], years[-1]
    totals = [sum(vals[i] for _, vals in series) for i in range(len(years))]
    ticks_y = nice_ticks(0, max(totals) if totals else 1)
    f.y_lo, f.y_hi = min(ticks_y), max(ticks_y)
    parts = [_axes(f, nice_ticks(f.x_lo, f.x_hi, 6), ticks_y)]
    running = [0.0] * len(years)
    keys = []
    for i, (label, vals) in enumerate(series):
        colour = SERIES[i % len(SERIES)]
        upper = [running[j] + vals[j] for j in range(len(years))]
        top = [(f.x(y), f.y(v)) for y, v in zip(years, upper)]
        bot = [(f.x(y), f.y(v)) for y, v in zip(years, running)][::-1]
        d = _path(top) + " L" + " L".join(f"{x:.1f},{y:.1f}" for x, y in bot) + " Z"
        parts.append(f'<path d="{d}" fill="{colour}" fill-opacity="0.85" '
                     f'class="viz-band"/>')
        running = upper
        keys.append((label, colour))
    tips = [f"Year {_fmt_x(y)}\n" + "\n".join(f"{l}: {_fmt_compact(v[i])}" for l, v in series)
            + f"\nTotal: {_fmt_compact(totals[i])}" for i, y in enumerate(years)]
    parts.append(_crosshair(f) + _hover(f, years, tips))
    return (_legend(keys) + '<div class="viz-wrap">' + _svg(f, "".join(parts), title, y_label)
            + '</div>')


def histogram(values, title="", x_label="", bins=28):
    """Distribution of an outcome. One series, so no legend - the title names it."""
    vals = [v for v in values if v is not None and math.isfinite(v)]
    if not vals:
        return '<p class="viz-empty">No data yet.</p>'
    # A long right tail would squash everything into one bar: show up to the
    # 99th percentile and say so, rather than let one outlier set the scale.
    ordered = sorted(vals)
    cap = ordered[min(len(ordered) - 1, int(0.99 * len(ordered)))]
    beyond = sum(1 for v in vals if v > cap)
    vals = [min(v, cap) for v in vals]
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        hi = lo + 1.0
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in vals:
        idx = min(bins - 1, int((v - lo) / width))
        counts[idx] += 1
    f = Frame(height=300)
    f.x_lo, f.x_hi = lo, hi
    ticks_y = nice_ticks(0, max(counts))
    f.y_lo, f.y_hi = 0, max(ticks_y)
    parts = [_axes(f, nice_ticks(lo, hi, 5), ticks_y, x_fmt=_fmt_compact,
                   y_fmt=lambda v: f"{v:,.0f}")]
    bw = f.plot_w / bins
    n = len(vals)
    for i, c in enumerate(counts):
        if c <= 0:
            continue
        x = f.pad_left + i * bw
        y = f.y(c)
        h = f.y(0) - y
        a, b = lo + i * width, lo + (i + 1) * width
        tip = (f"{_fmt_compact(a)} to {_fmt_compact(b)}"
               + (" and above" if i == bins - 1 and beyond else "")
               + f"\n{c:,} trials ({c / n:.1%})")
        parts.append(f'<rect class="viz-bar" x="{x + 1:.1f}" y="{y:.1f}" '
                     f'width="{max(1.0, bw - 2):.1f}" height="{h:.1f}" '
                     f'rx="2" fill="{SERIES[0]}" data-tip="{_e(tip)}"/>')
    note = (f'<p class="small-muted mb-0">The last bar also holds the {beyond:,} '
            f'trials above {_fmt_compact(cap)} (the top 1%).</p>' if beyond else "")
    return '<div class="viz-wrap">' + _svg(f, "".join(parts), title, x_label) + '</div>' + note


def tornado(rows, title=""):
    """Driver sensitivity: one bar per driver, diverging around the base case."""
    if not rows:
        return '<p class="viz-empty">Run the full analysis to populate this.</p>'
    n = len(rows)
    f = Frame(height=60 + 34 * n, pad_left=170, pad_bottom=30, pad_top=10)
    lo = min(min(r[1], r[2]) for r in rows)
    hi = max(max(r[1], r[2]) for r in rows)
    ticks = nice_ticks(max(0.0, lo - 0.05), min(1.0, hi + 0.05), 5)
    f.y_lo, f.y_hi = 0, n
    f.x_lo, f.x_hi = min(ticks), max(ticks)
    parts = [_axes(f, ticks, [], x_fmt=lambda v: f"{v * 100:.0f}%")]
    row_h = f.plot_h / n
    for i, (label, down, up) in enumerate(rows):
        cy = f.pad_top + (i + 0.5) * row_h
        x1, x2 = f.x(min(down, up)), f.x(max(down, up))
        parts.append(f'<rect class="viz-bar" x="{x1:.1f}" y="{cy - 9:.1f}" '
                     f'width="{max(2.0, x2 - x1):.1f}" height="18" rx="4" '
                     f'fill="{SERIES[0]}" fill-opacity="0.85"/>')
        parts.append(f'<text class="viz-tick" x="{f.pad_left - 10:.1f}" '
                     f'y="{cy + 4:.1f}" text-anchor="end">{_e(label)}</text>')
        parts.append(f'<text class="viz-label" x="{x2 + 6:.1f}" y="{cy + 4:.1f}">'
                     f'{_e(f"{max(down, up) * 100:.0f}%")}</text>')
    return _svg(f, "".join(parts), title or "Driver sensitivity")


def spaghetti(years, paths, median=None, title="", y_label=""):
    """A sample of individual futures - one hue, low opacity, median on top."""
    if not years or not paths:
        return '<p class="viz-empty">No data yet.</p>'
    f = Frame(height=320)
    f.x_lo, f.x_hi = years[0], years[-1]
    flat = [v for p in paths for v in p]
    ticks_y = nice_ticks(0, max(flat) if flat else 1)
    f.y_lo, f.y_hi = 0, max(ticks_y)
    parts = [_axes(f, nice_ticks(f.x_lo, f.x_hi, 6), ticks_y)]
    for p in paths:
        parts.append(f'<path d="{_path([(f.x(y), f.y(v)) for y, v in zip(years, p)])}" '
                     f'class="viz-thread" stroke="{SEQ[3]}" fill="none"/>')
    if median:
        parts.append(
            f'<path d="{_path([(f.x(y), f.y(v)) for y, v in zip(years, median)])}" '
            f'class="viz-line" stroke="{SERIES[1]}" fill="none"/>')
    keys = [("Sampled futures", SEQ[3])] + ([("Median", SERIES[1])] if median else [])
    return _legend(keys) + _svg(f, "".join(parts), title, y_label)


# --------------------------------------------------------------------------- #
# Portfolio charts. Each carries a hover layer: one transparent column per x
# whose data-tip lists every value at that x (web/static/js/retplan.js draws the
# crosshair and tooltip). The table-view twin in the template stays the
# authoritative, keyboard-reachable copy of the numbers.
# --------------------------------------------------------------------------- #
def _hover(f: Frame, xs, tips) -> str:
    if not tips:
        return ""
    out = []
    n = len(xs)
    for i, (x, tip) in enumerate(zip(xs, tips)):
        left = f.x(xs[i - 1]) if i else f.x(x) - (f.x(xs[1]) - f.x(x) if n > 1 else 10)
        right = f.x(xs[i + 1]) if i < n - 1 else f.x(x) + (f.x(x) - f.x(xs[i - 1]) if n > 1 else 10)
        x0 = max(f.pad_left, (left + f.x(x)) / 2)
        x1 = min(f.width - f.pad_right, (f.x(x) + right) / 2)
        out.append(f'<rect class="viz-hit" x="{x0:.1f}" y="{f.pad_top}" '
                   f'width="{max(1.0, x1 - x0):.1f}" height="{f.plot_h:.1f}" '
                   f'fill="transparent" data-x="{f.x(x):.1f}" data-tip="{_e(tip)}"/>')
    return "".join(out)


def _label_ticks(xs, labels, max_ticks=8):
    """Every k-th categorical label so ticks never collide."""
    n = len(xs)
    step = max(1, math.ceil(n / max_ticks))
    return [(xs[i], labels[i]) for i in range(0, n, step)]


def _axes_labelled(f: Frame, xticks, y_ticks, y_fmt=None) -> str:
    """Like _axes, but x ticks are (position, text) pairs."""
    y_fmt = y_fmt or _fmt_compact
    out = [_axes(f, [], y_ticks, y_fmt=y_fmt)]
    for x, text in xticks:
        out.append(f'<text class="viz-tick" x="{f.x(x):.1f}" '
                   f'y="{f.height - f.pad_bottom + 18:.1f}" text-anchor="middle">'
                   f'{_e(text)}</text>')
    return "".join(out)


def projection_fan(labels, bands, median, *, start=None, expected=None, target=None,
                   tips=None, title="", desc="", y_fmt=None):
    """Portfolio value over time: P10-P90 and P25-P75 bands in one hue, the
    median as the line, the no-volatility expectation dashed, a goal as a
    reference line. ``start`` prepends today's value at x = 0."""
    if not labels:
        return '<p class="viz-empty">No data yet.</p>'
    xs = list(range(1, len(labels) + 1))
    if start is not None:
        xs = [0] + xs
        labels = ["Today"] + list(labels)
        bands = [([start] + list(lo), [start] + list(hi)) for lo, hi in bands]
        median = [start] + list(median)
        if expected:
            expected = [start] + list(expected)
        if tips:
            tips = [f"Today\nValue {_fmt_compact(start)}"] + list(tips)
    f = Frame(height=360, pad_left=64)
    f.x_lo, f.x_hi = xs[0], xs[-1]
    hi = max([max(u) for _, u in bands] + [max(median)] + ([max(expected)] if expected else [])
             + ([target] if target else []))
    ticks_y = nice_ticks(0, hi)
    f.y_lo, f.y_hi = 0, max(ticks_y)
    parts = [_axes_labelled(f, _label_ticks(xs, labels), ticks_y, y_fmt)]
    shades = [SEQ[1], SEQ[3]]
    for i, (low, up) in enumerate(bands):
        top = [(f.x(x), f.y(v)) for x, v in zip(xs, up)]
        bot = [(f.x(x), f.y(v)) for x, v in zip(xs, low)][::-1]
        d = _path(top) + " L" + " L".join(f"{x:.1f},{y:.1f}" for x, y in bot) + " Z"
        parts.append(f'<path d="{d}" fill="{shades[i % 2]}" '
                     f'fill-opacity="{0.45 if i == 0 else 0.6}" stroke="none"/>')
    if target:
        parts.append(f'<line class="viz-target" x1="{f.pad_left}" x2="{f.width - f.pad_right}" '
                     f'y1="{f.y(target):.1f}" y2="{f.y(target):.1f}"/>'
                     f'<text class="viz-tick" x="{f.pad_left + 6}" y="{f.y(target) - 5:.1f}">'
                     f'Goal {_e(_fmt_compact(target))}</text>')
    if expected:
        parts.append(f'<path d="{_path([(f.x(x), f.y(v)) for x, v in zip(xs, expected)])}" '
                     f'class="viz-line viz-line-alt" stroke="{SERIES[1]}"/>')
    parts.append(f'<path d="{_path([(f.x(x), f.y(v)) for x, v in zip(xs, median)])}" '
                 f'class="viz-line" stroke="{SEQ[5]}" stroke-width="2.5"/>')
    parts.append(f'<text class="viz-label" x="{f.x(xs[-1]) - 4:.1f}" '
                 f'y="{f.y(median[-1]) - 9:.1f}" text-anchor="end">'
                 f'Median {_e(_fmt_compact(median[-1]))}</text>')
    parts.append('<line class="viz-hover" x1="0" x2="0" '
                 f'y1="{f.pad_top}" y2="{f.height - f.pad_bottom}" visibility="hidden"/>')
    parts.append(_hover(f, xs, tips))
    keys = [("Median", SEQ[5]), ("Middle 50% (P25-P75)", SEQ[3]),
            ("Middle 80% (P10-P90)", SEQ[1])]
    if expected:
        keys.append(("Expected-return path", SERIES[1]))
    return (_legend(keys) + '<div class="viz-wrap">'
            + _svg(f, "".join(parts), title, desc) + '</div>')


def range_bars(labels, lo, mid, hi, *, tips=None, title="", desc="", pct=True):
    """Period returns: a P10-P90 bar per period with the median as a tick.
    Diverging around zero, so the zero line is drawn and labelled."""
    if not labels:
        return '<p class="viz-empty">No data yet.</p>'
    n = len(labels)
    f = Frame(height=280, pad_left=56)
    xs = list(range(n))
    f.x_lo, f.x_hi = -0.6, n - 0.4
    ticks_y = nice_ticks(min(min(lo), 0), max(max(hi), 0), 6)
    f.y_lo, f.y_hi = min(ticks_y), max(ticks_y)
    fmt = (lambda v: f"{v * 100:.0f}%") if pct else _fmt_compact
    parts = [_axes_labelled(f, _label_ticks(xs, labels, 10), ticks_y, fmt)]
    parts.append(f'<line class="viz-axis" x1="{f.pad_left}" x2="{f.width - f.pad_right}" '
                 f'y1="{f.y(0):.1f}" y2="{f.y(0):.1f}"/>')
    bw = min(26.0, f.plot_w / n * 0.62)
    for i in range(n):
        x = f.x(i)
        y1, y2 = f.y(hi[i]), f.y(lo[i])
        parts.append(f'<rect class="viz-bar" x="{x - bw / 2:.1f}" y="{y1:.1f}" '
                     f'width="{bw:.1f}" height="{max(2.0, y2 - y1):.1f}" rx="4" '
                     f'fill="{SEQ[2]}" fill-opacity="0.8"/>')
        parts.append(f'<line x1="{x - bw / 2:.1f}" x2="{x + bw / 2:.1f}" '
                     f'y1="{f.y(mid[i]):.1f}" y2="{f.y(mid[i]):.1f}" '
                     f'stroke="{SEQ[5]}" stroke-width="2.5" stroke-linecap="round"/>')
    parts.append('<line class="viz-hover" x1="0" x2="0" '
                 f'y1="{f.pad_top}" y2="{f.height - f.pad_bottom}" visibility="hidden"/>')
    parts.append(_hover(f, xs, tips))
    keys = [("Median return", SEQ[5]), ("P10-P90 range", SEQ[2])]
    return (_legend(keys) + '<div class="viz-wrap">'
            + _svg(f, "".join(parts), title, desc) + '</div>')


def binned_histogram(counts, edges, *, x_fmt=None, marker=None, marker_label="",
                     title="", desc="", unit="trials"):
    """A pre-binned distribution (the projection stores counts, not samples)."""
    if not counts or not any(counts):
        return '<p class="viz-empty">No data yet.</p>'
    x_fmt = x_fmt or _fmt_compact
    n = len(counts)
    f = Frame(height=250, pad_left=52)
    f.x_lo, f.x_hi = edges[0], edges[-1]
    ticks_y = nice_ticks(0, max(counts), 4)
    f.y_lo, f.y_hi = 0, max(ticks_y)
    xt = nice_ticks(edges[0], edges[-1], 5)
    parts = [_axes(f, [], ticks_y, y_fmt=lambda v: f"{v:,.0f}")]
    for t in xt:
        if edges[0] <= t <= edges[-1]:
            parts.append(f'<text class="viz-tick" x="{f.x(t):.1f}" '
                         f'y="{f.height - f.pad_bottom + 18:.1f}" text-anchor="middle">'
                         f'{_e(x_fmt(t))}</text>')
    total = sum(counts) or 1
    for i, c in enumerate(counts):
        if c <= 0:
            continue
        x0, x1 = f.x(edges[i]), f.x(edges[i + 1])
        y = f.y(c)
        tip = (f"{x_fmt(edges[i])} to {x_fmt(edges[i + 1])}\n"
               f"{c:,} {unit} ({c / total:.1%})")
        parts.append(f'<rect class="viz-bar" x="{x0 + 1:.1f}" y="{y:.1f}" '
                     f'width="{max(1.0, x1 - x0 - 2):.1f}" height="{f.y(0) - y:.1f}" '
                     f'rx="3" fill="{SERIES[0]}" data-tip="{_e(tip)}"/>')
    if marker is not None and edges[0] <= marker <= edges[-1]:
        x = f.x(marker)
        parts.append(f'<line class="viz-target" x1="{x:.1f}" x2="{x:.1f}" '
                     f'y1="{f.pad_top}" y2="{f.height - f.pad_bottom}"/>'
                     f'<text class="viz-label" x="{x + 5:.1f}" y="{f.pad_top + 11}">'
                     f'{_e(marker_label)}</text>')
    return '<div class="viz-wrap">' + _svg(f, "".join(parts), title, desc) + '</div>'


def date_line(dates, series, *, title="", desc="", y_fmt=None, zero_floor=False,
              height=280, reference=None, reference_label=""):
    """Daily series against dates (ISO strings). series: [(label, values)].
    Month ticks; a crosshair tooltip lists every series on the hovered day."""
    if not dates or not series or not any(len(v) for _, v in series):
        return '<p class="viz-empty">No prices stored yet.</p>'
    y_fmt = y_fmt or _fmt_compact
    n = len(dates)
    xs = list(range(n))
    f = Frame(height=height, pad_left=58)
    f.x_lo, f.x_hi = 0, max(1, n - 1)
    flat = [v for _, vals in series for v in vals if v is not None]
    lo, hi = min(flat), max(flat)
    if reference is not None:
        lo, hi = min(lo, reference), max(hi, reference)
    pad = (hi - lo) * 0.08 or abs(hi) * 0.05 or 1
    ticks_y = nice_ticks(0 if zero_floor else lo - pad, hi + pad, 5)
    f.y_lo, f.y_hi = min(ticks_y), max(ticks_y)
    # a tick at the first trading day of each month (every other if crowded)
    months, last = [], None
    for i, d in enumerate(dates):
        if d[:7] != last:
            months.append((i, d))
            last = d[:7]
    step = 1 if len(months) <= 8 else 2
    names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct",
             "Nov", "Dec"]
    xt = [(i, f"{names[int(d[5:7]) - 1]} {d[2:4]}") for i, d in months[::step]]
    parts = [_axes_labelled(f, xt, ticks_y, y_fmt)]
    if reference is not None:
        parts.append(f'<line class="viz-target" x1="{f.pad_left}" x2="{f.width - f.pad_right}" '
                     f'y1="{f.y(reference):.1f}" y2="{f.y(reference):.1f}"/>'
                     f'<text class="viz-tick" x="{f.pad_left + 6}" y="{f.y(reference) - 5:.1f}">'
                     f'{_e(reference_label)}</text>')
    keys = []
    for k, (label, vals) in enumerate(series):
        colour = SERIES[k % len(SERIES)]
        pts = [(f.x(i), f.y(v)) for i, v in zip(xs, vals) if v is not None]
        if pts:
            parts.append(f'<path d="{_path(pts)}" class="viz-line" stroke="{colour}"/>')
        keys.append((label, colour))
    tips = []
    for i, d in enumerate(dates):
        lines = [d] + [f"{label}: {y_fmt(vals[i])}" for label, vals in series
                       if i < len(vals) and vals[i] is not None]
        tips.append("\n".join(lines))
    parts.append('<line class="viz-hover" x1="0" x2="0" '
                 f'y1="{f.pad_top}" y2="{f.height - f.pad_bottom}" visibility="hidden"/>')
    parts.append(_hover(f, xs, tips))
    return (_legend(keys) + '<div class="viz-wrap">'
            + _svg(f, "".join(parts), title, desc) + '</div>')


def quarter_path(values, *, crisis_quarters=0, title="", desc="", start_label="Start"):
    """A deterministic value path by quarter, with the crisis window shaded."""
    if not values:
        return '<p class="viz-empty">No data yet.</p>'
    xs = list(range(len(values)))
    f = Frame(height=280, pad_left=60)
    f.x_lo, f.x_hi = 0, max(1, len(values) - 1)
    lo, hi = min(values), max(values)
    ticks_y = nice_ticks(lo * 0.9, hi * 1.05, 5)
    f.y_lo, f.y_hi = min(ticks_y), max(ticks_y)
    xt = [(i, f"Q{i}" if i else start_label) for i in range(0, len(values),
                                                           max(1, len(values) // 8))]
    parts = []
    if crisis_quarters:
        x0, x1 = f.x(0), f.x(min(crisis_quarters, len(values) - 1))
        parts.append(f'<rect x="{x0:.1f}" y="{f.pad_top}" width="{x1 - x0:.1f}" '
                     f'height="{f.plot_h:.1f}" fill="var(--rp-crimson-tint)"/>'
                     f'<text class="viz-tick" x="{x0 + 6:.1f}" y="{f.pad_top + 12}">'
                     f'crisis</text>')
    parts.append(_axes_labelled(f, xt, ticks_y))
    parts.append(f'<line class="viz-target" x1="{f.pad_left}" x2="{f.width - f.pad_right}" '
                 f'y1="{f.y(values[0]):.1f}" y2="{f.y(values[0]):.1f}"/>')
    parts.append(f'<path d="{_path([(f.x(i), f.y(v)) for i, v in zip(xs, values)])}" '
                 f'class="viz-line" stroke="{SERIES[0]}"/>')
    tips = [f"{'Start' if i == 0 else f'Quarter {i}'}\nValue {_fmt_compact(v)}\n"
            f"{v / values[0] - 1:+.1%} vs start" for i, v in enumerate(values)]
    parts.append('<line class="viz-hover" x1="0" x2="0" '
                 f'y1="{f.pad_top}" y2="{f.height - f.pad_bottom}" visibility="hidden"/>')
    parts.append(_hover(f, xs, tips))
    return '<div class="viz-wrap">' + _svg(f, "".join(parts), title, desc) + '</div>'


def life_timeline(plan, start_year: int) -> str:
    """The plan laid out by age: people and their retirements, every income stream,
    time-limited and recurring costs, loans until they are paid off, conversions.
    One lane per row, grouped; a tooltip on each bar; a line at today."""
    if not plan.persons:
        return '<p class="viz-empty">No household yet.</p>'
    p0 = plan.persons[0]
    a0 = float(p0.age)
    a1 = float(min(p0.age + plan.horizon, max(pp.death_age - pp.age for pp in plan.persons) + p0.age))

    def own_to_p0(age, owner):
        """An age of `owner` expressed on person 1's age axis."""
        if 0 <= owner < len(plan.persons):
            return age - plan.persons[owner].age + p0.age
        return age

    lanes = []            # (group, label, start, end, colour, tip, marker)
    for i, pp in enumerate(plan.persons):
        s, e = a0, own_to_p0(pp.death_age, i)
        r = own_to_p0(pp.retire_age, i)
        lanes.append(("People", pp.label, s, e, SEQ[1],
                      f"{pp.label}\nage {pp.age:.0f} today, retires at {pp.retire_age:.0f}, "
                      f"planned to {pp.death_age:.0f}", r))
    cat_colour = {"employment": SERIES[0], "self_employment": SERIES[0], "state_pension": SERIES[2],
                  "db_pension": SERIES[2], "annuity": SERIES[2], "rental": SERIES[3]}
    for row in plan.income:
        if not row.enabled or row.amount <= 0:
            continue
        s, e = own_to_p0(row.start_age, row.owner), own_to_p0(row.end_age, row.owner)
        lanes.append(("Income", row.label, max(a0, s), min(a1, e),
                      cat_colour.get(row.category, SERIES[6]),
                      f"{row.label}\n{row.amount:,.0f} a year ({row.basis}) from age "
                      f"{row.start_age:.0f}" + (f" to {row.end_age:.0f}" if row.end_age < 150 else ""),
                      None))
    for row in plan.expenses:
        # lifelong costs are the background, not events: only what starts later,
        # stops before the plan does, or comes round every few years
        limited = (row.end_age < p0.death_age or row.start_age > a0 + 0.5
                   or row.recur_years > 1)
        if not row.enabled or row.amount <= 0 or not limited:
            continue
        s, e = max(a0, row.start_age), min(a1, row.end_age)
        every = f", every {row.recur_years} years" if row.recur_years > 1 else ""
        lanes.append(("Costs", row.label, s, e, SERIES[1],
                      f"{row.label}\n{row.amount:,.0f}{every} from age {row.start_age:.0f}"
                      + (f" to {row.end_age:.0f}" if row.end_age < 150 else ""), None))
    for ln in plan.loans:
        if not ln.enabled or ln.balance <= 0:
            continue
        s = a0 + ln.start_year
        e = min(a1, s + ln.term_years)
        lanes.append(("Debt", ln.label, s, e, SERIES[7],
                      f"{ln.label}\n{ln.balance:,.0f} at {ln.rate:.2%}, {ln.term_years} years "
                      f"({ln.kind.replace('_', ' ')}) - paid off at age {e:.0f}", None))
    for cv in plan.conversions:
        if not cv.enabled:
            continue
        what = (f"{cv.amount:,.0f} a year" if cv.mode == "amount"
                else f"fill taxable income to {cv.amount:,.0f}")
        lanes.append(("Conversions", cv.label, max(a0, cv.start_age), min(a1, cv.end_age),
                      SERIES[6], f"{cv.label}\n{what}, age {cv.start_age:.0f} to {cv.end_age:.0f}",
                      None))
    lanes = [l for l in lanes if l[3] > l[2]]
    if not lanes:
        return '<p class="viz-empty">Nothing on the timeline yet.</p>'
    row_h, gap, top, left, right = 13, 4, 18, 190, 16
    groups = []
    for l in lanes:
        if l[0] not in groups:
            groups.append(l[0])
    height = top + (row_h + gap) * len(lanes) + 16 * len(groups) + 34
    f = Frame(width=1300, height=height, pad_left=left, pad_right=right, pad_top=top, pad_bottom=30)
    f.x_lo, f.x_hi = a0, a1
    parts = []
    ticks = nice_ticks(a0, a1, 10)
    for t in ticks:
        if a0 <= t <= a1:
            x = f.x(t)
            parts.append(f'<line class="viz-grid" x1="{x:.1f}" x2="{x:.1f}" y1="{top - 6}" '
                         f'y2="{height - 26}"/><text class="viz-tick" x="{x:.1f}" '
                         f'y="{height - 10}" text-anchor="middle">{t:.0f}'
                         f'<tspan class="viz-tick" dx="3">({start_year + int(t - a0)})</tspan></text>')
    parts.append(f'<text class="viz-tick" x="{left - 8}" y="{height - 10}" text-anchor="end">'
                 f'age of {_e(p0.label)} (year)</text>')
    y = top
    last_group = None
    for group, label, s, e, colour, tip, marker in lanes:
        if group != last_group:
            parts.append(f'<text class="viz-label" x="4" y="{y + 11}">{_e(group)}</text>')
            y += 16
            last_group = group
        x0, x1 = f.x(s), f.x(e)
        parts.append(f'<text class="viz-tick" x="{left - 8}" y="{y + row_h / 2 + 4:.1f}" '
                     f'text-anchor="end">{_e(label[:26])}</text>')
        parts.append(f'<rect class="viz-bar" x="{x0:.1f}" y="{y}" width="{max(3.0, x1 - x0):.1f}" '
                     f'height="{row_h}" rx="5" fill="{colour}" fill-opacity="0.8" '
                     f'data-tip="{_e(tip)}"/>')
        if marker is not None and a0 <= marker <= a1:
            xm = f.x(marker)
            parts.append(f'<line x1="{xm:.1f}" x2="{xm:.1f}" y1="{y - 2}" y2="{y + row_h + 2}" '
                         f'stroke="var(--viz-ink)" stroke-width="2"/>'
                         f'<text class="viz-tick" x="{xm + 4:.1f}" y="{y + row_h / 2 + 4:.1f}" '
                         f'fill="var(--viz-ink)">retires</text>')
        y += row_h + gap
    return '<div class="viz-wrap">' + _svg(f, "".join(parts), "Your plan over time",
                                           "income, costs, debt and conversions by age") + '</div>'
