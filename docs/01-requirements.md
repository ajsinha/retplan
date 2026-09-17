# RetPlan — Requirements Specification

Version 1.0 · normative. Keywords **MUST / SHOULD / MAY** per RFC 2119.
Feature IDs referenced here are defined in [00-feature-list.md](00-feature-list.md).

---

## 1. Purpose and scope

RetPlan is a spreadsheet-based retirement planning model. It projects a household's
income, expenses, taxes, debts and investment accounts across a multi-decade horizon,
under deterministic assumptions and under stochastic market simulation, and reports
whether the plan is funded and how badly it fails when it fails.

**In scope:** household cash-flow projection, wrapper-aware account mechanics, a
user-defined tax engine, withdrawal policy engine, market simulation with regimes and
crashes, sensitivity and scenario analysis, interactive dashboards and charts.

**Out of scope:** live market data, portfolio holdings reconciliation, brokerage
integration, jurisdiction-specific tax advice, and any form of financial advice. The
workbook ships with an explicit educational-use disclaimer (F-GOV-4).

## 2. Platform decision (supersedes the original dual-engine goal)

| Tier | Target | Contents |
|---|---|---|
| **Tier A — Full** | LibreOffice Calc 7.4+ (tested on 24.x/25.x), `.ods` | Everything, including the Basic simulation engine, interactive controls, solver macros and script-refreshed charts |
| **Tier B — Portable core** | Excel 2016+ / any ODF-capable engine, `.xlsx` | Formula-only model: full deterministic projection, tax engine, withdrawal policies, capped formula-based Monte Carlo, all charts. No macros, no solvers, reduced trial counts |

- **PR-1 (M).** Tier A MUST be the reference implementation. Where the two tiers can
  disagree, Tier A is correct and Tier B MUST report its limitation on screen.
- **PR-2 (M).** The Tier B workbook MUST produce numerically identical deterministic
  results to Tier A (tolerance `1e-9` relative) for every golden scenario.
- **PR-3 (M).** No feature of the *deterministic* model may depend on macros. Opening the
  file with macros disabled MUST yield a complete, correct projection.
- **PR-4 (M).** Macros MUST be limited to: simulation, solving, control wiring, batch runs,
  import helpers and export. They MUST NOT be the sole source of any displayed formula
  result.
- **PR-5 (M).** The file MUST be fully offline: no external links, no web/DDE queries, no
  network calls from macros, no telemetry.

Portability rules are normative in [02-platform.md](02-platform.md).

## 3. Users and modes

- **U1 Self-directed planner** — needs guided entry, plain-language output, safe defaults.
- **U2 Power user** — needs every assumption exposed, and the ability to override any driver.
- **U3 Adviser/analyst** — needs scenario comparison, auditability, printable reports.
- **U4 Educator** — needs the mechanism visible: every intermediate step on a sheet.

- **FR-MODE-1 (M).** The workbook MUST offer Basic / Advanced / Expert input modes
  (F-UX-6) that hide or reveal input rows via outline grouping and a mode selector, without
  changing any computation.
- **FR-MODE-2 (M).** Hidden advanced inputs MUST retain their values and continue to be used.

## 4. Timeline and conventions

- **FR-TL-1 (M).** The model MUST support an annual or monthly period grid (F-HH-6),
  selected once, with a horizon of up to 80 years (960 monthly periods).
- **FR-TL-2 (M).** Period 0 is the plan start; it MUST accept an arbitrary start date.
- **FR-TL-3 (M).** Cash-flow timing convention (begin / mid / end of period) MUST be a
  single global input that consistently drives discounting, growth application and
  withdrawal ordering.
- **FR-TL-4 (M).** Within any period the calculation order MUST be fixed and documented
  (see [03-data-model.md §6](03-data-model.md)): opening balance → income → mandatory
  distributions → taxes on income → expenses and debt service → shortfall withdrawal
  (grossed up) → contributions/surplus → fees → market return → rebalancing → closing balance.
- **FR-TL-5 (M).** Every monetary output MUST be available in both nominal and real terms,
  switched by one global toggle (F-HH-8); charts and KPIs MUST follow the toggle and label
  themselves accordingly.
