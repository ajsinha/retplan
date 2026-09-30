# RetPlan — Release Notes (web application, v1.0.0)

What the application contains, what was measured, and where it stops. The limits
below are the same ones the application states in the help topic *What this model
does not do* and on the about page.

## What ships

| Item | Detail |
|---|---|
| `retplan/` | The planning engine: plan model, random numbers, markets, tax, projection, metrics, solvers, sample household |
| `portfolio/` | Database layer, repository, account types, Yahoo client, price collector and scheduler, FX, asset classes, checks and rebalancing, paste importer, portfolio builder, net worth records, projection, stress replays |
| `web/`, `routes/` | The FastAPI application: 16 route classes, Jinja templates, server-rendered SVG charts, the MAYA design in four themes, 28 help topics |
| `schema/` | `sqlite.sql` and `postgres.sql`, thirteen tables each |
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
- **Accounts and portfolios**: keep every account you own and owe - investments,
  cash, property and debts - on the Accounts page, each in its own currency, and
  gather them into any number of portfolios (an account can be in several; a
  portfolio can be made of other portfolios); fill investment accounts by ticker
  search, paste, or by uploading a broker's positions file to the portfolio builder
  (one account, or a file listing several); price them daily from Yahoo and convert
  them into each portfolio's currency; see net worth, investable assets, allocation by class, tax treatment,
  account and owner, a year of value, net worth over time, and the checks; set a
  target mix and get rebalancing trades; link a plan to a portfolio so its accounts
  and loans follow it.
- **Project and stress**: Monte Carlo a portfolio over 1–60 years with three return
  models, cash flows, a fee and a goal; replay five historical crises on the
  current mix or open every trial with one; save, reopen and download runs.
- **Securities**: look up any symbol; as administrator, maintain the shared list,
  including manually priced holdings.

## Changes

### 2026-09-29 - The AI assistant

- **Assistant** (`/assistant`, off by default): questions about your plan answered by a language
  model that takes every figure from RetPlan's own engine through tools - the plan, results,
  portfolios, what-if simulations, levers, claiming, conversions, the spending check, draw
  orders, a rule-based review and the strategy optimiser. Conversations are kept 30 days.
- **Provider and model abstractions** (`web/assistant/providers.py`): `anthropic` (Claude, over
  HTTPS, no SDK) and `fake` - `fake-null` does nothing and needs no key. Switched in
  `config/retplan.yaml` or on **Admin → Assistant settings**, which also sends a test message.
- **Privacy**: names become "Person 1", "Account 2"; amounts rounded; institutions and notes
  never sent; the answer has the names put back. *What is sent* shows it exactly.
- **Safety**: tool arguments checked against their schema; tools and features switched off are
  not offered; the only write is a new scenario, proposed and run only when approved; hourly
  and daily limits; access `everyone` or `admin`.

### 2026-09-29 - Configuration in YAML; the strategy optimiser; the assistant designed

- **Configuration** moved to `config/retplan.yaml`, read by the configurator adopted from
  DishtaYantra (`core/`): dotted keys, `${ENV:default}`, precedence command line >
  environment > a git-ignored `config/retplan.local.yaml` > the file, and live reload. The
  `RETPLAN_*` variables still work. `config/retplan.toml` is gone.
- **Your strategy** (`/strategy`): an optimiser choosing together when to retire, when to claim
  public pensions, how to spend, which account to draw first, whether to convert and how much to
  hold in shares, for one of four objectives; it never adds years of work unless the target
  needs them, reports each change's worth and the alternatives within the noise, and saves as a
  scenario. Settings under `strategy:`.
- Fixed while building it: splitting spending at retirement restarted every-few-years costs
  (a car every eight years fell due at the split); they now keep their cycle - this also
  corrects the suggested draw rate for plans with such costs.
- **AI assistant**: designed (`docs/07-ai-assistant.md`) with its whole configuration under
  `assistant:` (off by default). Not yet built.

### 2026-09-29 - Trading calendars and missing days

Each security follows a trading calendar (`portfolio/calendar.py`): US markets with
every NYSE holiday computed by rule and the special closures, the London Stock
Exchange with England and Wales bank holidays, currencies (weekdays but 1 January
and 25 December), crypto (every day), and plain weekdays for other exchanges. Every
run compares the stored days with the calendar and fetches back to the earliest
missing one; a day Yahoo has no bar for is a known gap (new table `price_gaps`) -
at once if more than ten days old, otherwise after three tries. Scheduled runs skip
symbols already complete for their calendar, so weekend and holiday runs fetch
almost nothing. When a fetch shows a dividend or split has restated adjusted
closes, the older stored ones are rescaled to match. Checked against five years of
live Yahoo data: US, London and crypto histories match their calendars exactly.

### 2026-09-29 - Market data

Securities can be collected every day whether anyone holds them or not: indices,
stocks, ETFs, mutual funds, futures, currencies and crypto. The administrator adds
them on the Market data page (`/market`) by Yahoo search, a pasted list or
ready-made sets, and chooses how much history each keeps (the global year, or 2, 5,
10 or 20 years; a lengthened window is backfilled). Every stored bar now has open,
high, low, close, adjusted close and volume, and any security's bars download as
CSV. Schema: `securities.collect` and `securities.keep_days`; `prices.open`,
`prices.high`, `prices.low`. As before there are no migrations - an older database
must be rebuilt, or have those columns added by hand.

### 2026-09-29 - Accounts, and portfolios as selections of them

