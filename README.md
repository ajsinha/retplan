# RetPlan — retirement planning you can audit

A self-hosted retirement planner and portfolio tracker. It projects a household's
income, spending, debt, tax and investments year by year, tests the plan against
thousands of simulated market histories, tracks real portfolios priced daily, and
projects them ten or more years ahead.

It is **jurisdiction-agnostic**: no country, currency, tax code or account type is
hard-coded. Tax is a table of bands you type; accounts are *tax wrappers* that say
when money is taxed - in, while it grows, or on the way out. And it is
**auditable**: every plan carries a reconciliation that proves money in equals
money out in every year of every simulated future.

## Quick start

```bash
./scripts/setup.sh                      # venv + dependencies
.venv/bin/python run_retplan_web.py     # http://127.0.0.1:5007
make test                               # engine, database, portfolio and web tests
```

Then either press **Start in two minutes** (the quick-start wizard), explore the
sample household on the dashboard, or add your accounts under **Portfolio →
Accounts** - one by one, or upload a broker's export listing several with **Import a
file of several accounts** - and gather them into portfolios under **Portfolios**.

The administrator account is `admin` / `retplan-dev-admin`. Change it (shield icon
→ *Change password*) before anyone else can reach the app; until you do, every
page you see as administrator says so.

## What it does

| | |
|---|---|
| **Quick start** (`/start`) | six short steps - you, income, savings, spending, assumptions, review - build a complete plan, with the plan so far summarised beside each step; savings are taken from a portfolio (asking only what goes into each account; the plan stays linked to it) or asked by account type - 401(k), Roth 401(k), IRA, Roth IRA, HSA, brokerage, savings, pension pot, tax-free savings - each with its own tax rules, limits and required withdrawals; US federal tax by default |
| **Scenarios** (`/scenarios`, `/compare`) | several named plans per workspace; compare odds, wealth and tax side by side on one seed |
| **Dashboard** | the verdict with success odds and their error bar, KPI tiles, a **suggested draw rate** worked out for your plan (with cautious and bold rates at the guardrail odds), up to eight charts; 500-25,000 trials; solvers for maximum spend, earliest retirement and saving needed |
| **Plan editor** | income, spending, debt, accounts, care and conversions as plain-language cards; adding one asks what it is, then a few questions a step at a time with sensible answers filled in; pause an item to leave it out without losing it; a table view for bulk edits. Household, tax wrappers, tax, markets and withdrawal policy are short forms |
| **Reports / Audit** | year-by-year cash flow, balance sheet and tax; the reconciliation audit |
| **Accounts** (`/accounts`) | every account you own or owe - investments (brokerage, 401(k), IRA, Roth, HSA, 529, pension pot, ISA/TFSA), cash, property and debts - each with an owner, its own currency and a type that says how it is taxed; net worth over all of them, each counted once; each has its own page: investment accounts hold positions added by ticker search, paste or upload, priced daily; cash and property keep a dated value; debts pay themselves down |
| **Portfolios** (`/portfolios`) | a portfolio is a selection of accounts and/or other portfolios - one account can be in any number of them, and a portfolio made of others includes all their accounts, each counted once; values are converted into its currency; net worth, investable assets, allocation by class, tax treatment, account and owner, risk checks, target mix and rebalancing trades; a change to an account shows at once in every portfolio that includes it, and a plan can be linked to a portfolio so its accounts and loans always follow it |
| **Portfolio builder** (`/portfolios/build`) | upload a broker's .xlsx or CSV of positions, into one account or as a file listing several accounts (each given a guessed type to confirm, and joining your account of the same name; into a new portfolio, an existing one, or none); RetPlan finds the table, reads the columns, identifies every security on Yahoo (symbol, ISIN or name), flags doubtful matches, and imports after you review |
| **Projection** | correlated lognormal, fat-tailed Student-t or bootstrap Monte Carlo over 1-60 years, contributions, withdrawals and a goal; yearly or quarterly table, P10-P90 fan chart, return and drawdown distributions, three sample futures, CSV, saved runs |
| **Stress tests** | 2008, the dot-com bust, Covid, the 2022 rate shock and 1973-74 replayed on your mix; any of them can open every projection trial |
| **Planning tools** (`/tools/*`) | what-if sliders and ranked levers on the dashboard; when to claim a public pension; Roth-style conversions; a spending check with guardrails; the tax-efficient draw order; health costs and long-term care simulated future by future |
| **Net worth history** (`/networth`) | assets, debts and a breakdown by kind for every account together and for each portfolio, recorded after every price collection (or on demand) and kept for good; today's split into investments, cash, property and debts, and the history as a chart |
| **Market data** (`/market`) | indices, stocks, ETFs, funds, futures, currencies and crypto collected every day whether held or not - open, high, low, close, adjusted close, volume; add by search, a pasted list or ready-made sets; up to 20 years of history per symbol; CSV download |
| **Securities** (`/securities`) | look up any symbol live on Yahoo; the administrator adds, amends and deletes securities, including manually priced ones (private funds, property) |
| **Help** (`/help`) | every screen and idea, searchable; `Ctrl-K` searches pages, help, accounts, portfolios and holdings |