- **FR-TL-6 (M).** Ages MUST be computed from birth dates and the period date, not entered
  separately, except where the user enters an age-based rule.

## 5. Household (F-HH-*)

- **FR-HH-1 (M).** 1–4 members, each with: name, birth date, retirement date or age,
  mortality basis, and an "included in plan" flag.
- **FR-HH-2 (M).** Phased retirement MUST be expressible as an FTE percentage path per
  member, scaling employment income and contributions.
- **FR-HH-3 (M).** Life expectancy MUST be selectable as (a) a fixed age, (b) a percentile
  of a user-supplied mortality table (`q_x` by age), or (c) joint-last-survivor derived from
  the same table. The plan horizon MUST default to the resulting age plus a user margin.
- **FR-HH-4 (M).** On a death event the model MUST apply, per configuration: pension and
  annuity continuation percentages, expense reduction percentage, change of tax filing
  unit, transfer of account ownership, and any death-benefit inflow.
- **FR-HH-5 (S).** Dependants MUST support start/end years and a cost stream, and MUST be
  removable without breaking references.

## 6. Income (F-INC-*)

- **FR-INC-1 (M).** Income MUST be entered as an unbounded table of streams; each row
  carries owner, type, gross amount, frequency, growth basis (fixed % / CPI / wage index /
  custom path ID), start age or date, end age or date, taxability category, and a
  pensionable/contributory flag.
- **FR-INC-2 (M).** At least 200 income rows MUST be supported without formula edits.
- **FR-INC-3 (M).** State/social pension MUST support a claim-age election with an actuarial
  adjustment factor table, an indexation rule, and an optional means-test taper
  (`benefit = max(0, base − rate × max(0, other_income − threshold))`).
- **FR-INC-4 (M).** Defined-benefit pensions MUST support accrual-based or fixed amounts,
  a COLA rule of {none, fixed %, CPI, CPI capped at x%, CPI − y%}, survivor continuation %,
  and an optional lump-sum commutation with a commutation factor, routing the lump sum to a
  nominated account and applying the configured tax treatment.
- **FR-INC-5 (S).** Annuity purchase MUST be modelled as: a withdrawal from a nominated
  account at a nominated age, converted at a user-supplied annuity rate (or money's-worth
  factor), producing an income stream with the chosen escalation, joint-life and guarantee
  terms.
- **FR-INC-6 (M).** One-off inflows MUST support a probability; in deterministic mode they
  are applied at expected value or at full value per a user switch, and in stochastic mode
  they are realised by a Bernoulli draw.
- **FR-INC-7 (M).** Rental income MUST net vacancy, management, maintenance and periodic
  capex, and MUST be linked to the corresponding property asset for sale events.

## 7. Expenses (F-EXP-*)

- **FR-EXP-1 (M).** The budget MUST be an unbounded category table with: label, amount,
  frequency, essential/discretionary flag, inflation basis (CPI or CPI + delta or a custom
  path), start age, end age, owner or household scope.
- **FR-EXP-2 (M).** A spending-smile multiplier curve MUST be editable by age band and
  applicable per category by a flag, defaulting to discretionary categories only.
- **FR-EXP-3 (M).** The healthcare module MUST allow a different inflation rate and a
  coverage-age step change.
- **FR-EXP-4 (S).** The long-term-care module MUST support deterministic mode (cost applied
  for a fixed period at a fixed age) and stochastic mode (entry hazard by age, duration
  drawn from a distribution, cost inflated at care inflation, net of an insurance benefit).
- **FR-EXP-5 (M).** One-off and recurring-cycle outflows (e.g. a car every 8 years) MUST be
  expressible without hand-entering each occurrence.
- **FR-EXP-6 (M).** The model MUST compute and display an essential-spending floor per year,
  which dynamic withdrawal policies MUST NOT breach.

## 8. Accounts and wrappers (F-ACC-*)

- **FR-ACC-1 (M).** Accounts MUST be defined in a registry table; the number of accounts is
  limited only by the reserved table size (≥ 40 accounts).
