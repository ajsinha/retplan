# RetPlan — Mathematics and Simulation Specification

Every algorithm below is normative and is implemented once in
`retplan/` (pure Python + numpy) and mirrored by generated spreadsheet formulas.
Equality of the two implementations is a test requirement (TR-4).

---

## 1. Notation

`t` = period index, `0 … T`; `Δ` = periods per year (1 annual, 12 monthly).
`P_t` = portfolio value at the start of period `t`. `μ`, `σ` are the **arithmetic**
expected simple return and standard deviation per year, as entered by the user.

## 2. Pseudo-random numbers

`RAND()` is banned (non-reproducible, engine-dependent). RetPlan uses **L'Ecuyer's combined
multiplicative generator** (1988), exact in IEEE-754 doubles and therefore bit-identical in
Python, in Basic and in cell formulas.

```
s1 ← s1 · 40014 mod 2147483563
s2 ← s2 · 40692 mod 2147483399
z  ← (s1 − s2) mod 2147483562
u  ← (z + 1) / 2147483563          ∈ (0,1)
```

Period ≈ 2.3 × 10^18. Both products stay below 2^53, so no rounding occurs.
Seeds are derived from the user seed `S` by `s1 = 1 + (S mod 2147483562)`,
`s2 = 1 + ((S·48271) mod 2147483398)`, then 16 warm-up draws are discarded.

- Each stochastic dimension (asset shocks, regime transitions, crash occurrence, crash
  depth, inflation, longevity, expense shocks, one-off events) MUST draw from its **own
  stream**, seeded by `S` combined with a fixed per-dimension offset, so that changing the
  trial count or toggling a feature does not reshuffle unrelated draws.
- Trial `i` MUST be seeded by `S ⊕ (i · 2654435761 mod 2^31)` so trials are independent and
  a single trial can be reproduced in isolation (F-SIM-9).

## 3. Normal and Student-t variates

Inverse-CDF sampling (not Box–Muller), so that antithetic and Latin-hypercube variance
reduction work, and so the spreadsheet fallback can use `NORM.S.INV(u)` and agree.

- `z = Φ⁻¹(u)` via Acklam's rational approximation, refined by one Halley step; absolute
  error < 1e-15, and within 1e-9 of `NORM.S.INV` in both engines.
- Student-t with ν degrees of freedom: `t = z / sqrt(W/ν)`, `W ~ χ²_ν`. To keep the user's
  stated volatility meaningful, the variate is **variance-matched**:
  `t* = t · sqrt((ν−2)/ν)`, requiring `ν > 2`. This preserves σ while fattening the tails.

## 4. From arithmetic inputs to log-space parameters

Users think in arithmetic means; compounding happens in log space. With per-period
`m = μ/Δ` and `s = σ/√Δ`:

```
σ_log = sqrt( ln(1 + s² / (1+m)²) )
μ_log = ln(1+m) − σ_log²/2
R     = exp(μ_log + σ_log · ε) − 1
```

For the normal (not lognormal) option, `R = m + s·ε`, floored at −0.99 to prevent
non-economic values. The choice is a user setting; lognormal is the default.

## 5. Correlated multi-asset shocks

Given the user correlation matrix `C` (N×N):

1. **Validate**: symmetry, unit diagonal, all entries in [−1, 1].
2. **Repair if needed**: shrink toward the identity, `C_λ = (1−λ)C + λI`, taking the
   smallest `λ ∈ {0, 0.01, 0.02, …, 0.5}` on a grid for which the Cholesky factorisation
   succeeds. The applied `λ` is reported on screen (FR-AL-2).
3. **Factor**: `C = L Lᵀ` by the standard Cholesky recursion
   `L_ii = sqrt(C_ii − Σ_{k<i} L_ik²)`, `L_ij = (C_ij − Σ_{k<j} L_ik L_jk) / L_jj`.
4. **Draw**: `ε = L z`, with `z` a vector of iid standard variates from §3.

The spreadsheet fallback computes the same `L` in a triangular block of cells.

## 6. Market regimes (bull / normal / bear, extensible)

A discrete-time Markov chain over `K` user-defined regimes with transition matrix `P`,
rows summing to 1 (validated).

- **Regime draw**: given state `k`, the next state is the smallest `j` with
  `u < Σ_{l≤j} P_kl` — inverse CDF on the row.
- **Initial state**: `{stationary, specified, random}`. The stationary distribution `π` is
  obtained by repeated squaring, `P^(2^6) = P^64`, whose rows have converged for any
  practical `P`; `π` is then the first row.
