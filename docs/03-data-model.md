# RetPlan — Data Model and Calculation Order

## 1. Sheet inventory

| # | Sheet | Kind | Purpose |
|---|---|---|---|
| 1 | `Read Me` | doc | Version, disclaimer, limitations, unlock procedure |
| 2 | `Start Here` | input/nav | Guided 10 steps, completeness checklist, run buttons |
| 3 | `In-Household` | input | Members, dates, retirement, mortality, survivor rules |
| 4 | `In-Income` | input | Income stream table (200 rows) |
| 5 | `In-Expenses` | input | Expense category table (200 rows) + smile curve |
| 6 | `In-Debt` | input | Loans (20 rows) |
| 7 | `In-Accounts` | input | Account registry (40 rows) + contribution rules |
| 8 | `In-Wrappers` | input | Tax wrapper definitions (12 rows × 16 attributes) |
| 9 | `In-Markets` | input | Asset classes, correlations, regimes, crash process, fees |
| 10 | `In-Tax` | input | Schedules, brackets, allowances, surtaxes, CG rules |
| 11 | `In-Policy` | input | Withdrawal policy, ordering, surplus routing, goals |
| 12 | `Scenarios` | input | Named scenario columns and the active-scenario switch |
| 13 | `Lists` | hidden | Enumerations, keys, lookup tables, mortality, MRD divisors |
| 14 | `Eng-Timeline` | calc | Per-period spine: dates, ages, indices, phase flags |
| 15 | `Eng-Income` | calc | Per-period income by tax category |
| 16 | `Eng-Expense` | calc | Per-period expenses: essential, discretionary, one-offs |
| 17 | `Eng-Debt` | calc | Per-loan amortisation and aggregate debt service |
| 18 | `Eng-Tax` | calc | Stacked bracket tax, gross-up inversion, effective/marginal |
| 19 | `Eng-Portfolio` | calc | Wrapper ledgers: roll-forward, returns, fees, flows |
| 20 | `Eng-Withdraw` | calc | Need, MRD, sourcing order, penalties, shortfall |
| 21 | `Sim-Control` | calc | Seed, trials, mode, input hash, staleness flag |
| 22 | `Sim-Results` | data | Per-trial summary statistics written by the macro |
| 23 | `Sim-Paths` | data | Per-period percentile bands and sampled paths |
| 24 | `ChartData` | calc | Every chart's source block, one block per chart |
| 25 | `Dashboard` | output | KPIs, headline charts, verdict, controls |
| 26 | `Rep-Cashflow` | output | Year-by-year cash-flow statement |
| 27 | `Rep-Balance` | output | Year-by-year balance sheet by account and wrapper |
| 28 | `Rep-Tax` | output | Year-by-year tax detail |
| 29 | `Rep-Assumptions` | output | Auto-generated assumptions appendix |
| 30 | `Audit` | output | Reconciliation identities and self-test checks |

## 2. Layout grammar

- **DR-1.** Input tables run **down** in rows; the header row is frozen; row 1 of every
  table is an ID column that never changes.
- **DR-2.** Engine sheets run **one period per row**, period index `t = 0..T` in column A,
  variables across columns. This matches the per-trial numpy arrays exactly.
- **DR-3.** Every engine column has a stable symbolic name recorded in `Lists`; the builder
  resolves names to column letters, so inserting a column never breaks a formula.
- **DR-4.** Reserved blank rows in every input table are pre-formatted and pre-validated;
  users never insert rows.
- **DR-5.** All monetary inputs are in base currency, nominal, as at the plan start date,
  unless the row's `Basis` cell says `real`.

## 3. Core tables (abridged schema)

### `In-Income`
`ID | Enabled | Owner | Label | Category | Amount | Basis(real/nominal) | Frequency | Growth basis {fixed,CPI,wage,path} | Growth % | Path ID | Start {age|date} | End {age|date} | Taxable schedule | Taxable fraction % | Pensionable | Survivor continuation % | Means-tested | Probability | Notes`

### `In-Expenses`
`ID | Enabled | Label | Category | Amount | Basis | Frequency | Essential? | Inflation basis | Inflation delta % | Smile applies? | Start | End | Recurrence years | Owner/scope | Probability | Notes`