- **FR-ACC-2 (M).** Each account MUST reference a **tax wrapper** defined in a user-editable
  wrapper table with at least these attributes:
  `contribution_deductible (bool/%)`, `growth_taxed_annually (bool)`,
  `growth_tax_schedule`, `withdrawal_taxable_fraction (%)`,
  `withdrawal_tax_schedule`, `contribution_cap_type {none, absolute, %income}`,
  `contribution_cap_value`, `catch_up_age`, `catch_up_amount`,
  `early_withdrawal_age`, `early_withdrawal_penalty_%`,
  `mandatory_distribution_age`, `mandatory_distribution_table_id`,
  `lock_until_age`, `tax_free_lump_sum_%`.
- **FR-ACC-3 (M).** The wrapper abstraction MUST be sufficient to express EET, TEE, TTE and
  ETT regimes without formula changes. Adding a new wrapper MUST require no formula edits.
- **FR-ACC-4 (M).** Employer contributions MUST support tiered match formulas
  (e.g. 100% of first 3%, 50% of next 2%), non-elective contributions, and a vesting
  schedule; unvested balances MUST be excluded from the accessible-wealth KPI.
- **FR-ACC-5 (M).** Taxable accounts MUST track cost basis on an average-cost method,
  splitting withdrawals into return-of-capital and realised gain, with a loss
  carry-forward pool.
- **FR-ACC-6 (M).** Mandatory minimum distributions MUST be computed from a user-editable
  divisor/percentage table by age and forced before any discretionary withdrawal.
- **FR-ACC-7 (M).** Illiquid assets MUST be excluded from the withdrawal engine unless an
  explicit sale event is scheduled, and MUST be flagged separately in net worth.
- **FR-ACC-8 (S).** Wrapper conversions MUST compute the tax cost in the year of conversion
  and MUST support an annual conversion limit and a "fill to top of bracket X" rule.

## 9. Allocation, costs and returns (F-ALLOC-*, F-RET-*)

- **FR-AL-1 (M).** Up to 10 user-defined asset classes with expected return, volatility, and
  a yield/growth split used for taxable drag.
- **FR-AL-2 (M).** A correlation matrix MUST be editable, MUST be validated for symmetry and
  unit diagonal, and MUST be repaired by shrinkage toward the identity when not positive
  semi-definite, with the applied shrinkage reported.
- **FR-AL-3 (M).** Allocation MUST be definable household-wide or per account, MUST sum to
  100% (validated), and MUST support a glidepath of type {none, linear, step-table, rule}.
- **FR-AL-4 (M).** Rebalancing MUST support {none, every period, calendar annual, bands}
  and MUST apply realised-gain tax in taxable accounts when rebalancing.
- **FR-AL-5 (M).** Total cost MUST be the sum of fund TER, platform fee, adviser fee
  (tiered on assets) and an explicit trading cost on turnover, applied to the correct base.
- **FR-RET-1 (M).** Return modes MUST include: fixed, custom path, historical backtest,
  Monte Carlo, and stress path — selected by one control.
- **FR-RET-2 (M).** Monte Carlo MUST be reproducible: the same seed and inputs MUST yield
  identical results across runs, machines and (for the shared algorithm) both tiers.
- **FR-RET-3 (M).** Return distribution MUST be selectable: normal, lognormal, or Student-t
  with user degrees of freedom, variance-matched to the input volatility.
- **FR-RET-4 (M).** The **regime engine** MUST support K ≥ 3 user-defined regimes
  (default bear / normal / bull) with per-regime per-asset mean and volatility, a K×K
  Markov transition matrix (rows validated to sum to 1), a correlation-tightening weight
  per regime, and a starting-state rule of {stationary, specified, random}.
- **FR-RET-5 (M).** The **crash process** MUST be independent of, and additive to, the
  regime engine, parameterised by: annual crash probability, depth distribution
  (triangular min/mode/max or lognormal), duration in periods, a per-asset-class crash beta
  (allowing bonds to gain), and a recovery fraction applied over a recovery window.
- **FR-RET-6 (M).** Deterministic stress paths MUST be user-definable as a pasted return
  series and MUST be applicable starting at any chosen year (F-RET-8, F-RET-9).
- **FR-RET-7 (S).** Historical backtest MUST roll the plan across every feasible start year
  of a pasted series and report the full distribution of outcomes.
- **FR-RET-8 (S).** Bootstrap engines (IID and block/stationary) MUST be available over the
  pasted historical series.
