"""The projection engine.

Two design choices carry most of the weight:

**Everything is computed in real (today's money) terms.**  Nominal figures are
produced at the end by multiplying by each trial's own realised CPI index, so a
"real" result is correct path by path rather than deflated by an average.

**Tax is handled by homogeneity rather than by re-building bands per trial.**
A progressive schedule is positively homogeneous of degree one: scaling every
band, allowance and cap by `s` gives `Tax_s(x) = s * Tax_1(x / s)`.  So indexed
bands need no adjustment in real terms (s = 1), and frozen bands - the fiscal
drag case - are handled exactly with `s = 1 / CPI_t`.  No per-trial rebuild, no
approximation.

The whole model is vectorised over trials: a single trial is just `n = 1`, which
means the deterministic projection and the Monte Carlo run identical code and
cannot drift apart.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .markets import MarketModel
from .plan import Plan

EPS = 1e-12


@dataclass
class Results:
    """Per-trial, per-period arrays.  Shape (n_trials, T+1) unless noted."""
    plan: Plan
    cpi: np.ndarray
    balance: np.ndarray          # total portfolio at the START of the period, real
    balance_close: np.ndarray    # ... and at the end, after flows and returns
    mrd: np.ndarray              # forced distributions
    balance_by_wrapper: np.ndarray   # (n, T+1, NW), real
    income: np.ndarray
    spend: np.ndarray
    tax: np.ndarray
    withdrawal: np.ndarray
    contribution: np.ndarray
    fees: np.ndarray
    ret_rate: np.ndarray
    shortfall: np.ndarray
    debt_balance: np.ndarray
    net_worth: np.ndarray
    regime: np.ndarray
    taxable_income: np.ndarray
    ages: np.ndarray             # (T+1,)

    @property
    def terminal(self):
        return self.net_worth[:, -1]

    @property
    def depleted_period(self):
        """First period with an unmet need, or -1 when the plan never fails."""
        bad = self.shortfall > 1e-6
        any_bad = bad.any(axis=1)
        first = np.argmax(bad, axis=1)
        return np.where(any_bad, first, -1)

    def success(self, legacy_target=0.0):
        return (self.depleted_period < 0) & (self.terminal >= legacy_target - 1e-6)


def _amortise(loan, T):
    """Nominal payment, interest, principal and balance vectors for one loan."""
    pay = np.zeros(T + 1)
    interest = np.zeros(T + 1)
    bal = np.zeros(T + 1)
    b = float(loan.balance)
    r = float(loan.rate)
    n = max(1, int(loan.term_years))
    if loan.kind == "amortising":
        ann = b * r / (1 - (1 + r) ** -n) if r > EPS else b / n
    elif loan.kind == "interest_only":
        ann = b * r
    else:                                   # bullet: nothing until maturity
        ann = 0.0
    for t in range(T + 1):
        bal[t] = b
        if b <= EPS or t < loan.start_year:
            continue
        i = b * r
        p = ann - i + loan.extra_payment
        if loan.kind == "interest_only":
            p = loan.extra_payment
        if t - loan.start_year >= n - 1:     # final year clears the balance
            p = b
        p = min(max(0.0, p), b)
        interest[t] = i
        pay[t] = i + p
        b -= p
    return pay, interest, bal


class Projection:
    def __init__(self, plan: Plan):
        self.plan = plan
        self.T = int(plan.horizon)
        self.NW = len(plan.wrappers)
        self.NL = len(plan.ledgers)
        self.A = len(plan.market.assets)
        self._precompute()

    # ------------------------------------------------------------------ setup
    def _precompute(self):
        p, T = self.plan, self.T
        t = np.arange(T + 1)
        self.t = t
        self.ages = np.array([[pp.age + k for k in t] for pp in p.persons])  # (P, T+1)
        self.alive = np.array([[(pp.age + k) <= pp.death_age for k in t]
                               for pp in p.persons])
        self.age = self.ages[0] if len(p.persons) else t.astype(float)
        self.retired = np.array([[(pp.age + k) >= pp.retire_age for k in t]
                                 for pp in p.persons])
        self.hh_retired = self.retired.all(axis=0) if len(p.persons) else np.ones(T + 1, bool)

        # --- income: deterministic real and nominal vectors, by taxability ----
        self.inc_real = np.zeros(T + 1)
        self.inc_nom = np.zeros(T + 1)
        self.inc_tax_real = np.zeros(T + 1)     # taxable share, real
        self.inc_tax_nom = np.zeros(T + 1)
        self.inc_by_cat = {c: np.zeros(T + 1) for c in
                           ("employment", "pension", "other", "tax_free", "one_off")}
        self.pensionable = np.zeros(T + 1)
        for row in p.income:
            if not row.enabled or row.amount == 0:
                continue
            o = min(row.owner, len(p.persons) - 1)
            a = self.ages[o]
            live = (a >= row.start_age) & (a <= row.end_age)
            surv = np.where(self.alive[o], 1.0, row.survivor_fraction)
            base = np.where(live, row.amount * row.probability * surv, 0.0)
            k = (t - np.argmax(live)) if row.grow_from_start else t
            g = (1 + row.growth) ** np.maximum(0, k)
            v = base * g
            if row.basis == "real":
                self.inc_real += v
                self.inc_tax_real += v * row.taxable_fraction
            else:
                self.inc_nom += v
                self.inc_tax_nom += v * row.taxable_fraction
            cat = ("employment" if row.category in ("employment", "self_employment")
                   else "pension" if row.category in ("db_pension", "state_pension", "annuity")
                   else "tax_free" if row.category == "tax_free"
                   else "one_off" if row.category == "one_off" else "other")
            self.inc_by_cat[cat] += v
            if row.category in ("employment", "self_employment"):
                self.pensionable += v

        # --- expenses: essential / discretionary, real and nominal -----------
        sm = np.interp(self.age, p.smile.ages, p.smile.mult)
        self.smile_mult = sm
        self.ess_real = np.zeros(T + 1)
        self.disc_real = np.zeros(T + 1)
        self.ess_nom = np.zeros(T + 1)
        self.disc_nom = np.zeros(T + 1)
        for row in p.expenses:
            if not row.enabled or row.amount == 0:
                continue
            a = self.ages[max(0, row.owner)] if row.owner >= 0 else self.age
            live = (a >= row.start_age) & (a <= row.end_age)
            if row.recur_years and row.recur_years > 0:
                first = int(np.argmax(live)) if live.any() else 0
                live = live & (((t - first) % int(row.recur_years)) == 0)
            v = np.where(live, row.amount * row.probability, 0.0)
            v = v * (1 + row.infl_delta) ** t
            if row.smile:
                v = v * sm
            if row.basis == "real":
                (self.ess_real if row.essential else self.disc_real).__iadd__(v)
            else:
                (self.ess_nom if row.essential else self.disc_nom).__iadd__(v)

        # --- debt ------------------------------------------------------------
        self.debt_pay_nom = np.zeros(T + 1)
        self.debt_int_nom = np.zeros(T + 1)
        self.debt_bal_nom = np.zeros(T + 1)
        for ln in p.loans:
            if not ln.enabled or ln.balance <= 0:
                continue
            pay, interest, bal = _amortise(ln, T)
            self.debt_pay_nom += pay
            self.debt_int_nom += interest
            self.debt_bal_nom += bal

        # --- allocation weights per ledger, per period ------------------------
        self.w = np.zeros((self.NL, T + 1, self.A))
        for i, lg in enumerate(p.ledgers):
            w0 = np.asarray(lg.weights, dtype=float)
            w0 = np.resize(w0, self.A)
            w0 = w0 / max(EPS, w0.sum())
            if lg.glide_to:
                w1 = np.resize(np.asarray(lg.glide_to, dtype=float), self.A)
                w1 = w1 / max(EPS, w1.sum())
                frac = np.clip((self.age - lg.glide_start_age)
                               / max(EPS, lg.glide_end_age - lg.glide_start_age), 0, 1)
                self.w[i] = w0[None, :] * (1 - frac)[:, None] + w1[None, :] * frac[:, None]
            else:
                self.w[i] = w0[None, :]
        self.ter = np.array([a.ter for a in p.market.assets])
        self.wrapper_of = np.array([lg.wrapper for lg in p.ledgers], dtype=int)
        self.order_wd = np.argsort([lg.withdraw_priority for lg in p.ledgers], kind="stable")
        self.order_ct = np.argsort([lg.contribute_priority for lg in p.ledgers], kind="stable")

    # --------------------------------------------------------------- helpers
    def _mrd_divisor(self, wrapper, age):
        tbl = wrapper.mrd_divisors
        if not tbl:
            return np.inf
        ages = [x[0] for x in tbl]
        divs = [x[1] for x in tbl]
        if age < ages[0]:
            return np.inf
        # Step lookup, not interpolation: published minimum-distribution tables
        # give one divisor per whole age, and the sheet does the same.
        idx = int(np.searchsorted(ages, age, side="right")) - 1
        return float(divs[max(0, min(idx, len(divs) - 1))])

    # ------------------------------------------------------------------- run
    def run(self, n_trials: int = 1, seed: int | None = None, market=None) -> Results:
        p, T, NL, NW, A = self.plan, self.T, self.NL, self.NW, self.A
        seed = p.seed if seed is None else seed
        mm = MarketModel(p.market) if market is None else market
        gen = mm.generate(n_trials, T, seed)
        rets, infl = gen["returns"], gen["inflation"]          # (n,T,A), (n,T)

        n = n_trials
        cpi = np.ones((n, T + 1))
        cpi[:, 1:] = np.cumprod(1.0 + infl, axis=1)
        real_ret = (1.0 + rets) / (1.0 + infl[:, :, None]) - 1.0

        S = np.zeros((n, NL, A))                               # real balances
        basis = np.zeros((n, NL))
        for i, lg in enumerate(p.ledgers):
            if lg.enabled:
                S[:, i, :] = lg.opening * self.w[i, 0, :]
                basis[:, i] = lg.basis if lg.basis else lg.opening

        out = {k: np.zeros((n, T + 1)) for k in
               ("income", "spend", "tax", "withdrawal", "contribution", "fees",
                "ret_rate", "shortfall", "taxable_income", "mrd")}
        bal_w = np.zeros((n, T + 1, NW))
        bal_tot = np.zeros((n, T + 1))
        bal_close = np.zeros((n, T + 1))
        carry_loss = np.zeros(n)
        gm = np.ones(n)                                        # guardrail multiplier
        rate0 = np.zeros(n)
        rate0_set = np.zeros(n, dtype=bool)
        prev_ret = np.zeros(n)

        pol = p.policy
        fee_rate_l = np.array([[float(np.dot(self.w[i, kk], self.ter))
                                for kk in range(T + 1)] for i in range(NL)])

        for k in range(T + 1):
            age = self.age[k]
            cp = cpi[:, k]
            s_scale = np.ones(n) if p.tax.index_bands else 1.0 / cp
            tot = S.sum(axis=(1, 2))
            for wi in range(NW):
                m = self.wrapper_of == wi
                bal_w[:, k, wi] = S[:, m, :].sum(axis=(1, 2)) if m.any() else 0.0
            bal_tot[:, k] = tot

            # ---- income (real) ---------------------------------------------
            income = self.inc_real[k] + self.inc_nom[k] / cp
            taxable = self.inc_tax_real[k] + self.inc_tax_nom[k] / cp

            # ---- mandatory distributions ------------------------------------
            mrd_total = np.zeros(n)
            for i, lg in enumerate(p.ledgers):
                wr = p.wrappers[lg.wrapper]
                if age < wr.mrd_age:
                    continue
                div = self._mrd_divisor(wr, age)
                if not np.isfinite(div) or div <= 0:
                    continue
                amt = S[:, i, :].sum(axis=1) / div
                S[:, i, :] -= amt[:, None] * self._frac(S[:, i, :])
                mrd_total += amt
                taxable += amt * wr.withdrawal_taxable_fraction
            income_plus = income + mrd_total

            # ---- spending target --------------------------------------------
            ess = self.ess_real[k] + self.ess_nom[k] / cp
            disc = self.disc_real[k] + self.disc_nom[k] / cp
            spend = self._spending(k, ess, disc, tot, cp, gm, pol)

            debt = self.debt_pay_nom[k] / cp

            # ---- tax on income (before discretionary withdrawals) ------------
            # The allowance is fixed by income alone and then held for the whole
            # period.  Letting a withdrawal taper its own allowance would make the
            # gross-up circular again, and the error is second order.
            allow = self._allowance(taxable, s_scale)
            base = np.maximum(0.0, taxable - allow)
            unused = np.maximum(0.0, allow - taxable)
            tax_income = self._tax(base, s_scale) + self._surtax(taxable, s_scale)
            need = spend + debt + tax_income - income_plus

            # ---- withdrawals -------------------------------------------------
            x0 = base.copy()
            wd_total = np.zeros(n)
            tax_wd = np.zeros(n)
            remaining = np.maximum(0.0, need)
            for i in self.order_wd:
                lg = p.ledgers[i]
                if not lg.enabled:
                    continue
                wr = p.wrappers[lg.wrapper]
                if not wr.liquid or age < wr.lock_age:
                    continue
                if not np.any(remaining > 1e-9):
                    break
                avail = S[:, i, :].sum(axis=1)
                pen = wr.early_penalty if age < wr.early_age else 0.0
                # One tax path for every wrapper.  A taxable account's withdrawal
                # is taxable only to the extent it is gain, scaled by the
                # jurisdiction's inclusion rate; a pension is taxable in full; a
                # tax-free wrapper is taxable not at all.  Same arithmetic, one
                # exact inversion.
                if wr.realises_capital_gains:
                    val = np.maximum(avail, EPS)
                    gain_frac = np.clip(1.0 - basis[:, i] / val, 0.0, 1.0)
                    f = gain_frac * p.tax.cg_inclusion
                else:
                    f = np.full(n, wr.withdrawal_taxable_fraction)
                f_eff = f / max(1e-6, 1.0 - pen)
                free = np.where(f > 1e-12, unused / np.maximum(f, 1e-12), np.inf)
                over = np.maximum(0.0, remaining - free * (1.0 - pen))
                h = self._gross_up(over, x0, f_eff, s_scale)
                want = np.where(f > 1e-12,
                                np.minimum(remaining / max(1e-6, 1.0 - pen), free)
                                + h / max(1e-6, 1.0 - pen),
                                remaining / max(1e-6, 1.0 - pen))
                take = np.minimum(avail, np.maximum(0.0, want))
                if not np.any(take > 0):
                    continue
                add_base = np.maximum(0.0, f * take - unused)
                gross_tax = self._tax(x0 + add_base, s_scale) - self._tax(x0, s_scale)
                if wr.realises_capital_gains:
                    basis[:, i] = np.maximum(
                        0.0, basis[:, i] * (1.0 - take / np.maximum(avail, EPS)))
                net = take * (1.0 - pen) - gross_tax
                remaining = np.maximum(0.0, remaining - net)
                S[:, i, :] -= take[:, None] * self._frac(S[:, i, :])
                unused = np.maximum(0.0, unused - f * take)
                x0 = x0 + add_base
                wd_total += take
                tax_wd += gross_tax
            shortfall = remaining

            # ---- surplus: contributions --------------------------------------
            surplus = np.maximum(0.0, income_plus - spend - debt - tax_income)
            contrib = np.zeros(n)
            for i in self.order_ct:
                lg = p.ledgers[i]
                if not lg.enabled or not np.any(surplus > 1e-9):
                    continue
                wr = p.wrappers[lg.wrapper]
                if self.hh_retired[k]:
                    continue
                want = lg.contribution + lg.contribution_pct_income * self.pensionable[k]
                want += (min(lg.contribution_pct_income, lg.employer_match_cap_pct)
                         * self.pensionable[k] * lg.employer_match_pct)
                cap = (np.inf if wr.cap_type == "none" else
                       wr.cap_value if wr.cap_type == "absolute" else
                       wr.cap_value * self.pensionable[k])
                if age >= wr.catch_up_age:
                    cap = cap + wr.catch_up_amount
                add = np.minimum(surplus, min(max(0.0, want), cap))
                if k == T:
                    add = np.zeros(n)
                S[:, i, :] += add[:, None] * self.w[i, k, :]
                basis[:, i] += add
                surplus -= add
                contrib += add
            # anything left over sweeps into the last contribution priority
            if np.any(surplus > 1e-9) and NL:
                j = min(max(0, pol.sweep_ledger), NL - 1)
                S[:, j, :] += surplus[:, None] * self.w[j, k, :]
                basis[:, j] += surplus
                contrib += surplus

            out["mrd"][:, k] = mrd_total
            out["income"][:, k] = income_plus
            out["spend"][:, k] = spend + debt
            out["tax"][:, k] = tax_income + tax_wd
            out["withdrawal"][:, k] = wd_total
            out["contribution"][:, k] = contrib
            out["shortfall"][:, k] = shortfall
            out["taxable_income"][:, k] = x0

            if k == T:
                bal_close[:, k] = S.sum(axis=(1, 2))
                break

            # ---- fees, returns, rebalancing ----------------------------------
            fee = np.zeros(n)
            for i, lg in enumerate(p.ledgers):
                if not lg.enabled:
                    continue
                rate = fee_rate_l[i][k] + p.platform_fee + p.adviser_fee
                amt = S[:, i, :] * rate
                fee += amt.sum(axis=1)
                S[:, i, :] -= amt
                S[:, i, :] *= (1.0 + real_ret[:, k, :])
                if lg.rebalance == "annual":
                    tv = S[:, i, :].sum(axis=1)
                    S[:, i, :] = tv[:, None] * self.w[i, k + 1, :]
            out["fees"][:, k] = fee
            nb = S.sum(axis=(1, 2))
            bal_close[:, k] = nb
            # Forced distributions leave the portfolio too, so they belong in the
            # base the implied return is measured against; omitting them made the
            # reported rate - and the reconciliation built on it - drift once a
            # wrapper started mandating draws.
            ob = np.maximum(tot - mrd_total - wd_total + contrib - fee, EPS)
            out["ret_rate"][:, k] = nb / ob - 1.0
            prev_ret = out["ret_rate"][:, k]
            gm = self._guardrails(k, tot, spend, gm, pol, prev_ret, infl[:, k],
                                  rate0, rate0_set)

        debt_bal = self.debt_bal_nom[None, :] / cpi
        nw = bal_close - debt_bal
        return Results(plan=p, cpi=cpi, balance=bal_tot, balance_close=bal_close,
                       mrd=out["mrd"], balance_by_wrapper=bal_w,
                       income=out["income"], spend=out["spend"], tax=out["tax"],
                       withdrawal=out["withdrawal"], contribution=out["contribution"],
                       fees=out["fees"], ret_rate=out["ret_rate"],
                       shortfall=out["shortfall"], debt_balance=debt_bal,
                       net_worth=nw, regime=gen["regime"],
                       taxable_income=out["taxable_income"], ages=self.age)

    # ------------------------------------------------------------- components
    @staticmethod
    def _frac(block):
        """Pro-rata split of a withdrawal across the assets held in a ledger."""
        tot = block.sum(axis=1, keepdims=True)
        return np.where(tot > EPS, block / np.maximum(tot, EPS), 0.0)

    def _allowance(self, gross_taxable, s):
        sc = self.plan.tax.ordinary
        s = np.asarray(s, dtype=float)
        if sc.allowance <= 0:
            return np.zeros_like(np.asarray(gross_taxable, dtype=float))
        lost = np.maximum(0.0, gross_taxable - sc.taper_start * s) * sc.taper_rate
        return np.maximum(0.0, sc.allowance * s - lost)

    def _surtax(self, gross_taxable, s):
        ts = self.plan.tax
        if ts.surtax_rate <= 0:
            return 0.0
        s = np.asarray(s, dtype=float)
        return np.maximum(0.0, gross_taxable - ts.surtax_threshold * s) * ts.surtax_rate

    def _tax(self, taxable_real, s):
        """Tax in real terms, using the homogeneity trick for frozen bands."""
        s = np.asarray(s, dtype=float)
        return self.plan.tax.ordinary.tax_on_taxable(taxable_real / s) * s

    def _gross_up(self, need, x0, f, s):
        s = np.asarray(s, dtype=float)
        return self.plan.tax.ordinary.gross_up(need / s, x0 / s, f) * s

    def _spending(self, k, ess, disc, portfolio, cp, gm, pol):
        m = pol.method
        if m == "fixed_nominal":
            return (ess + disc) / cp
        if m == "pct_portfolio":
            return np.maximum(ess, pol.pct * portfolio)
        if m == "vpw":
            rem = max(1, self.T - k)
            r = pol.vpw_rate
            factor = r / (1 - (1 + r) ** -rem) if r > EPS else 1.0 / rem
            return np.maximum(ess, portfolio * factor)
        if m == "table":
            rem = max(1.0, float(self.T - k))
            return np.maximum(ess, portfolio / rem)
        if m == "guardrails":
            return ess + disc * gm
        return ess + disc                                  # fixed_real

    def _guardrails(self, k, portfolio, spend, gm, pol, prev_ret, infl,
                    rate0, rate0_set):
        if pol.method != "guardrails":
            return gm
        if not self.hh_retired[k]:
            return gm
        rate = spend / np.maximum(portfolio, EPS)
        fresh = self.hh_retired[k] & (~rate0_set)
        rate0[fresh] = rate[fresh]
        rate0_set[fresh] = True
        hi = (rate > (1 + pol.guard_up) * rate0) & ((self.T - k) > pol.guard_final_years)
        lo = rate < (1 - pol.guard_down) * rate0
        gm = np.where(hi, gm * (1 - pol.guard_cut), gm)
        gm = np.where(lo, gm * (1 + pol.guard_raise), gm)
        if pol.inflation_skip:
            skip = (prev_ret < 0) & (rate > rate0)
            gm = np.where(skip, gm / (1.0 + np.maximum(0.0, infl)), gm)
        return np.clip(gm, 0.2, 3.0)