### `In-Accounts`
`ID | Enabled | Owner | Label | Wrapper ID | Opening balance | Cost basis | Allocation set ID | Liquidity {liquid, illiquid} | Withdrawal priority | Contribution priority | Employee contribution rule | Employer match tiers | Vesting schedule ID | Currency | Notes`

### `In-Wrappers`
`ID | Label | Contribution deductible % | Growth taxed annually? | Growth schedule | Growth taxable fraction % | Withdrawal taxable fraction % | Withdrawal schedule | Cap type | Cap value | Catch-up age | Catch-up amount | Early withdrawal age | Early penalty % | MRD age | MRD table ID | Lock-until age | Tax-free lump sum %`

### `In-Markets`
- Asset class table: `ID | Label | Expected return % | Volatility % | Income yield % | TER % | Turnover %`
- Correlation matrix: N×N, validated.
- Regime table: `Regime | Label | Return multiplier/offset per asset | Volatility multiplier | Correlation tightening w | Transition row p(k→1..K)`
- Crash block: `Annual probability | Depth min/mode/max | Duration periods | Recovery fraction | Recovery periods | Per-asset crash beta`
- Fee block: platform %, adviser tiers, trading cost bps.

### `In-Tax`
- Schedule table: `Schedule ID | Label | Base | Allowance | Allowance taper start | Taper rate | Cap | Indexed?`
- Bracket table: `Schedule ID | Band # | Lower bound | Rate %`
- Stacking order table: `Category | Order | Schedule ID | Inclusion %`
- Capital-gains block, surtax block, estate block.

### `In-Policy`
Withdrawal policy ID and all policy parameters; ordering lists; surplus routing;
legacy target; confidence level; guardrail parameters; cash-buffer rule.

## 4. Named-range conventions

`IN_<sheet>_<field>` for scalars, `TBL_<name>` for whole tables, `COL_<table>_<field>` for
table columns, `ENG_<sheet>_<var>` for engine columns, `SIM_<var>` for simulation blocks.

- **DR-6.** Every named range MUST be document-scoped and MUST be listed on `Lists`.
- **DR-7.** Scenario switching MUST work by `INDEX(scenario_block, row, active_scenario)`,
  so the engine reads exactly one set of values at a time.

## 5. Units

| Quantity | Unit | Convention |
|---|---|---|
| Money | base currency | positive = inflow to the household |
| Rates | decimal fraction stored, percent displayed | 0.045 shows as 4.50% |
| Returns | per period, simple (not log) at the interface; log internally |
| Volatility | annualised standard deviation of simple returns |
| Ages | years, decimal allowed | computed from dates |
| Periods | integer index from 0 |

## 6. Calculation order within a period `t`

This order is normative for both the formula engine and the numpy engine.

```
1.  opening balances per wrapper, opening debt balances
2.  index update: CPI_t, wage_t, category price levels
3.  gross income by category (employment, pension, rental, other), survivor rules applied
4.  mandatory distributions (MRD) forced out of affected wrappers
5.  expense requirement: essential + discretionary (smile, category inflation, one-offs)
6.  debt service: interest, scheduled principal, extra payments
7.  tax on income excluding any new discretionary withdrawal
8.  net cash position = income + MRD − tax − expenses − debt service
9.  if deficit: withdrawal need, grossed up by exact bracket inversion, sourced by priority,
    applying penalties, lock-in, liquidity and the cash-buffer rule
10. if surplus: contributions routed by priority, respecting caps and employer match
11. fees charged on the post-flow balance
12. market return applied per asset class, per wrapper, using the period's regime and crash
13. annual taxation of growth for wrappers that require it
14. rebalancing to the glidepath target, realising gains where applicable
15. closing balances; record shortfall, funded ratio, drawdown, KPIs
```

- **DR-8.** Flows are applied before return when the timing convention is `begin`, after
  return when `end`, and half-weighted when `mid`.
- **DR-9.** The reconciliation identity
  `closing = opening + inflows − outflows + return − fees − taxes_from_account`
  MUST hold to `1e-6` for every wrapper and every period.