- **FR-RET-9 (M).** Every stochastic mode MUST also drive inflation stochastically when the
  user enables it, preserving the correlation between inflation and asset returns via a
  user-set coefficient.

## 10. Tax engine (F-TAX-*)

- **FR-TAX-1 (M).** All rates, thresholds, allowances and caps MUST be data. No tax
  constant may appear in a formula.
- **FR-TAX-2 (M).** The engine MUST support N independent schedules, each a bracket table of
  (lower bound, rate), applied to a defined base, with an optional allowance, an optional
  allowance taper, and an optional cap.
- **FR-TAX-3 (M).** Income MUST be classified by category and stacked in a user-defined
  order before brackets are applied, so that the marginal rate on the last unit is correct.
- **FR-TAX-4 (M).** The filing unit MUST support individual, joint (combined bands), and
  income-splitting with a divisor.
- **FR-TAX-5 (M).** Tax bands MUST be optionally indexed to inflation; when not indexed,
  fiscal drag MUST emerge naturally.
- **FR-TAX-6 (M).** The **gross-up** of a net spending shortfall into a gross withdrawal MUST
  be solved by exact piecewise-linear inversion of the stacked bracket function.
  Circular references MUST NOT be used and iterative calculation MUST NOT be required.
- **FR-TAX-7 (M).** Each year MUST report: taxable income by category, tax by schedule,
  total tax, effective rate, marginal rate, and the tax paid on withdrawals specifically.
- **FR-TAX-8 (S).** Capital gains MUST support an annual exemption, a holding-period
  discount factor, and loss carry-forward across periods.
- **FR-TAX-9 (C).** Estate tax on terminal wealth MUST be computed from its own schedule.

## 11. Withdrawal policy (F-WD-*)

- **FR-WD-1 (M).** Policies MUST include at minimum: fixed real, fixed nominal, constant
  percentage, guardrails, amortisation/VPW, table-driven, and floor-and-upside; selected by
  one control, with all parameters exposed.
- **FR-WD-2 (M).** Guardrail parameters (upper guard, lower guard, cut %, raise %,
  inflation-skip rule, terminal-years exclusion) MUST all be editable.
- **FR-WD-3 (M).** Withdrawal sourcing MUST follow a user-ordered account priority list, and
  MUST respect: mandatory distributions first, lock-in ages, early-withdrawal penalties,
  liquidity flags, and an optional cash-buffer-first rule.
- **FR-WD-4 (M).** When no source can meet the need, the model MUST record an explicit
  shortfall (amount, year, cumulative), MUST NOT permit negative balances, and MUST NOT
  silently borrow.
- **FR-WD-5 (M).** Surplus income MUST be routed by a user-ordered contribution priority
  respecting wrapper caps, with the remainder to a nominated taxable account.
- **FR-WD-6 (M).** A legacy target MUST be supported; success is then defined as terminal
  real wealth ≥ target.

## 12. Data entry worksheet (F-UX-*) — elaborated

- **FR-UX-1 (M).** Inputs MUST live on dedicated input sheets, organised into labelled
  sections with a fixed row anatomy:
  `[Input ID] [Label] [Value] [Unit] [Allowed range] [Default] [Applies to] [Help] [Status]`.
- **FR-UX-2 (M).** The `Status` cell MUST show OK / MISSING / OUT OF RANGE / IMPLAUSIBLE /
  OVERRIDDEN, driven by validation formulas, and MUST be colour- *and* text-coded.
- **FR-UX-3 (M).** Every input cell MUST carry data validation (type + range or list) and an
  input help message. List sources MUST be named ranges, never literal lists.
- **FR-UX-4 (M).** A `Start Here` sheet MUST provide: a 10-step guided path, hyperlinks to
  each section, the completeness checklist, the sample-data toggle and the run controls.
- **FR-UX-5 (M).** The completeness checklist MUST enumerate every unmet requirement by name
  with a hyperlink to the offending cell, and MUST show a percentage complete.
- **FR-UX-6 (M).** Input cells MUST reject formulas: a check MUST flag any input cell whose
  content is a formula, since that breaks scenario switching.