- **Expected duration** of regime `k` is `1/(1 − P_kk)`, displayed next to the input so the
  user can calibrate persistence intuitively (a bear with `P_kk = 0.5` lasts ~2 years).
- **Per-regime parameters**: each regime carries, per asset class, a mean offset `a_k`
  (or multiplier) and a volatility multiplier `b_k`, so
  `m_k = m + a_k`, `s_k = s · b_k`.
- **Correlation tightening**: in stress regimes, diversification fails. Correlations are
  pulled toward 1 by a regime weight `w_k ∈ [0,1]`:
  `C_k = (1 − w_k)·C + w_k·J`, where `J` is the all-ones matrix. `J` is positive
  semi-definite, so the convex combination remains PSD — the Cholesky is always valid.

Defaults shipped as sample data (user-editable, not hard-coded):

| Regime | mean offset (equity) | vol multiplier | `w` | P(→bear) | P(→normal) | P(→bull) |
|---|---|---|---|---|---|---|
| Bear | −22% | 1.9× | 0.55 | 0.50 | 0.45 | 0.05 |
| Normal | 0% | 1.0× | 0.00 | 0.10 | 0.80 | 0.10 |
| Bull | +8% | 0.8× | 0.00 | 0.04 | 0.26 | 0.70 |

Stationary distribution of that matrix ≈ bear 13%, normal 62%, bull 25%.

## 7. Random crashes (jump process)

Independent of, and multiplicative on top of, the regime return — so a crash can strike in
any regime, and the bear regime raises the odds through its own parameters.

- **Occurrence**: Bernoulli per period with probability `λ` (default 4% per year), or
  Poisson counts by inverse transform when multiple crashes per period are allowed.
- **Depth** `D`: triangular distribution with user min/mode/max (default 20% / 35% / 60%),
  sampled by exact inverse CDF:

```
c = (mode − min)/(max − min)
D = min + sqrt(u · (max−min) · (mode−min))                 if u < c
D = max − sqrt((1−u) · (max−min) · (max−mode))             otherwise
```

- **Asset transmission**: each asset class has a crash **beta** `β_j`; the realised shock is
  `−β_j · D`. Equities default to 1.0, corporate credit 0.4, government bonds −0.15 (a
  flight-to-quality gain), cash 0.0, property 0.6. This is what makes the crash module
  genuinely multi-asset rather than an equity-only haircut.
- **Duration**: a crash of duration `d > 1` spreads `D` across `d` periods with weights
  `(0.6, 0.3, 0.1)` by default (user-editable), so drawdowns are not instantaneous.
- **Recovery**: a fraction `ρ` of the cumulative loss is added back as extra drift spread
  evenly over the following `r` periods, capturing partial mean reversion without
  introducing a full autocorrelation model.
- **Combination**: `1 + R_total = (1 + R_regime) · (1 − shock_t) · (1 + recovery_t)`.

## 8. Sequence-of-returns risk

- **Forced-bad-start test**: the worst `k` consecutive periods of the user's chosen series
  are moved to the first `k` periods of retirement, with the remainder following in order.
- **Retirement-date stress**: a specified crash is forced at retirement year ± n, and the
  KPI delta against the base is reported (F-RET-9).
- **Historical rolling backtest**: for a pasted series of `n` annual returns and a horizon
  `T`, every start `s ∈ [1, n−T+1]` produces one full plan run; the outcome distribution is
  reported alongside the Monte Carlo distribution.
- **Block bootstrap**: blocks of length `L` (default 5) are drawn with replacement from the
  historical series until `T` periods are filled, preserving short-horizon autocorrelation.
  The stationary bootstrap variant uses a geometric block length with mean `L`.

## 9. Inflation

`π_t` is fixed, path-supplied, or stochastic with mean reversion (Ornstein–Uhlenbeck in
discrete form):

```
π_t = π̄ + φ · (π_{t−1} − π̄) + σ_π · ε_t
```

`ε_t` is correlated with the equity shock by a user coefficient `ρ_{π,eq}`, implemented by
appending inflation as an extra row/column of the correlation matrix. Category price levels
compound `π_t + delta_c`. The real/nominal toggle deflates by the realised cumulative CPI of
the same path — so real results are correct path-by-path, not deflated by an average.

## 10. Taxation

### 10.1 Stacked progressive tax

Income categories are stacked in a user-defined order. For a schedule with bands
`(b_1=0, r_1), (b_2, r_2), …`, tax on a stacked slice `[x, y]` above allowance `A` is

```
Tax(x,y) = Σ_i r_i · [ max(0, min(y−A, b_{i+1}) − max(x−A, b_i)) ]
```

