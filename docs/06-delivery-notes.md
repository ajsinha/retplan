# RetPlan — Release Notes (web application, v1.0.0)

What the application contains, what was measured, and where it stops. The limits
below are the same ones the application states in the help topic *What this model
does not do* and on the about page.

## What ships

| Item | Detail |
|---|---|
| `retplan/` | The planning engine: plan model, random numbers, markets, tax, projection, metrics, solvers, sample household |
| `portfolio/` | Database layer, repository, Yahoo client, price collector and scheduler, FX, asset classes, checks and rebalancing, paste importer, portfolio builder, projection, stress replays |
| `web/`, `routes/` | The FastAPI application: 13 route classes, Jinja templates, server-rendered SVG charts, the MAYA design in four themes, 28 help topics |
| `schema/` | `sqlite.sql` and `postgres.sql`, nine tables each |
| `config/retplan.toml` | All settings, each overridable by a `RETPLAN_*` variable |
| `tools/` | `fetch_prices.py` (one collection run, for cron), `copy_db.py` (move data between databases) |
| `tests/` | `run_tests.py` (engine) and `test_portfolio.py` (database, portfolios, builder, administration, web) |

## Getting started

```bash
./scripts/setup.sh                      # .venv and dependencies
.venv/bin/python run_retplan_web.py     # http://127.0.0.1:5007
make test                               # both test suites, offline
```

## What a user can do

- **Plan**: build a plan in six wizard steps or in the ten-section editor; keep
  several scenarios and compare them on one seed; see the fixed-return projection
  immediately; run 500–25,000 Monte Carlo trials for success odds with an error
  bar, terminal-wealth and depletion distributions, and the effective returns the
  market model really produces; run the solvers (maximum spend, earliest
  retirement, extra saving), the spending sweep and the tornado; read cash-flow,
  balance-sheet and tax reports and the audit; export and import plans as JSON.
- **Portfolios**: enter holdings by ticker search, paste, or by uploading a broker's
  positions file to the portfolio builder; price them daily from Yahoo in any base
  currency; see allocation, a year of value, and the checks; set a target mix and
  get rebalancing trades; copy a portfolio into a plan account.
- **Project and stress**: Monte Carlo a portfolio over 1–60 years with three return
  models, cash flows, a fee and a goal; replay five historical crises on the
  current mix or open every trial with one; save, reopen and download runs.
- **Securities**: look up any symbol; as administrator, maintain the shared list,
  including manually priced holdings.

## Verification performed

| Check | Result (at the time of writing) |
|---|---|
| Engine suite (`tests/run_tests.py`) | 110 checks passing in about 3 s |
| Portfolio and web suite (`tests/test_portfolio.py`, SQLite) | 158 checks passing in about 3 s |
| Golden scenarios G1–G9 | Exact to 1e-9 relative (G2 lands on zero within 1e-6) |
| Reconciliation | Balance roll-forward ties to 1e-6 relative every period, including employer money and conversions |
| Gross-up | Net delivered equals the need for every taxable fraction, with and without penalty |
| Market statistics | Regime occupancy, crash frequency and depth, calibration, volatility, correlation and the lognormal closed form within tolerance at 40,000 trials (200,000 with `--slow`) |
| Projection | Closed forms for cash, contributions, withdrawals, fees; the three return models agree on the median within 5% |
| Schema parity | Both schema files declare identical tables, columns and indexes |

Timings on the development machine (sample household, 61 years, 6 accounts):

| Operation | Time |
|---|---|
| 10,000 engine trials | 1.4 s |
| Dashboard payload at 2,000 trials | 0.5 s |
| Full analysis (solvers, sweep, tornado) at 2,000 trials | 8.5 s |
| Portfolio projection, 2 assets, 30 years, 5,000 trials | 0.1 s |

## Known limits

### Time and structure

- **Annual periods** in the plan; timing within a year is not modelled. Portfolio
  projections are the exception: they run quarterly. The plan's `timing` field is
  stored but not used.
- **No random lifespan.** The plan is funded for the full horizon; planning age
  decides only when a person's income falls to its survivor share.
- **Everyone retires together** in the earliest-retirement solver, which never
  extends a salary row beyond the age entered.

### Tax

- **Household-level tax.** A couple's income is taxed as one unit, which overstates
  tax where individuals are taxed separately and incomes are uneven.
- **Allowances and tapers are bands** (plus one tapered allowance). That keeps the
  schedule exactly invertible; a credit or means-tested benefit must be approximated
  as a band.
- **Capital gains** are the gain share of a withdrawal times an inclusion rate,
  under the ordinary bands. The `capital` schedule is stored but unused; there is no
  annual gains exemption.
- **The allowance is fixed by income before withdrawals** each year; a withdrawal
  cannot taper its own allowance. The error is second order.
- Wrapper fields `contribution_deductible`, `growth_taxed_annually`,
  `growth_taxable_fraction` and `tax_free_lump_sum` are stored but not used by the
  engine.

### Markets

- **The assumptions drive everything.** Returns, volatility, correlations, regimes
  and crash parameters are the user's.
- **The fixed-return view ignores diversification.** Each asset grows at its own
  typical (median) rate, which errs slightly cautious; the *average* basis errs
  optimistic.
- **Income yield is informational**; dividend and interest drag in taxable accounts
  is not charged separately.

### Not built

- Long-term care, annuity purchase, equity release and bracket-filling
  optimisation. Care costs can be entered as a spending row with a probability; an
  annuity as an income row with the premium taken off a balance.
- Monthly periods; stochastic mortality; the policy's cash buffer.

### Portfolios

- **One year of daily prices** is kept. It estimates volatility and correlation well
  and the mean hardly at all, so expected returns lean on the asset-class
  assumptions, blended with up to 20 years of monthly history where available.
- **Yahoo's endpoints are unofficial** and can change, fail or throttle without
  notice. A symbol that cannot be priced counts as zero.
- **No transaction ledger.** Holdings are a snapshot; the year-of-value chart is a
  back-cast of today's holdings, not a performance record.
- **Currency risk only as far as the stored year**: foreign holdings are converted
  day by day with the stored FX pair.
- **Crisis replays are approximate**: rounded index paths, not a precise record of
  any fund.
- **No tax inside portfolio projections**: flows and growth are pre-tax.

### Operations

- No schema migrations: a schema change means editing both schema files and
  altering or rebuilding the database.
- One administrator account. `local_is_admin` must stay off behind a reverse proxy,
  where every request looks local.
- Simulation results are kept in memory and lost on restart; plans and portfolios
  are not.

### Where the answer will be least reliable

- A large share of wealth in one illiquid asset, such as a business or a home to be
  sold.
- Tax that depends on rules that are not bands, or on two people's separate
  assessments.
- A plan that relies on the exact month of an event.
- A success rate within its error bar of the target.

**Not financial advice.** RetPlan projects the consequences of assumptions the user
supplies; it does not predict markets.
