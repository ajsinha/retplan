# RetPlan — Feature Catalogue

Scannable inventory of what the workbook does. Each feature has an ID, a one-line
description, a MoSCoW priority and a release phase. Normative detail lives in
[01-requirements.md](01-requirements.md).

Phases: **P1** core deterministic model · **P2** stochastic engine + charting ·
**P3** optimisation, advanced tax, extras.

---

## 1. Household & timeline — `F-HH-*`

| ID | Feature | Pri | Phase |
|---|---|---|---|
| F-HH-1 | 1–4 household members, each with birth date, sex-neutral mortality table selector, retirement date, planning horizon | M | P1 |
| F-HH-2 | Independent retirement dates and phased/partial retirement per member (FTE % ramp) | M | P1 |
| F-HH-3 | Life expectancy: fixed age, percentile of a user-supplied mortality table, or joint-last-survivor | M | P1 |
| F-HH-4 | Survivor transition: on first death, apply income continuation %, expense reduction %, tax-filing change, account consolidation | M | P1 |
| F-HH-5 | Dependants (children/parents) with support start/end ages and cost profiles | S | P1 |
| F-HH-6 | Timeline granularity switch: annual or monthly; all outputs consistent under both | M | P1 |
| F-HH-7 | Horizon up to 80 years from plan start; plan start date arbitrary (not just Jan 1) | M | P1 |
| F-HH-8 | Real (today's money) vs nominal display toggle applied globally to every table and chart | M | P1 |
| F-HH-9 | Mid-year/mid-period convention selector (begin / mid / end of period cash flows) | S | P1 |

## 2. Income — `F-INC-*`

| ID | Feature | Pri | Phase |
|---|---|---|---|
| F-INC-1 | Unlimited employment income streams: owner, gross amount, growth rule (fixed %, wage index, custom path), start/end age | M | P1 |
| F-INC-2 | Bonus / commission with variability (% of base, min–max, expected value, optional stochastic draw) | S | P1 |
| F-INC-3 | Equity compensation: grant schedule, vesting cliff + ramp, price growth assumption, sale policy (sell-on-vest / hold N years) | S | P2 |
| F-INC-4 | Self-employment / business income, with expense ratio and separate contribution treatment | M | P1 |
| F-INC-5 | Career breaks, sabbaticals, redundancy periods, re-entry salary haircut | S | P1 |
| F-INC-6 | Rental property income: gross rent, vacancy %, management %, maintenance %, periodic capex, rent indexation | M | P1 |
| F-INC-7 | State / social pension: eligibility age, claim-age election, actuarial adjustment table (early/late factors), indexation rule, means-test taper table | M | P1 |
| F-INC-8 | Defined-benefit pension: accrual formula or fixed amount, start age, COLA rule (full/capped/fixed/none), survivor continuation %, lump-sum commutation option with commutation factor | M | P1 |
| F-INC-9 | Annuities: immediate/deferred, fixed/escalating/index-linked, single/joint life, guarantee period, purchase from a nominated account at a nominated age | S | P2 |
| F-INC-10 | Royalties, trust distributions, alimony/maintenance, disability and other transfer payments (generic recurring stream with own tax category) | S | P1 |
| F-INC-11 | One-off inflows: inheritance, business sale, property sale, gift, insurance payout — each with amount, year, probability and tax category | M | P1 |
| F-INC-12 | Home equity release: downsizing (sale year, net proceeds, new housing cost) and reverse mortgage (draw schedule, rate, LTV cap) | C | P3 |
| F-INC-13 | Post-retirement part-time / consulting income with earnings-test interaction against state pension | S | P2 |

## 3. Expenses — `F-EXP-*`

| ID | Feature | Pri | Phase |
|---|---|---|---|
| F-EXP-1 | Category budget (unlimited rows) with essential/discretionary flag and category-specific inflation delta | M | P1 |
| F-EXP-2 | Retirement spending "smile": user-editable multiplier curve by age (go-go / slow-go / no-go) applied per category | M | P1 |
| F-EXP-3 | Per-category start/end ages (e.g. commuting ends at retirement, travel ends at 80) | M | P1 |
| F-EXP-4 | Healthcare module: pre-/post-public-coverage age, premium growth rate distinct from CPI, out-of-pocket cap | M | P1 |
| F-EXP-5 | Long-term care module: entry probability by age, duration distribution, annual cost, care inflation, insurance offset, stochastic or deterministic mode | S | P2 |
| F-EXP-6 | Lumpy one-off outflows: vehicles (with replacement cycle), home renovation, weddings, relocations — with recurrence rule | M | P1 |
| F-EXP-7 | Education costs per dependant: start year, duration, annual cost, education inflation | S | P1 |
| F-EXP-8 | Housing cost engine: rent vs own, property tax, insurance, HOA/service charge, maintenance % of value, and change-of-home events | M | P1 |
| F-EXP-9 | Charitable giving / legacy gifting schedule, optionally tax-deductible | C | P2 |
| F-EXP-10 | Spending floor and ceiling used by dynamic withdrawal rules (essential floor never cut) | M | P2 |
| F-EXP-11 | Expense shock overlay: probability-weighted unexpected expense per year (mean, sd, frequency) for the stochastic engine | S | P2 |

## 4. Debt — `F-DEBT-*`

| ID | Feature | Pri | Phase |
|---|---|---|---|
| F-DEBT-1 | Unlimited loans: balance, rate, term, repayment type (amortising / interest-only / bullet / offset), start date | M | P1 |
| F-DEBT-2 | Full amortisation schedule with extra payments, lump-sum prepayment and payoff date detection | M | P1 |
| F-DEBT-3 | Variable-rate loans linked to the model's rate path, with reset frequency and caps/floors | S | P2 |
| F-DEBT-4 | Refinance event: new rate/term/fees at a chosen year | C | P3 |
| F-DEBT-5 | Payoff-vs-invest comparison: marginal after-tax return differential and net-worth delta | S | P2 |
| F-DEBT-6 | Deductible-interest flag feeding the tax engine | S | P2 |

## 5. Accounts & tax wrappers — `F-ACC-*`

| ID | Feature | Pri | Phase |
|---|---|---|---|
| F-ACC-1 | Generic account registry: name, owner, wrapper type, opening balance, cost basis, currency, liquidity flag | M | P1 |
| F-ACC-2 | **User-defined tax wrappers** on the EET/TEE/TTE/ETT taxonomy: is the contribution deductible, is growth taxed annually, are withdrawals taxable, at which schedule, and what fraction is taxable | M | P1 |
| F-ACC-3 | Per-wrapper rules: contribution cap (absolute or % of income), catch-up uplift from age X, early-withdrawal penalty %/age, mandatory minimum distribution table from age Y, lock-in age | M | P1 |
| F-ACC-4 | Employer contributions: match formula (tiered %), non-elective %, vesting schedule (cliff/graded), true-up | M | P1 |
| F-ACC-5 | Cost-basis tracking for taxable accounts (average cost), realised/unrealised gain split, loss carry-forward | M | P2 |
| F-ACC-6 | Real assets: primary residence, investment property, land — with appreciation, transaction costs, and optional sale events | M | P1 |
| F-ACC-7 | Illiquid / alternative holdings: private business, collectibles, crypto — separate return and volatility, haircut on valuation | S | P2 |
| F-ACC-8 | Cash reserve / emergency fund with target months-of-expenses and refill policy | M | P1 |
| F-ACC-9 | Inter-account transfers with rules: wrapper-conversion events (taxable transfer between wrappers), annual limit, tax cost computed | S | P2 |
| F-ACC-10 | Multi-currency accounts: FX rate path, translation to base currency, optional FX volatility in simulation | C | P3 |

## 6. Asset allocation & costs — `F-ALLOC-*`

| ID | Feature | Pri | Phase |
|---|---|---|---|
| F-ALLOC-1 | User-defined asset classes (up to 10): expected real return, volatility, income yield vs capital growth split | M | P1 |
| F-ALLOC-2 | Full correlation matrix between asset classes, validated for symmetry and positive semi-definiteness | M | P2 |
| F-ALLOC-3 | Allocation set per account or one household-level policy, with drift and rebalancing | M | P1 |
| F-ALLOC-4 | Glidepath: linear to target, step table by age, rule-based (e.g. `equity% = k − age`), rising-equity glidepath, or none | M | P1 |
| F-ALLOC-5 | Rebalancing policy: none / annual / threshold bands (±x%), with tax cost of rebalancing in taxable accounts | M | P2 |
| F-ALLOC-6 | Fee stack: fund TER, platform fee, advisory fee (tiered by AUM), trading costs, each deducted in the correct period | M | P1 |
| F-ALLOC-7 | Asset *location* option: hold high-yield assets preferentially in sheltered wrappers | C | P3 |
| F-ALLOC-8 | Bucket / time-segmentation strategy: N buckets with horizon, allocation and refill rules | S | P2 |

## 7. Returns, regimes & shocks — `F-RET-*`

| ID | Feature | Pri | Phase |
|---|---|---|---|
| F-RET-1 | Deterministic fixed return per asset class | M | P1 |
| F-RET-2 | User-supplied deterministic return path (paste a year-by-year series) | M | P1 |
| F-RET-3 | Historical backtest: paste a historical series, roll the plan through every start year, report the distribution of outcomes | M | P2 |
| F-RET-4 | Monte Carlo, reproducible: deterministic PRNG with a user seed, so identical results in Excel and LibreOffice | M | P2 |
| F-RET-5 | Return distributions: normal, lognormal, or fat-tailed Student-t with user-set degrees of freedom | M | P2 |
| F-RET-6 | **Market-regime engine**: user-defined regimes (bull / normal / bear, extensible), each with own mean, volatility and correlation scaling, driven by a Markov transition matrix with editable persistence | M | P2 |
| F-RET-7 | **Random crash process**: annual crash probability, crash depth distribution (min/mode/max or lognormal), multi-period drawdown shape, and a recovery-speed parameter | M | P2 |
| F-RET-8 | Deterministic stress paths: user-defined crash-at-retirement, lost-decade, stagflation, and any custom path, plus "worst historical N-year start" | M | P2 |
| F-RET-9 | Sequence-of-returns test: force the worst k years to the start of retirement and report the damage | M | P2 |
| F-RET-10 | Mean reversion / autocorrelation parameter on returns; volatility clustering option | C | P3 |
| F-RET-11 | Bootstrap engines: IID bootstrap and block bootstrap (block length editable) over the pasted historical series | S | P2 |
| F-RET-12 | Correlated multi-asset draws via Cholesky decomposition computed in-sheet | M | P2 |
| F-RET-13 | Regime-conditional inflation and bond/equity correlation flip in the bear regime | C | P3 |

## 8. Inflation & indexation — `F-INF-*`

| ID | Feature | Pri | Phase |
|---|---|---|---|
| F-INF-1 | Base inflation rate, or user-supplied path, or stochastic inflation (mean, sd, persistence) | M | P1 |
| F-INF-2 | Category inflation deltas (healthcare, education, care, housing) | M | P1 |
| F-INF-3 | Wage growth as its own series, decoupled from price inflation | M | P1 |
| F-INF-4 | Indexation rules per income stream: full CPI, capped CPI, fixed %, none, or CPI-minus | M | P1 |
| F-INF-5 | Tax-band indexation flag (bands frozen vs indexed) — models fiscal drag | S | P2 |

## 9. Tax engine — `F-TAX-*`

| ID | Feature | Pri | Phase |
|---|---|---|---|
| F-TAX-1 | Fully user-editable progressive bracket tables, multiple independent schedules (earned, pension, interest, dividend, capital gain, other) | M | P1 |
| F-TAX-2 | Filing-unit switch: individual, joint, or split-income with a transfer ratio | M | P1 |
| F-TAX-3 | Allowances, deductions and credits, including tapered/withdrawn allowances above a threshold | M | P1 |
| F-TAX-4 | Flat surtaxes, social/health contributions, and local/state add-ons expressed as % of a chosen base with own caps | M | P1 |
| F-TAX-5 | Capital gains: annual exemption, holding-period discount, loss carry-forward, deemed-disposal option | M | P2 |
| F-TAX-6 | Withdrawal taxability by wrapper, with partial-taxable fractions (e.g. 25% tax-free lump sum, or annuity exclusion ratio) | M | P1 |
| F-TAX-7 | Mandatory minimum distributions driven by a user-editable divisor table | M | P2 |
| F-TAX-8 | Wrapper-conversion (Roth-style) planner: convert up to the top of a chosen bracket each year, with break-even analysis | S | P3 |
| F-TAX-9 | Bracket-filling withdrawal optimiser: fill to a target marginal rate before moving to the next account | S | P3 |
| F-TAX-10 | Tax gross-up solved exactly: net spending need converted to gross withdrawal by piecewise-linear bracket inversion (no circular references) | M | P2 |
| F-TAX-11 | Estate / inheritance tax on terminal wealth, with allowance and rate table | C | P3 |
| F-TAX-12 | Effective and marginal tax rate reported every year, with a full tax reconciliation row | M | P2 |

## 10. Withdrawal & spending policy — `F-WD-*`

| ID | Feature | Pri | Phase |
|---|---|---|---|
| F-WD-1 | Fixed real spending (inflation-adjusted) | M | P1 |
| F-WD-2 | Fixed nominal spending | M | P1 |
| F-WD-3 | Constant percentage of portfolio | M | P2 |
| F-WD-4 | Guardrails (Guyton–Klinger style): editable upper/lower guard %, raise/cut %, prosperity and capital-preservation rules, inflation-skip rule | M | P2 |
| F-WD-5 | Amortisation-based / VPW: annuitise remaining portfolio over remaining horizon at an assumed rate | M | P2 |
| F-WD-6 | Required-minimum-style table-driven withdrawal | S | P2 |
| F-WD-7 | Floor-and-upside: guaranteed floor from pensions/annuities, discretionary from portfolio | S | P2 |
| F-WD-8 | Ratchet rule: allow permanent raises after strong markets, never cut below floor | C | P3 |
| F-WD-9 | Configurable withdrawal *ordering* across accounts, drag-to-reorder via priority numbers, with penalty/lock-in awareness | M | P1 |
| F-WD-10 | Cash-buffer-first rule: spend from cash in down years, refill in up years | S | P2 |
| F-WD-11 | Surplus policy: where excess income is invested, in what priority (match → cap-limited wrappers → taxable) | M | P1 |
| F-WD-12 | Legacy target: stop-at-zero vs leave a real bequest of X; success redefined accordingly | M | P2 |

## 11. Results, KPIs & risk — `F-RISK-*`, `F-GOAL-*`

| ID | Feature | Pri | Phase |
|---|---|---|---|
| F-GOAL-1 | Success probability, depletion-age distribution, and shortfall magnitude/duration when it fails | M | P2 |
| F-GOAL-2 | Maximum sustainable spend at a chosen confidence level (solved in-sheet, no Solver dependency) | M | P2 |
| F-GOAL-3 | Earliest feasible retirement age at a chosen confidence level | M | P2 |
| F-GOAL-4 | Funded ratio: PV(assets + future income) ÷ PV(future spending) at a chosen discount rate | M | P2 |
| F-GOAL-5 | Required savings rate / contribution gap to reach the goal | M | P1 |
| F-GOAL-6 | Coast number and FI number (portfolio at which no further saving is required) | S | P2 |
| F-GOAL-7 | Real terminal wealth percentiles (P5/P25/P50/P75/P95) and expected legacy after estate tax | M | P2 |
| F-RISK-1 | Worst-case drawdown, longest underwater period, and worst 10-year real return experienced in the plan | S | P2 |
| F-RISK-2 | Tornado sensitivity chart: ±x% on each driver, ranked by impact on the primary KPI | M | P2 |
| F-RISK-3 | Two-way sensitivity heatmap (e.g. retirement age × spending) computed without Excel Data Tables | M | P2 |
| F-RISK-4 | Break-even finder: the value of any single driver at which the plan just succeeds | S | P3 |
| F-RISK-5 | Longevity risk view: success probability conditional on living to 85 / 90 / 95 / 100 | S | P2 |

## 12. Data entry experience — `F-UX-*`

| ID | Feature | Pri | Phase |
|---|---|---|---|
| F-UX-1 | **Dedicated multi-section Input workbook area**: a guided `Start Here` sheet plus themed input sheets (Household, Income, Expenses, Accounts, Markets, Tax, Policy), never mixing inputs into calculation sheets | M | P1 |
| F-UX-2 | Strict cell conventions: blue = you type, grey = calculated & locked, green = choose from list, amber = optional/advanced, red = error | M | P1 |
| F-UX-3 | Every input row carries: label, unit, allowed range, default, an inline help string and a "why this matters" note | M | P1 |
| F-UX-4 | Data validation on every input cell: type, range, enumerated lists sourced from lookup tables, cross-field rules (e.g. retirement age > current age) | M | P1 |
| F-UX-5 | Completeness checklist that lists exactly what is still missing or implausible, with jump links | M | P1 |
| F-UX-6 | Progressive disclosure: Basic / Advanced / Expert input modes; advanced rows collapse into grouped outlines | M | P1 |
| F-UX-7 | Sample-data toggle: load a fully worked example household, then clear it in one step | M | P1 |
| F-UX-8 | Input audit: flags stale, overridden or hard-coded values, and any formula typed into an input cell | S | P2 |
| F-UX-9 | Bulk import sheets for CSV paste: historical returns, account balances, transaction/budget exports, mortality tables | M | P2 |
| F-UX-10 | Unit and currency configuration: symbol, thousands scaling, date format, period convention — presentation only, never affecting maths | M | P1 |
| F-UX-11 | Print/PDF-ready layouts with defined print ranges for every report sheet | S | P2 |
| F-UX-12 | Accessibility: no information by colour alone, minimum 11pt, high-contrast palette, logical tab order, screen-reader-friendly headers | M | P1 |

## 13. Interactivity — `F-INT-*`

| ID | Feature | Pri | Phase |
|---|---|---|---|
| F-INT-1 | Scenario switch: one control cell selects the active scenario column; the whole model, every chart and every KPI recalculates instantly | M | P1 |
| F-INT-2 | Named scenarios (Base / Bear / Bull / custom, unlimited) stored as parallel input columns, with side-by-side comparison and delta columns | M | P1 |
| F-INT-3 | Live "what-if" sliders implemented portably: spinner-free stepper cells (`+`/`−` increment cells), validated dropdowns and typed overrides that drive the model directly | M | P1 |
| F-INT-4 | Chart drill controls: dropdowns select which member, account, scenario, percentile band or date window a chart displays, via dynamic named ranges | M | P2 |
| F-INT-5 | Percentile band selector on fan charts (e.g. show 5/25/50/75/95 or 10/50/90) | S | P2 |
| F-INT-6 | Manual-recalculation mode for heavy simulation, with a visible "results are stale" banner and a recalculation instruction | M | P2 |
| F-INT-7 | Snapshot / freeze: copy current results to a values-only comparison column to compare against later edits | S | P2 |
| F-INT-8 | Optional, strictly non-essential macro layer shipped as two separate add-ons (VBA for Excel, Basic for LibreOffice) for convenience only — the workbook is fully functional without it | C | P3 |

## 14. Charting — `F-CHT-*`

| ID | Feature | Pri | Phase |
|---|---|---|---|
| F-CHT-1 | Net-worth projection with **percentile fan chart** (stacked-area band construction, portable to both engines) | M | P2 |
| F-CHT-2 | Spaghetti plot of N sampled simulation paths with the median highlighted | M | P2 |
| F-CHT-3 | Stacked-area balance composition by wrapper/asset class over time | M | P1 |
| F-CHT-4 | Annual cash-flow waterfall: income → tax → spending → contributions → net portfolio change | M | P2 |
| F-CHT-5 | Income-sources stacked chart across retirement (pension, annuity, portfolio, work, other) | M | P1 |
| F-CHT-6 | Terminal-wealth histogram plus cumulative distribution of depletion age | M | P2 |
| F-CHT-7 | Success-probability curve vs spending level, and vs retirement age | M | P2 |
| F-CHT-8 | Tornado chart of driver sensitivities | M | P2 |
| F-CHT-9 | Heatmap grid (retirement age × spend, or allocation × spend) rendered with conditional formatting | M | P2 |
| F-CHT-10 | Drawdown / underwater chart of the portfolio in real terms | S | P2 |
| F-CHT-11 | Regime timeline ribbon showing which regime each simulated year was in for the displayed path | S | P2 |
| F-CHT-12 | Tax composition chart: effective rate and tax by type over time | S | P2 |
| F-CHT-13 | Contribution vs growth attribution chart (how much of the balance is money in vs return) | S | P2 |
| F-CHT-14 | In-cell micro-charts using `REPT()` bars and conditional-format data bars as a portable substitute for sparklines | M | P1 |
| F-CHT-15 | Gauge-style KPI tiles (funded ratio, success %) built from bar charts, not unsupported shapes | S | P2 |
| F-CHT-16 | Every chart driven by dynamic named ranges so series resize with the horizon without manual edits | M | P2 |

## 15. Reporting & governance — `F-OUT-*`, `F-GOV-*`

| ID | Feature | Pri | Phase |
|---|---|---|---|
| F-OUT-1 | Executive dashboard: KPIs, three headline charts, plan verdict, top three risks | M | P1 |
| F-OUT-2 | Year-by-year cash-flow statement (every inflow, outflow, tax and transfer) | M | P1 |
| F-OUT-3 | Year-by-year balance sheet by account and wrapper | M | P1 |
| F-OUT-4 | Tax detail schedule per year per person | M | P2 |
| F-OUT-5 | Assumptions appendix auto-generated from the active scenario | M | P1 |
| F-OUT-6 | Reconciliation sheet proving sources = uses and balance roll-forward to the cent, every period | M | P1 |
| F-OUT-7 | Scenario comparison report with deltas on every KPI | S | P2 |
| F-GOV-1 | Version number, changelog sheet, and a model-integrity self-test that reports PASS/FAIL | M | P1 |
| F-GOV-2 | Fully offline: no web queries, no external links, no telemetry, no PII required | M | P1 |
| F-GOV-3 | Sheet protection on calculation areas (documented, no password by default) with an explicit unlock procedure | M | P1 |
| F-GOV-4 | Educational-use disclaimer and a stated list of model limitations | M | P1 |
| F-GOV-5 | Workbook built from source by a reproducible build script, not hand-edited | S | P1 |

## 16. Simulation engine & macro layer — `F-SIM-*`

Primary target is LibreOffice Calc, where a Basic engine does the heavy lifting. See
[02-platform.md](02-platform.md) for the two-tier model and
[04-math-and-simulation.md](04-math-and-simulation.md) for the algorithms.

| ID | Feature | Pri | Phase |
|---|---|---|---|
| F-SIM-1 | LibreOffice Basic Monte Carlo engine: in-memory arrays, bulk write-back, automatic calculation suspended during the run | M | P2 |
| F-SIM-2 | Configurable trial count (100 – 50,000) with a live progress indicator and a Cancel path | M | P2 |
| F-SIM-3 | Deterministic seeded PRNG shared by the macro engine and the formula engine, producing bit-identical streams | M | P2 |
| F-SIM-4 | Formula-only fallback engine (capped trials) so the file still simulates with macros disabled or in Excel | M | P2 |
| F-SIM-5 | Solver macros: max sustainable spend, earliest retirement age, required contribution — by bisection on the full model | M | P2 |
| F-SIM-6 | Batch runner: execute every scenario in sequence and populate the comparison report | S | P3 |
| F-SIM-7 | Interactive controls: sliders/spinners, buttons, and a scenario dialog, all wired to input cells | M | P2 |
| F-SIM-8 | Results cache: simulation output stored as values with a seed + input hash, so staleness is detectable | M | P2 |
| F-SIM-9 | Per-path export: dump any single simulated path to a sheet for inspection and charting | S | P2 |
| F-SIM-10 | Antithetic variates and optional Latin-hypercube stratification to cut variance at a given trial count | C | P3 |