Allowances taper: `A_eff = max(0, A − taper_rate · max(0, income − taper_start))`.

### 10.2 Exact gross-up (no circular references)

Given other income already stacked to level `x₀` and a required **net** amount `n`, the
gross withdrawal `g` solving `g − Tax(x₀, x₀+g) = n` is found by **piecewise-linear
inversion**, not iteration:

1. Compute the cumulative net at every band ceiling: `N_i = (b_i − x₀) − Tax(x₀, b_i)`.
2. Find the band `k` with `N_k ≤ n < N_{k+1}` by `MATCH`.
3. `g = (b_k − x₀) + (n − N_k) / (1 − r_{k+1})`.

Exact, single-pass, and identical in the sheet and in Python. When the withdrawal is only
partially taxable (fraction `f`), the effective marginal rate in step 3 becomes
`1 − f·r_{k+1}`, and step 1 uses `f·` the taxable slice.

### 10.3 Other

- Capital gains: realised gain on a withdrawal from a taxable account is
  `w · (1 − basis/value)`, average-cost; gains net an annual exemption and any carried loss,
  then apply the CG schedule with an optional holding-period discount.
- Mandatory distributions: `MRD_t = balance_t / divisor(age_t)` from a user table.
- Effective rate = total tax / gross income; marginal rate is measured by re-running the
  stacked tax with +1 unit of income (an exact finite difference, one extra column).

## 11. Withdrawal policies

Let `W_t` be the gross real spending target and `w_t = W_t / P_t`.

- **Fixed real**: `W_t = W_0`, inflated by realised CPI.
- **Fixed nominal**: `W_t = W_0`.
- **Constant percentage**: `W_t = p · P_t`.
- **VPW / amortisation**: `W_t = P_t · r / (1 − (1+r)^{−(N−t)})`, with `r` the assumed real
  return and `N−t` the remaining horizon.
- **Table-driven**: `W_t = P_t / divisor(age_t)`.
- **Guardrails (Guyton–Klinger)**, all parameters editable:
  - *Capital preservation*: if `w_t > (1+G_up)·w_0` and more than `k` periods remain,
    cut `W_t` by `c%`.
  - *Prosperity*: if `w_t < (1−G_dn)·w_0`, raise `W_t` by `c%`.
  - *Inflation rule*: skip the inflation increase if the prior-period portfolio return was
    negative **and** `w_t > w_0`; no catch-up later.
  - Essential spending is a floor that no rule may breach (FR-EXP-6).
- **Floor-and-upside**: guaranteed income covers the essential floor; only the discretionary
  layer is drawn from the portfolio and is subject to cuts.

## 12. Key metrics

- **Success**: terminal real wealth ≥ legacy target and no period with an unmet essential
  need. Probability = successful trials / trials.
- **Funded ratio**: `(P_0 + PV(future non-portfolio income)) / PV(future spending)`,
  discounted at a user rate (default: the portfolio's expected real return).
- **Maximum sustainable spend**: bisection on `W_0` such that the success probability equals
  the target confidence, tolerance `1e-4` relative, ≤ 40 evaluations.
- **Safe withdrawal rate**: max sustainable spend ÷ `P_0` at retirement.
- **Depletion age**: first period where liquid wealth hits zero; reported as a distribution.
- **Worst drawdown**: `min_t (P_t / max_{s≤t} P_s − 1)` in real terms.
- **Shortfall**: cumulative unmet need in real terms, and the number of years affected —
  reported because a plan that fails at 94 by a little is not a plan that fails at 72 by a lot.

## 13. Variance reduction and convergence

- **Antithetic variates**: trial `2i+1` reuses trial `2i`'s uniforms as `1−u` for the asset
  shock stream only (regime and crash streams stay independent, to avoid negative dependence
  artefacts in the jump process).
- **Latin hypercube** (optional) stratifies the first-period uniforms.
- **Convergence report**: the standard error of the success probability,
  `sqrt(p(1−p)/n)`, is displayed with the result, plus the trial count needed for a ±1%
  half-width at 95% confidence. A result of "82%" from 200 trials is reported as
  "82% ± 5.3%", because a false precision is worse than no number.

## 14. Numerical hygiene

- Balances are clamped at zero; shortfalls are recorded, never negative balances.
- All divisions are guarded; `0/0` yields a labelled state, not `#DIV/0!`.
- Money is carried in double precision and rounded only for display; reconciliation
  tolerance is `1e-6` absolute on a per-period basis.
- The numpy engine and the formula engine MUST agree to `1e-9` relative on the
  deterministic path (TR-4); any drift is a build-blocking failure.
