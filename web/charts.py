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
    while v <= hi + step * 0.5:
        ticks.append(round(v, 10))
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


def _axes(f: Frame, x_ticks, y_ticks, x_fmt=None, y_fmt=None) -> str:
    """Hairline grid + axis labels. Solid, never dashed; one shade off surface."""
    x_fmt = x_fmt or (lambda v: f"{v:,.0f}")
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
    return _legend(keys) + _svg(f, "".join(parts), title, y_label)


def line_chart(years, series, title="", y_label="", highlight=None):
    """Multi-series lines on ONE axis. series: [(label, values)]."""
    if not years or not series:
        return '<p class="viz-empty">No data yet.</p>'
    f = Frame(height=300)
    f.x_lo, f.x_hi = years[0], years[-1]
    flat = [v for _, vals in series for v in vals]
    ticks_y = nice_ticks(min(min(flat), 0), max(flat))
    f.y_lo, f.y_hi = min(ticks_y), max(ticks_y)
    parts = [_axes(f, nice_ticks(f.x_lo, f.x_hi, 6), ticks_y)]
    keys = []
    for i, (label, vals) in enumerate(series):
        colour = SERIES[i % len(SERIES)]
        dim = highlight is not None and label != highlight
        parts.append(
            f'<path d="{_path([(f.x(y), f.y(v)) for y, v in zip(years, vals)])}" '
            f'class="viz-line" stroke="{colour}" fill="none" '
            f'{"stroke-opacity=\'0.35\'" if dim else ""}/>')
        keys.append((label, colour))
    return _legend(keys) + _svg(f, "".join(parts), title, y_label)


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
    return _legend(keys) + _svg(f, "".join(parts), title, y_label)


def histogram(values, title="", x_label="", bins=28):
    """Distribution of an outcome. One series, so no legend - the title names it."""
    vals = [v for v in values if v is not None and math.isfinite(v)]
    if not vals:
        return '<p class="viz-empty">No data yet.</p>'
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
    parts = [_axes(f, nice_ticks(lo, hi, 5), ticks_y)]
    bw = f.plot_w / bins
    for i, c in enumerate(counts):
        if c <= 0:
            continue
        x = f.pad_left + i * bw
        y = f.y(c)
        h = f.y(0) - y
        parts.append(f'<rect class="viz-bar" x="{x + 1:.1f}" y="{y:.1f}" '
                     f'width="{max(1.0, bw - 2):.1f}" height="{h:.1f}" '
                     f'rx="2" fill="{SERIES[0]}"/>')
    return _svg(f, "".join(parts), title, x_label)


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