- **FR-UX-7 (M).** Plausibility warnings MUST fire for at least: real return > 8%, inflation
  > 10% or < −2%, savings rate > 80%, withdrawal rate > 8%, retirement age < 40 or > 80,
  horizon age > 110, allocation not summing to 100%, expenses > income during accumulation
  with no drawdown source, and any correlation outside [−1, 1].
- **FR-UX-8 (M).** Undo-safety: no input action may require deleting rows of a table;
  tables MUST have reserved blank rows pre-formatted and pre-validated.
- **FR-UX-9 (S).** Paste-import sheets MUST accept raw CSV paste and normalise it via
  formulas, with a mapping row and a validation report, without macros.
- **FR-UX-10 (M).** A printed input summary (assumptions appendix) MUST be generated from
  the active scenario automatically.

## 13. Interactivity (F-INT-*, F-SIM-7)

- **FR-INT-1 (M).** A single `Scenario` control cell MUST switch every input the model uses,
  via `INDEX` lookups against scenario columns. Switching MUST require no macro.
- **FR-INT-2 (M).** Tier A MUST provide form controls (sliders/spinners, list boxes, command
  buttons) on the dashboard and control sheet, bound to the same input cells the keyboard
  user edits. Controls MUST be optional sugar, never the only route.
- **FR-INT-3 (M).** Chart selectors (member, account, scenario, percentile set, horizon
  window) MUST drive charts through dynamic named ranges built with `INDEX`/`OFFSET`.
- **FR-INT-4 (M).** When simulation results are stale relative to current inputs, a
  prominent banner MUST say so; staleness MUST be detected by comparing a stored hash of the
  inputs and seed to the live one.
- **FR-INT-5 (M).** Long runs MUST show progress and MUST be cancellable; the document MUST
  be left in a consistent state on cancel.
- **FR-INT-6 (S).** A snapshot action MUST freeze current KPIs into a comparison column.

## 14. Simulation engine (F-SIM-*)

- **FR-SIM-1 (M).** Tier A MUST implement simulation in LibreOffice Basic using in-memory
  arrays, with automatic recalculation disabled and a single bulk write-back of results.
- **FR-SIM-2 (M).** Trial count MUST be user-settable from 100 to 50,000; the default MUST
  be ≤ 2,000 so a first run is fast.
- **FR-SIM-3 (M).** The PRNG MUST be a documented, deterministic, seeded generator
  implemented identically in Basic and in formulas
  (see [04-math-and-simulation.md §2](04-math-and-simulation.md)). `RAND()` MUST NOT be used
  anywhere in the model.
- **FR-SIM-4 (M).** Simulation output MUST include, per trial: terminal real wealth,
  depletion period (or none), minimum funded ratio, worst drawdown, total real spending
  delivered, and total shortfall; plus per-period percentile paths for charting.
- **FR-SIM-5 (M).** Percentiles MUST be computed per period across trials for at least
  P5, P10, P25, P50, P75, P90, P95.
- **FR-SIM-6 (M).** The formula-only fallback (Tier B) MUST implement the same mathematics
  with a capped trial count and MUST state the cap on screen.
- **FR-SIM-7 (M).** Solvers (max sustainable spend, earliest retirement age, required
  contribution) MUST use bisection to a stated tolerance, MUST report the iteration count,
  and MUST fail gracefully with a message when the objective is not bracketed.
- **FR-SIM-8 (S).** Antithetic variates MUST be available as a toggle and MUST halve the
  effective number of independent draws, documented on screen.

## 15. Charting (F-CHT-*)

- **FR-CHT-1 (M).** Every chart MUST be reproducible from a visible data block on a
  `ChartData` sheet; no chart may reference a hidden ad-hoc computation.
- **FR-CHT-2 (M).** The fan chart MUST be constructed as a stacked-area band set
  (base = P5, then differences P10−P5, P25−P10, …) with transparent base series, so it
  renders identically in both engines.
- **FR-CHT-3 (M).** Charts MUST use a colour-blind-safe palette, MUST label axes with units
  and the real/nominal basis, and MUST NOT rely on colour alone to distinguish the median.
- **FR-CHT-4 (M).** Chart series MUST resize automatically with the plan horizon.
- **FR-CHT-5 (S).** Heatmaps MUST be rendered with conditional formatting on a numeric grid,
  with numbers visible, not as an image.