## The engine

- **Real terms throughout.** Everything is computed in today's money; nominal
  figures multiply by each trial's own inflation path.
- **Tax by bands, inverted exactly.** A progressive schedule is piecewise linear and
  strictly increasing, so "how much must I withdraw to spend X after tax" is one
  calculation, not an iteration.
- **Markets that misbehave.** A Markov regime (bear / normal / bull), correlated
  lognormal, normal or Student-t shocks, and a crash process with a depth
  distribution, a multi-year shape and per-asset transmission - so bonds can gain
  while equities fall.
- **Vectorised over trials.** One trial is `n = 1`, so the deterministic projection
  and the Monte Carlo run the same code and cannot drift apart.

## Database and configuration

Everything is in `config/retplan.toml`, overridable by `RETPLAN_*` environment
variables. The database is SQLAlchemy over **SQLite** (default, zero setup) or
**PostgreSQL**:

```toml
[database]
url = "sqlite:///{data_dir}/retplan.db"
# url = "postgresql+psycopg://retplan:secret@localhost:5432/retplan"
```

There are **no migrations**. The schema is two hand-written files describing the
same tables, `schema/sqlite.sql` and `schema/postgres.sql`. An empty database is
built from the one for its dialect at start-up; a database missing a declared table
or column is refused with a message naming exactly what to add. A database made
before accounts belonged to the workspace (with `portfolio_accounts` and
`portfolio_children` choosing which accounts and portfolios a portfolio includes)
must be rebuilt.

```bash
python tools/copy_db.py --to postgresql+psycopg://...   # move your data across
make test-pg PG=postgresql+psycopg://.../empty_db        # run the suite on PostgreSQL
```

### Prices

Daily bars (open, high, low, close, adjusted close, volume) for every held symbol,
every security collected as market data, and the exchange-rate pairs needed to
convert each account into each portfolio's currency, come from Yahoo Finance's
chart endpoint using only the standard library.
The app collects them daily at `prices.run_at` and catches up at start-up when the
last run is stale; `tools/fetch_prices.py` does one run for cron. Closes older than
`prices.retention_days` (365) are deleted after every run, unless a market-data
symbol keeps more (2 to 20 years); long-run return and
volatility from up to twenty years of monthly history are kept as numbers only.

### Workspaces

There are no planning accounts. Each browser is a workspace, identified by an
opaque id in a signed session cookie; plans, accounts and portfolios are stored against it,
so the cookie never carries anyone's finances. The only shared data are securities
and prices, which only the administrator can change.

## Design

The interface follows MAYA's design: design tokens as CSS custom properties, four
themes (Crimson, Dark, Blue, Green), a gradient top bar with mega-menus, gradient
heroes, pills that carry a glyph and a word so status is never colour alone, and
no inline script - pages declare behaviour with `data-*` attributes. Charts are
server-rendered SVG with a hover layer and a table view, using a colour-vision-safe
palette validated against both surfaces. Every library is vendored; nothing loads
from a CDN.

## Repository layout

```
retplan/     the planning engine - rng, tax, markets, engine, metrics, solvers, samples
portfolio/   db (SQLAlchemy), repository, account_types, yahoo, prices, projection,
             stress, checks, fx, importer, builder, networth
web/         app singleton, config, templating, charts, view models, wizard, plan_link,
             admin, plan store
web/static/  css/tokens.css + css/theme.css, js, vendored Bootstrap and icons
web/templates/  base + _nav (mega menu) + _macros; one folder per area
routes/      one handler class per area, registered by the app singleton
schema/      sqlite.sql and postgres.sql - the only definition of the database
config/      retplan.toml
tools/       fetch_prices.py, copy_db.py
tests/       run_tests.py (engine) and test_portfolio.py (database, prices,
             projections, builder, admin, web; offline)
docs/        requirements, architecture, data model, mathematics, test plan
```

## Licence

MIT. **Not financial advice** — this is an educational model, and its output is
only as good as the assumptions you type into it.
