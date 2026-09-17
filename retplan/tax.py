"""Generic progressive tax engine with exact, non-iterative gross-up.

No jurisdiction is hard-coded: a Schedule is just a table of band lower bounds
and marginal rates, plus an optional allowance, allowance taper and cap.  The
same class expresses a flat tax (one band), a progressive income tax, a capital
gains schedule, or a social contribution with a ceiling.

The gross-up in :meth:`Schedule.gross_up` is the piece that matters most: the
naive way to answer "how much must I withdraw to spend X after tax?" is a
circular reference, which spreadsheets solve iteratively and non-deterministically.
Because a stacked progressive tax is piecewise linear and strictly increasing in
gross income, it can be inverted exactly in one pass instead.  See
docs/04-math-and-simulation.md section 10.2.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

BIG = 1e18


@dataclass
class Schedule:
    label: str = "ordinary"
    lowers: list = field(default_factory=lambda: [0.0])   # band lower bounds, ascending
    rates: list = field(default_factory=lambda: [0.0])    # marginal rate above each bound
    allowance: float = 0.0
    taper_start: float = BIG      # allowance withdrawn above this income
    taper_rate: float = 0.0       # allowance lost per unit of income above the start
    cap: float = BIG              # maximum tax payable under this schedule

    def __post_init__(self):
        self.L = np.asarray(self.lowers, dtype=float)
        self.R = np.asarray(self.rates, dtype=float)
        if self.L[0] != 0.0:
            raise ValueError(f"{self.label}: first band lower bound must be 0")
        if np.any(np.diff(self.L) <= 0):
            raise ValueError(f"{self.label}: band bounds must strictly ascend")
        if np.any(self.R < 0) or np.any(self.R > 1):
            raise ValueError(f"{self.label}: rates must lie in [0, 1]")
        self.U = np.append(self.L[1:], BIG)
        # Cumulative tax at each band's lower bound - a constant vector, which is
        # what makes the inversion a lookup rather than a search.
        widths = self.U - self.L
        self.CT = np.concatenate([[0.0], np.cumsum(self.R[:-1] * widths[:-1])])

    # -- forward direction ------------------------------------------------
    def effective_allowance(self, gross):
        gross = np.asarray(gross, dtype=float)
        lost = np.maximum(0.0, gross - self.taper_start) * self.taper_rate
        return np.maximum(0.0, self.allowance - lost)

    def taxable(self, gross):
        gross = np.asarray(gross, dtype=float)
        return np.maximum(0.0, gross - self.effective_allowance(gross))

    def tax_on_taxable(self, x):
        """Tax due on an amount already net of allowances."""
        x = np.maximum(0.0, np.asarray(x, dtype=float))[..., None]
        slices = np.clip(x - self.L, 0.0, self.U - self.L)
        return np.minimum((slices * self.R).sum(axis=-1), self.cap)

    def tax(self, gross):
        return self.tax_on_taxable(self.taxable(gross))

    def marginal_rate(self, x):
        idx = np.clip(np.searchsorted(self.L, np.asarray(x, dtype=float), side="right") - 1,
                      0, len(self.R) - 1)
        return self.R[idx]

    # -- inverse direction ------------------------------------------------
    def gross_up(self, need_net, x0, taxable_fraction=1.0):
        """Gross withdrawal `g` such that `g - extra_tax(g) == need_net`.

        `x0` is the taxable income already stacked below this withdrawal, so the
        tranche is taxed at the correct *marginal* rates rather than an average.
        `taxable_fraction` is the share of the withdrawal that is taxable at all
        (a 25% tax-free lump sum is f = 0.75; a tax-free wrapper is f = 0).
        """
        need = np.maximum(0.0, np.asarray(need_net, dtype=float))
        x0 = np.maximum(0.0, np.broadcast_to(np.asarray(x0, dtype=float), need.shape))
        f = np.broadcast_to(np.asarray(taxable_fraction, dtype=float), need.shape)

        out = need.copy()                       # f == 0 -> no tax, gross == net
        live = f > 1e-12
        if not np.any(live):
            return out

        nd, x0l, fl = need[live], x0[live], f[live]
        tax_x0 = self.tax_on_taxable(x0l)

        # Net achievable when taxable income reaches each band bound above x0.
        bounds = self.L[None, :]                              # (1, m)
        above = bounds > x0l[:, None]
        n_at = (bounds - x0l[:, None]) / fl[:, None] - (self.CT[None, :] - tax_x0[:, None])
        reach = above & (n_at <= nd[:, None])

        b0 = np.clip(np.searchsorted(self.L, x0l, side="right") - 1, 0, len(self.R) - 1)
        k = reach.sum(axis=1)
        istar = np.clip(b0 + k, 0, len(self.R) - 1)

        anchor = np.where(k == 0, x0l, self.L[istar])
        net_at_anchor = np.where(k == 0, 0.0, np.take_along_axis(n_at, istar[:, None], 1)[:, 0])
        slope = 1.0 / fl - self.R[istar]
        slope = np.where(slope <= 1e-12, 1e-12, slope)        # guard a 100% band

        y = anchor + (nd - net_at_anchor) / slope             # taxable income reached
        out[live] = np.maximum(0.0, (y - x0l) / fl)
        return out


@dataclass
class TaxSystem:
    """A household's schedules plus the stacking order of income categories."""
    ordinary: Schedule = field(default_factory=Schedule)
    capital: Schedule = field(default_factory=Schedule)
    surtax_rate: float = 0.0
    surtax_threshold: float = BIG
    cg_inclusion: float = 1.0
    """Share of a realised gain that enters taxable income.  1.0 taxes gains at
    ordinary rates, 0.5 is a half-inclusion system, 0.0 exempts them entirely.
    A separate flat gains rate is expressed by putting the account in a wrapper
    with a fixed withdrawal taxable fraction instead."""
    index_bands: bool = True

    def indexed(self, price_level: float) -> "TaxSystem":
        """Bands indexed to inflation, or frozen so fiscal drag emerges."""
        if not self.index_bands or abs(price_level - 1.0) < 1e-15:
            return self
        s = price_level

        def scale(sc: Schedule) -> Schedule:
            return Schedule(sc.label, list(np.asarray(sc.lowers) * s), list(sc.rates),
                            sc.allowance * s,
                            sc.taper_start * s if sc.taper_start < BIG else BIG,
                            sc.taper_rate, sc.cap * s if sc.cap < BIG else BIG)

        return TaxSystem(scale(self.ordinary), scale(self.capital), self.surtax_rate,
                         self.surtax_threshold * s if self.surtax_threshold < BIG else BIG,
                         self.cg_inclusion, self.index_bands)

    def income_tax(self, ordinary_income, realised_gain=0.0):
        """Total tax on a stack of ordinary income plus an included gain."""
        total = np.asarray(ordinary_income, dtype=float) + \
            np.asarray(realised_gain, dtype=float) * self.cg_inclusion
        sur = np.maximum(0.0, total - self.surtax_threshold)
        return self.ordinary.tax(total) + sur * self.surtax_rate