- **FR-CHT-6 (M).** A chart index sheet MUST list every chart, what it shows and how to read
  it.

## 16. Reporting, audit and integrity (F-OUT-*, F-GOV-*)

- **FR-OUT-1 (M).** The dashboard MUST show, at minimum: funded status verdict, success
  probability, median and P10 terminal real wealth, earliest depletion age at P10,
  maximum sustainable real spend, current and required savings rate, and the three largest
  sensitivities.
- **FR-OUT-2 (M).** A reconciliation sheet MUST assert, for every period and every account:
  `closing = opening + contributions + return − fees − withdrawals − taxes_paid_from_account`
  to within `1e-6`, and MUST show a single global PASS/FAIL.
- **FR-OUT-3 (M).** A self-test sheet MUST run at least 25 invariant checks (identities,
  validation states, matrix validity, probability sums, monotonicity of cumulative series)
  and report PASS/FAIL with the failing check named.
- **FR-OUT-4 (M).** The assumptions appendix MUST be generated, not hand-maintained.
- **FR-GOV-1 (M).** The workbook MUST carry a version, a build date, a changelog sheet, and
  a documented limitations list.
- **FR-GOV-2 (M).** Calculation sheets MUST be protected by default (no password), with the
  unlock procedure documented on the `Read Me` sheet.
- **FR-GOV-3 (S).** The workbook MUST be produced by a reproducible build script from
  source, so that a rebuild from the same source yields the same file content.

## 17. Non-functional requirements

- **NFR-1 (M) Performance — deterministic.** A full deterministic recalculation over an
  80-year annual horizon MUST complete in ≤ 2 s on a mid-range 2020s desktop.
- **NFR-2 (M) Performance — simulation.** Tier A MUST complete 2,000 trials × 60 years ×
  5 asset classes in ≤ 20 s, and 10,000 trials in ≤ 120 s, with progress shown.
- **NFR-3 (M) Performance — file.** Delivered file size MUST be ≤ 15 MB; open time ≤ 5 s.
- **NFR-4 (M) Determinism.** Two runs with identical inputs and seed MUST agree to `1e-12`
  relative on every reported KPI.
- **NFR-5 (M) Numerical hygiene.** No circular references. No volatile functions
  (`OFFSET`, `INDIRECT`, `NOW`, `TODAY`, `RAND`, `RANDBETWEEN`) in the calculation core;
  `TODAY()` MAY appear once, on an input sheet, as a default suggestion only.
- **NFR-6 (M) Robustness.** No formula may display an error value to the user. All
  divisions, lookups and logs MUST be guarded, and a deliberate error MUST surface as a
  labelled message, not `#VALUE!`.
- **NFR-7 (M) Scale.** ≥ 200 income rows, ≥ 200 expense rows, ≥ 40 accounts, ≥ 20 loans,
  ≥ 10 asset classes, ≥ 12 scenarios, ≥ 960 periods.
- **NFR-8 (M) Accessibility.** Minimum 11pt body text, contrast ratio ≥ 4.5:1, no meaning
  conveyed by colour alone, every input cell reachable by keyboard in a logical order.
- **NFR-9 (M) Localisation.** Currency symbol, thousands scaling, and date format MUST be
  user-configurable presentation settings that never affect computation. Formulas MUST be
  stored in locale-independent form.
- **NFR-10 (M) Privacy.** No personal identifier is required beyond a display name; the file
  MUST work fully with anonymous labels.
- **NFR-11 (M) Recoverability.** A corrupted or cleared input MUST be restorable from the
  defaults column; a `Restore defaults` path MUST exist for every input section.
- **NFR-12 (S) Maintainability.** Every calculation sheet MUST follow one column grammar
  (period index across columns or down rows, consistently), documented in the data model.
- **NFR-13 (M) Security.** Macros MUST perform no file, shell or network access beyond
  writing into the open document, and the Basic source MUST be readable by the user.

## 18. Acceptance

The release is acceptable when: every **M** requirement is demonstrated; the self-test and
reconciliation sheets report PASS on all golden scenarios; the Tier A/Tier B equivalence
harness reports zero deviations beyond tolerance; and the test plan in
[05-test-plan.md](05-test-plan.md) passes in full.
