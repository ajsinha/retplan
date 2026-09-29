# RetPlan — Mathematics and Simulation

The algorithms behind the plan engine (`retplan/`) and the portfolio projection
(`portfolio/`). Section numbers are referenced from code comments and the other
documents.

---

## 1. Notation

`t = 0 … T` is the annual period index of a plan. `μ`, `σ` are the **arithmetic**
expected simple return and standard deviation per year, as the user enters them.
All plan quantities are real (today's money) unless marked nominal. `CPI_t` is a
trial's cumulative price index, `CPI_0 = 1`.

## 2. Pseudo-random numbers (plan engine)

The plan engine uses **L'Ecuyer's combined multiplicative generator** (1988),
vectorised so one object holds one stream per trial:

```
s1 ← s1 · 40014 mod 2147483563
s2 ← s2 · 40692 mod 2147483399
z  ← (s1 − s2) mod 2147483562
u  ← (z + 1) / 2147483563          ∈ (0,1)
```

Both products stay below 2^53, so the arithmetic is exact in doubles.

- **Seeding.** Each stream's two states come from SplitMix64 applied to a counter
  built from the user seed, a fixed per-dimension offset and the trial index. The
  scrambling matters: L'Ecuyer streams seeded by nearby integers are lagged copies
  of one another. Eight warm-up draws are discarded.
- **Independent dimensions.** Asset shocks, regime transitions, crash occurrence,
  crash depth, inflation and the chi-square draws for Student-t each use their own
  stream (`rng.STREAM`), so toggling one feature or changing the trial count never
  reshuffles the draws of another, and trial *i* is the same whatever *n* is.

The portfolio projection (§17) uses NumPy's `default_rng` with the settings' seed.

## 3. Normal and Student-t variates

Inverse-CDF sampling, so antithetic variates work:

- `z = Φ⁻¹(u)` by Acklam's rational approximation, refined by one Halley step
  (absolute error below 1e-15).
- Student-t with ν degrees of freedom: `t = z / sqrt(W/k)` with `k = round(ν)` and
  `W` a sum of `k` squared independent normals, then **variance-matched**,
  `t* = t · sqrt((k−2)/k)`, requiring ν > 2. The stated σ keeps its meaning while
  the tails fatten.

## 4. From arithmetic inputs to log-space parameters

```
σ_log = sqrt( ln(1 + σ² / (1+μ)²) )
μ_log = ln(1+μ) − σ_log²/2
R     = exp(μ_log + σ_log · ε) − 1
```

For the normal option, `R = μ + σ·ε`. Monte Carlo returns are floored at −99.5%
after the crash layer.

### 4.1 The fixed-return basis

The deterministic projection (market mode `fixed`, and the dashboard's
fixed-return view) grows each asset at a constant rate chosen by
`MarketSpec.fixed_basis`:

- **typical** (default): the median growth rate,
  `(1 + μ) · exp(−σ_log²/2) − 1`, what compounding delivers in the middle future;
- **average**: `μ` itself, higher by roughly `σ²/2`, which makes a fixed-return
  plan look better than half of its futures.

Fixed mode has no regimes, crashes or stochastic inflation.

## 5. Correlated multi-asset shocks

1. **Repair if needed.** Shrink toward the identity, `C_λ = (1−λ)C + λI`, taking
   the smallest `λ ∈ {0, 0.01, …, 0.50}` for which the Cholesky factorisation
   succeeds; if none does, the identity. The applied `λ` is shown on the dashboard.
2. **Factor.** `C_λ = L Lᵀ`.
3. **Draw.** `ε = L z`, with `z` iid from §3.

## 6. Market regimes

A discrete Markov chain over `K` user-defined regimes with transition matrix `P`,
rows summing to 1 (validated to 1e-6).

- **Next state**: the smallest `j` with `u < Σ_{l≤j} P_kl`.
- **Initial state**: stationary (draw from `π`), random (uniform), or a fixed index.
- **Stationary distribution** `π`: the first row of `P^64` (six squarings).
- **Expected duration** of regime `k`: `1/(1 − P_kk)`.
- **Per-regime parameters.** A scalar mean offset `a_k` is scaled per asset by its
  volatility relative to the first asset, `a_kj = a_k · σ_j/σ_1`, so a bear market
  hits equities harder than cash. Volatility is multiplied by `b_k`.
- **Correlation tightening**: `C_k = (1 − w_k)·C + w_k·J`, `J` all ones. `J` is PSD,
  so the convex combination stays PSD. One Cholesky factor per regime.

Sample regimes (data in `retplan/samples.py`, not code):

| Regime | mean offset | vol × | `w` | → bear | → normal | → bull |
|---|---|---|---|---|---|---|
| Bear | −22% | 1.9 | 0.55 | 0.50 | 0.45 | 0.05 |
| Normal | 0% | 1.0 | 0.00 | 0.10 | 0.80 | 0.10 |
| Bull | +8% | 0.8 | 0.00 | 0.04 | 0.26 | 0.70 |

## 7. Random crashes (jump process)

Applied multiplicatively on top of the regime return.

- **Occurrence**: Bernoulli per year with probability `λ` (default 4%).
- **Depth** `D`: triangular with min / mode / max (default 20% / 35% / 60%), by
  exact inverse CDF:

```
c = (mode − min)/(max − min)
D = min + sqrt(u · (max−min) · (mode−min))                 if u < c
D = max − sqrt((1−u) · (max−min) · (max−mode))             otherwise
```

- **Shape**: the fall is spread over `duration` years by weights (default
  0.6, 0.3, 0.1, normalised to the duration).
- **Recovery**: a fraction `ρ` of `D` is added back evenly over the `r` years after
  the fall ends (a negative shock).
- **Transmission**: asset `j` receives `β_j` times the shock:
  `1 + R_total = (1 + R_regime) · (1 − shock_t · β_j)`. Sample betas: equity 1.0,
  government bonds −0.15 (a flight-to-quality gain), credit 0.4, property 0.6,
  cash 0, alternatives 0.5.

## 8. Calibration

With `calibrate` on (default), regime drift and crash drag are re-centred so the
**unconditional** mean return equals the `μ` typed:

```
drag_j = λ · E[D] · (1 − ρ) · β_j,      E[D] = (min + mode + max)/3
ā_j    = Σ_k π_k a_kj
μ_eff,j = (1 + μ_j)/(1 − drag_j) − 1 − ā_j
```

Without it, adding a bear regime or a crash process would silently lower every
expected return. The dashboard reports the realised mean and volatility per asset
from a separate sample (up to 4,000 trials) beside the inputs.

## 9. Inflation

Fixed, a user path (repeated to fill the horizon), or AR(1):

```
π_t = π̄ + φ · (π_{t−1} − π̄) + σ_π · (ρ · ε_eq,t + sqrt(1−ρ²) · ε_ind,t)
```

`ε_eq` is the first asset's correlated shock, so inflation co-moves with equities
by `ρ`. Real asset returns are `(1 + R)/(1 + π) − 1`, per trial, per year.

## 10. Taxation

### 10.1 Progressive schedule

Bands `(L_i, r_i)`, `L_1 = 0`, upper bound `U_i = L_{i+1}`:

```
Tax(x) = min( Σ_i r_i · clip(x − L_i, 0, U_i − L_i), cap )
```

Allowance: `A_eff = max(0, A − taper_rate · max(0, income − taper_start))`, fixed
from income alone at the start of the year. A withdrawal cannot taper its own
allowance (that would make the gross-up circular); the error is second order. A
surtax adds `surtax_rate · max(0, taxable − threshold)`.

### 10.2 Exact gross-up

With taxable income already stacked to `x₀`, a withdrawal of which a fraction `f`
is taxable, and a required **net** amount `n`, find `g` with
`g − [Tax(x₀ + f·g) − Tax(x₀)] = n`:

1. For every band bound `L_i > x₀`, the net achieved when taxable income reaches it:
   `N_i = (L_i − x₀)/f − (CT_i − Tax(x₀))`, where `CT_i` is the cumulative tax at
   `L_i` (a constant vector).
2. Take the highest band reached, `N_i ≤ n`; call its bound the anchor.
3. `y = anchor + (n − N_anchor) / (1/f − r)`; `g = (y − x₀)/f`.

One pass, no iteration. `f = 0` means gross = net. An early-withdrawal penalty `p`
is folded in by using `f/(1−p)` and dividing the target by `1−p`. Unused
allowance is consumed first, tax-free.

### 10.3 Fiscal drag by homogeneity

A progressive schedule is positively homogeneous of degree one:
`Tax_s(x) = s · Tax_1(x/s)` when every band, allowance and cap is scaled by `s`.
Indexed bands in real terms need `s = 1`; frozen bands use `s = 1/CPI_t` — exact,
with no per-trial rebuild.

### 10.4 Other

- **Capital gains**: a withdrawal of `w` from a wrapper that realises gains has
  taxable fraction `f = (1 − basis/value) · cg_inclusion` (average cost). Basis is
  reduced pro rata; contributions add to it.
- **Minimum distributions**: `MRD_t = balance_t / divisor(age_t)`, the divisor by
  step lookup (the last listed age at or below the current age), from `mrd_age`.
  Taxed at the wrapper's withdrawal fraction; unspent MRDs are reinvested through
  the surplus.

## 11. Contributions and employer match

While at least one person is working (and not in the final period), surplus
`S = max(0, income − spend − debt − tax)` funds accounts in contribution priority:

```
pay     = earnings this year (employment + self-employment)
want    = contribution + contribution_pct_income · pay
cap     = ∞ | cap_value | cap_value · pay     (+ catch_up_amount from catch_up_age)
own     = min(S, want, cap)
match   = min( min(own, pct_want)/pay , match_cap_pct ) · pay · match_pct
match   = min(match, cap − own)
```

where `pct_want = contribution_pct_income · pay`. Your own saving reduces the
surplus; the **employer match does not** — it is new money on top, paid on the
percentage-of-pay saving actually made. Whatever surplus remains goes to the
policy's sweep account.

### 11.1 Conversions between accounts

Before the spending target is set, each enabled conversion active at person 1's
age (`start_age ≤ age < end_age`, never in the final period) moves

```
amount mode:   c = min(balance_src, amount)
fill_to mode:  c = min(balance_src, max(0, target − taxable) / f_src)
```

from the source account (pro rata across its assets, basis reduced pro rata) into
the destination at its current weights (basis increased by `c`). Taxable income
rises by `f_src · c`, where `f_src` is the source wrapper's withdrawal taxable
fraction, so the conversion's tax is part of the year's tax on income and is met
by ordinary withdrawals through the exact gross-up. The portfolio total is
unchanged, so the reconciliation identity is unaffected.

## 12. Withdrawal policies

`E_t`, `D_t` are essential and discretionary spending; `P_t` the opening portfolio.

- **Fixed real**: `E_t + D_t`.
- **Fixed nominal**: `(E_t + D_t)/CPI_t` — the amounts held flat in money terms, so
  their real value falls with inflation.
- **% of portfolio**: `max(E_t, p · P_t)`.
- **VPW**: `max(E_t, P_t · r / (1 − (1+r)^{−(T−t)}))`.
- **Table**: `max(E_t, P_t / (T − t))`.
- **Guardrails**: `E_t + D_t · g_t`, where the multiplier `g` starts at 1 and, once
  the whole household is retired, with `w_t = spend/P_t` and `w_0` its value in the
  first retired year:
  - *capital preservation*: if `w_t > (1+G_up)·w_0` and more than `k` years remain,
    `g ← g·(1 − cut)`;
  - *prosperity*: if `w_t < (1−G_dn)·w_0`, `g ← g·(1 + raise)`;
  - *inflation skip*: if last year's return was negative and `w_t > w_0`,
    `g ← g/(1 + π_t)`;
  - `g` is clipped to [0.2, 3.0]. Essential spending is never cut.

## 13. Metrics

- **Success**: no year with shortfall above 1e-6 and real terminal net worth ≥ the
  legacy target. `p` = successful / trials.
- **Standard error**: `sqrt(p(1−p)/n)`, shown with the result; 95% interval
  `p ± 1.96·se`; trials needed for ±1%: `1.96² · max(p(1−p), 0.01) / 0.01²`.
  "82%" from 200 trials is reported as "82% ± 2.7%", because false precision is
  worse than none.
- **Funded ratio** (fixed-return path):
  `(P_0 + Σ_t (income_t − MRD_t)·d_t) / Σ_t spend_t·d_t`, `d_t = (1+r)^{−t}` at the
  policy's discount rate. Forced distributions are excluded from income because
  they come out of the portfolio already counted in `P_0`.
- **Depletion age**: the age at the first shortfall year; P10 and P50 over failing
  trials.
- **Drawdown**: `min_t (NW_t / max_{s≤t} NW_s − 1)` in real net worth; worst and
  median over trials.
- **Terminal wealth**: P5, P50, P95 and mean of real net worth at `T`.

## 14. Solvers

Bisection on the full model (every evaluation re-runs the projection with
`max(200, min(1500, trials/2))` trials on the plan seed). If the bracket holds no
root, the endpoint nearer the target is returned and flagged unbracketed.

| Solver | Variable | Bracket | Tolerance |
|---|---|---|---|
| Maximum sustainable spend | factor on every spending row | 0.1 – 3.0 | 2e-3 |
| Earliest retirement age | everyone's retirement age | current age + 0.5 – min(85, planning age − 1) | 0.01 years |
| Required extra saving | added to the sweep account's contribution | 0 – 200,000 | 1e-2 relative |

- **Success curve**: success at 17 spending levels from 50% to 150%.
- **Tornado**: success at ± a step for each driver — expected returns ±1 pt,
  inflation ±1 pt, spending ±10%, retirement age ±2 years, fees ±0.5 pt, longevity
  ±5 years (horizon extended to cover it, capped at 80), volatility ±3 pts, crash
  probability ±3 pts — ranked by the spread.
- Moving retirement moves the end age of earnings that stopped at the old
  retirement age; earnings that ended earlier keep their end.

## 15. Variance reduction

With `antithetic` on, odd-numbered trials use `1 − u` for the asset-shock stream
only; regime, crash and inflation streams stay independent.

## 16. Numerical hygiene

- Balances are never negative; unmet need is recorded as shortfall.
- Divisions are guarded with `max(·, 1e-12)`; a 100% tax band has its slope floored.
- The reconciliation identity (03-data-model DR-11) holds to 1e-6 relative in every
  period; the audit reports the worst error.

---

## 17. Portfolio projection (`portfolio/projection.py`)

### 17.1 Estimates per security

- **Volatility**: with at least 60 daily log returns in the stored year,
  `σ_1y = sd(r)·sqrt(252)`. With long-run monthly volatility `σ_lt` also known,
  `σ = sqrt(½σ_1y² + ½σ_lt²)`; otherwise whichever exists; otherwise the class
  assumption. Cash uses the class assumption.
- **Expected return**: never the one-year sample mean.
  - `assumption`: the class `μ`;
  - `history`: the security's long-run arithmetic return, if at least 3 years;
  - `blend` (default): `μ = (1−w)·μ_class + w·μ_lt`, `w = min(years, 20)/40`, so
    at most half weight at 20 years.
  A per-holding override replaces either number.
- **Long-run statistics** (`yahoo.long_run_stats`): from up to 20 years of monthly
  adjusted closes (at least 25), `σ_lt = sd(log r)·sqrt(12)`, and
  `μ_lt = exp(12·mean(log r) + σ_lt²/2) − 1`.
- **Correlation**: pairwise over common dates (at least 60),
  `ρ = 0.7·ρ_sample + 0.3·ρ_class`; otherwise the class prior (same class 0.90, cash
  0, "other" 0.50, listed pairs, else 0.30). Repaired as in §5.
- Foreign holdings use price series converted day by day with the stored FX pair,
  so currency risk enters the volatility and correlations.

### 17.2 Simulation

A quarterly clock (`Q = 4`), whatever the reporting frequency. Per quarter
`k = 0 … 4·years − 1`:

1. **Contributions** at the start of the quarter buy the target mix:
   `amount/4 · (1+g)^{year − start} · (1+π)^{k/4}` if indexed.
2. **Withdrawals**: scheduled amount plus `withdrawal_rate/4 · V`, taken pro rata,
   capped at `V`; a capped withdrawal marks the trial depleted.
3. **Returns**, one of:
   - *parametric*: `gross = exp(m_q + s_q·Lz)`, with
     `m_q = (ln(1+μ) − s²/2)/4`, `s_q = sqrt(s²/4)`, `s² = ln(1 + σ²/(1+μ)²)`;
   - *fat_tails*: the same with `Lz / sqrt(χ²_5/5) · sqrt(3/5)`, one chi-square
     draw shared by every asset so crashes are joint;
   - *bootstrap*: from the stored daily log returns on dates every risky asset
     shares (at least 84), every overlapping 21-day window sum; each column is
     centred and rescaled so a quarter's shock (three windows) has exactly the
     blended volatility; per quarter three windows are drawn independently and
     `gross = exp(m_q + Σ windows)`. The data supplies shape (fat tails,
     co-movement); the assumptions supply level. Too few common days falls back to
     parametric with a note.
   - During a stress opening (§18), the scenario's quarterly class returns replace
     the draw in every trial.
4. **Fee**: `V ← V·(1 − f_q)`, `f_q = 1 − (1 − fee)^{1/4}`.
5. **Rebalance** to the start weights at the end of every quarter, year, or never.
6. The quarter's time-weighted return `r_k = V_end / V_after_flows − 1` feeds a
   growth index for CAGR and maximum drawdown (fees included, flows excluded).

### 17.3 Results

- Per reporting period: P5–P95 of nominal and real value (deflated by
  `(1+π)^{years}`), mean, period-return percentiles, median CAGR to date, mean
  contributions, median withdrawals, P(loss in period), P(depleted by then),
  P(real value ≥ start), P(goal reached by then).
- Summary: end-value percentiles, CAGR percentiles, P(end < net money in),
  P(CAGR < inflation), P(depleted), P(goal) with its standard error, max-drawdown
  and worst-calendar-year percentiles.
- **Expected path**: no noise, portfolio return `w·μ` compounded quarterly with the
  same flows and fee.
- **Portfolio analytics**: `μ_p = w·μ`, `σ_p = sqrt(wᵀΣw)`, `Σ = diag(σ) C diag(σ)`;
  risk share `w_i (Σw)_i / σ_p²`, summing to 1.
- **Representative futures**: the trials whose real end value is nearest P10, P50
  and P90.
- Histograms of real end value (24 bins to P98) and of maximum drawdown (20 bins,
  −80% to 0).

## 18. Stress replays (`portfolio/stress.py`)

Five episodes as quarterly total returns of five proxies (US equity, US aggregate
bonds, T-bills, REITs, a commodity index), rounded to about a percentage point per
quarter; 1973–74 is annual data spread evenly, `(1+R)^{1/4} − 1` per quarter.

| Key | Episode | Quarters |
|---|---|---|
| `gfc` | 2007 Q4 – 2009 Q4 | 9 |
| `dotcom` | 2000 Q2 – 2002 Q4 | 11 |
| `covid` | 2020 Q1 – Q2 | 2 |
| `rates2022` | 2022 | 4 |
| `stagflation` | 1973 – 1974 | 8 |

- **Class path**: each asset class follows its proxy with a beta (intl equity 1.05,
  EM equity 1.25, crypto 2.5 and other 0.8 on equity; the rest 1.0). The excess over
  cash is scaled, not the rate: `R = c + β(R_proxy − c)`, floored at −95%.
- **Replay** (no cash flows): start weights, apply each quarter's class returns,
  rebalance as configured; then compound at `(1+μ)^{1/4}` per quarter until the value
  regains its start or 40 quarters pass. Reported: trough, drawdown
  `trough/start − 1`, value and return at the end of the crisis, quarter of recovery.
- **Stress-opened projection**: the episode's quarters open every trial; the
  stochastic model continues from there. This tests sequence risk: the crisis first,
  then an uncertain future.

## 19. Portfolio rebalancing (`portfolio/checks.py`)

Targets by class are normalised to sum to 1. With total `V`, new money `N` and
current class values `v_c`: trade `t_c = w_c·(V + N) − v_c` (sums to `N`); drift
`v_c/V − w_c`, out of band above 5 points. With `N > 0`, the new-money-only plan
splits `N` across classes in proportion to their positive gaps, never selling.