- **Accounts** are the building blocks and belong to the workspace, not to a
  portfolio. Each has a type (`portfolio/account_types.py`) in one of four kinds:
  investments (brokerage, 401(k), Roth 401(k), IRA, Roth IRA, HSA, 529, pension
  pot, tax-free savings), cash, property and debts; a name, an owner (you, partner
  or joint), an optional institution, its own **currency** (by default the one most
  accounts use), and a type that sets its tax treatment. The **Accounts** page
  (`/accounts`, Portfolio → Accounts) lists every account by kind with net worth
  over all of them, each counted once, a net-worth chart, and the portfolios each
  is in. Accounts are added and updated through a step-by-step dialog, whose last
  optional step chooses the portfolios it is part of; hand-kept values show their
  age and are flagged after 90 days; debts pay themselves down month by month.
- Every account has its own page (`/accounts/{id}`): holdings for investment
  accounts (add one, paste, or upload positions into it; move a holding to another
  investment account), value or debt details otherwise, and "In portfolios" to
  choose which portfolios it is in. Duplicating an account copies its holdings (the
  copy is in no portfolio); deleting it removes it from every portfolio. The
  free-text holding account is gone.
- A **portfolio** is a selection: any accounts (one account can be in any number
  of portfolios) and/or other portfolios, whose accounts it includes recursively,
  now and later, each counted once. A portfolio cannot contain itself, directly or
  through another. The portfolio page has "Choose accounts", "New account", cards
  marked "through <part>", "Take out of <portfolio>" (the account stays) and a
  "Made of … / Part of …" line. Deleting a portfolio never deletes accounts;
  duplicating one shares its accounts rather than copying them.
- **Live link**: portfolios hold references, so a change to an account is seen at
  once by every portfolio including it and by every plan linked to such a
  portfolio.
- The builder uploads from an account page into that account, or reads a file of
  several accounts (from the nav, the Accounts page or a portfolio's menu),
  confirming a guessed type for each account found, joining existing accounts of
  the same name, and putting them into a new portfolio, an existing one, or no
  portfolio. Search (`Ctrl-K`) finds accounts.
- The portfolio page shows net worth, investable assets (investments plus cash
  accounts), property, debts and the past year; accounts grouped by kind;
  allocation by class, tax treatment, account and owner; net worth over time.
  Projections, stress tests, checks and the target mix work on investable assets.
- Net worth is recorded after each price collection for every account together
  (each once) and for every portfolio, or on demand from a portfolio's menu (which
  records both), with a breakdown by kind. `/networth` shows "Every account" first,
  then each portfolio. Manual snapshots and "to plan" from a snapshot are removed.
- A plan can be **linked** to a portfolio (`plan.portfolio_id`,
  `web/plan_link.py`): every time the plan is read, its accounts and loans are
  brought in line with the portfolio's accounts (those leaving or joining the
  portfolio leave or join the plan), keeping what the plan adds; simulation results
  are dropped when the portfolio's accounts change. "Use in your
  retirement plan" is replaced by linking, unlinking and "Start a plan from it"; the
  quick start can take its accounts from a portfolio and builds a linked plan.
- Database: new `accounts` table (owned by the workspace, with a `currency`, no
  `portfolio_id`); new `portfolio_accounts` (many-to-many) and `portfolio_children`
  (nested portfolios) tables; `holdings.account_id` (NOT NULL, cascading) replaces
  the free-text `account` column and `holdings.portfolio_id`; `snapshots` rows are
  kind `all` (every account) or `portfolio`, with a JSON breakdown. Thirteen tables
  in all. Plan JSON gains `portfolio_id`; ledgers and
  loans gain `account_id`. `/api/portfolios/{id}` adds `net_worth`, `property`,
  `debts` and `accounts` (holdings carry `account` and `account_id`).
- New routes: `/accounts`, `/accounts/dialog`, `/accounts/save`, `/accounts/{aid}`
  and its `delete`, `duplicate`, `portfolios`, `refresh`, `holdings`, `import` and
  `holdings/save`; `/holdings/{hid}/delete`; `/portfolios/{pid}/members`,
  `/portfolios/{pid}/accounts/{aid}/remove`, `/portfolios/{pid}/parts/{cid}/remove`,
  `/portfolios/{pid}/record`; `/portfolios/build?aid=` or `?pid=`.
- **No migration.** A database from before this change must be rebuilt.

## Verification performed

| Check | Result (at the time of writing) |
|---|---|
| Engine suite (`tests/run_tests.py`) | 110 checks passing in about 3 s |
| Portfolio and web suite (`tests/test_portfolio.py`, SQLite) | 199 checks passing in about 18 s |
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
- **Cash, property and debts are typed in.** They are only as current as their last
  update (debts pay down on schedule between updates); property and debts count in
  net worth and are never projected.

### Operations

- No schema migrations: a schema change means editing both schema files and
  altering or rebuilding the database.
- One administrator account. `local_is_admin` must stay off behind a reverse proxy,
  where every request looks local.
- Simulation results are kept in memory and lost on restart; plans, accounts and
  portfolios are not.

### Where the answer will be least reliable

- A large share of wealth in one illiquid asset, such as a business or a home to be
  sold.
- Tax that depends on rules that are not bands, or on two people's separate
  assessments.
- A plan that relies on the exact month of an event.
- A success rate within its error bar of the target.

**Not financial advice.** RetPlan projects the consequences of assumptions the user
supplies; it does not predict markets.
