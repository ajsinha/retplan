# RetPlan — Portable Retirement Planning Workbook

A single, macro-free spreadsheet model that behaves **identically in Microsoft Excel and
LibreOffice Calc**, and that is **jurisdiction-agnostic**: no hard-coded country, currency,
tax code, pension scheme or account type. Everything that varies by country, employer or
person is data the user edits in tables, not logic baked into formulas.

## Documents

| Doc | Purpose |
|---|---|
| [docs/00-feature-list.md](docs/00-feature-list.md) | Scannable catalogue of every feature, with IDs and release phase |
| [docs/01-requirements.md](docs/01-requirements.md) | Normative, testable requirements (functional + non-functional) |
| [docs/02-platform.md](docs/02-platform.md) | Tiering (LibreOffice-first), macro architecture, allowed/banned formula constructs |
| [docs/03-data-model.md](docs/03-data-model.md) | Sheet inventory, table schemas, units, key relationships, calculation order |
| [docs/04-math-and-simulation.md](docs/04-math-and-simulation.md) | Algorithms: PRNG, distributions, regimes, crashes, tax inversion, policies |
| [docs/05-test-plan.md](docs/05-test-plan.md) | Golden scenarios, cross-implementation equivalence, acceptance criteria |
| [docs/06-delivery-notes.md](docs/06-delivery-notes.md) | What was actually built, what was measured, and every departure from the spec |

## Quick start

```bash
./scripts/setup.sh                      # venv + dependencies
.venv/bin/python run_retplan_web.py     # the web app on port 5007

make test        # engine + portfolio/web suites, offline       (~5 s)
make build       # generate RetPlan.ods through the UNO API    (~80 s)
make verify      # prove the sheet and the engine agree exactly
make simulate    # run the Monte Carlo and write results in
make install     # put the macros in your LibreOffice profile
```

Then open `RetPlan.ods`, work through **Start Here**, and press **Run simulation**
on the Dashboard. The projection itself is live formulas and needs no macros.

### Enabling the buttons

The projection is live formulas and needs nothing. The four Dashboard buttons need
two things:

1. **The Python script provider** — `sudo apt install libreoffice-script-provider-python`
   (already present on most desktop installs).
2. **Permission to run the document's macros.** The workbook binds its buttons to
   scripts, so LibreOffice's macro security applies. At the default **High** level
   with no trusted location, it disables them on open and the buttons do nothing.
   The portable way, from anywhere you have cloned this repo:

   ```bash
   make setup          # installs the macros and trusts this checkout
   # or, separately:
   python3 tools/install_macros.py
   python3 tools/trust_folder.py           # trusts the repo root and everything under it
   python3 tools/trust_folder.py --list    # show current trusted locations
   python3 tools/trust_folder.py --remove  # undo
   ```

   `trust_folder.py` resolves the repo root at run time, so it does the right thing
   wherever the project lives — move or re-clone it and re-run `make setup`.
   LibreOffice matches trusted locations by URL prefix, so one entry covers every
   subfolder. Your macro security **level is left untouched**; only this location is
   added. LibreOffice must be closed when you run it, since a running instance owns
   the profile and rewrites it on exit.

   Prefer the GUI? **Tools ▸ Options ▸ LibreOffice ▸ Security ▸ Macro Security… ▸
   Trusted Sources ▸ Trusted File Locations ▸ Add…**, or set Macro Security to
   **Medium** to be prompted on every open.

Prefer not to touch either setting? Run the simulation from the command line
instead — identical code, identical results:

```bash
python3 tools/simulate.py RetPlan.ods --trials 10000 --full
```

## What is in the box

- **24 worksheets**: guided input sheets, a fully visible formula engine, simulation
  sheets, a dashboard with ten charts, three reports and an audit sheet.
- **A generic tax engine**: a table of bands you type. A tax-free allowance is a 0%
  first band; a taper is a band with the higher effective rate. Because the schedule
  stays piecewise linear it is *exactly invertible*, so "how much must I withdraw to
  spend X after tax" is solved in one pass — no circular references, no iteration.
- **A market engine with three layers**: a Markov regime (bear / normal / bull), a
  correlated diffusive shock (lognormal, normal or fat-tailed Student-t), and a jump
  process for crashes with a depth distribution, a multi-year drawdown shape and
  per-asset transmission betas — so government bonds can *gain* while equities fall.
- **The same maths twice, and proved equal**: the workbook's formulas and the numpy
  engine agree to 7e-12 relative over 61 years on the full sample household.

## The three design commitments

1. **Portability over cleverness.** No macros, no dynamic arrays, no structured references,
   no Excel Data Tables, no slicers. If a construct is not proven in both engines at the
   declared floor versions, it is not used. See [CR-*](docs/02-platform.md).
2. **Generality over presets.** Tax is a user-editable bracket engine; account types are
   user-defined *tax wrappers* (EET / TEE / TTE / ETT); asset classes, inflation series,
   life expectancy and pension indexation are all input tables. Shipping "presets" are
   sample data files, never formulas.
3. **Auditability over black boxes.** Every displayed number traces to a visible
   intermediate row. A reconciliation sheet proves sources = uses and that every balance
   rolls forward exactly, every period.

## Identifier conventions

- `F-<AREA>-<n>` — feature (catalogue)
- `FR-<AREA>-<n>` — functional requirement
- `NFR-<n>` — non-functional requirement
- `CR-<n>` — compatibility rule
- `DR-<n>` — data model rule
- `TR-<n>` — test requirement

Priority uses MoSCoW: **M**ust / **S**hould / **C**ould / **W**on't (this release).


## The web application

A FastAPI application, now developed independently of the workbook (which is
kept as it was at 1.0; see *The LibreOffice workbook* in the help for how the two
differ). Its design - four themes, mega-menu navigation,
gradient heroes, help centre and about page - is adopted from MAYA.

```bash
./scripts/setup.sh                      # venv + dependencies
.venv/bin/python run_retplan_web.py     # http://127.0.0.1:5007
```

`--host`, `--port`, `--reload`, `--log-level` and `--data-dir` are flags;
everything else is in `config/retplan.toml`, overridable by `RETPLAN_*`
environment variables.

| | |
|---|---|
| **Quick start** (`/start`) | six short steps - you, income, savings, spending, assumptions, review - build a complete plan |
| **Scenarios** (`/scenarios`, `/compare`) | several named plans per workspace; compare odds, wealth and tax side by side on one seed |
| **Dashboard** | verdict hero with success odds and error bar, KPI tiles, up to eight charts; 500-25,000 trials |
| **Plan editor** | nine sections; rarely changed columns hidden behind *Show advanced columns*; contextual help on each |
| **Reports / Audit** | year-by-year cash flow, balance sheet and tax; the reconciliation audit |
| **Portfolios** (`/portfolios`) | holdings with ticker search or paste-import, daily prices, FX conversion, allocation, risk checks, target mix and rebalancing trades, a one-click copy into the plan |
| **Projection** | correlated lognormal, fat-tailed Student-t or bootstrap Monte Carlo over 1-60 years, contributions and withdrawals, a goal; yearly or quarterly table, P10-P90 fan chart, return and drawdown distributions, three sample futures, CSV export, saved runs |
| **Stress tests** | 2008, the dot-com bust, Covid, the 2022 rate shock and 1973-74 replayed on your mix; any of them can open every projection trial |
| **Portfolio builder** (`/portfolios/build`) | upload a broker's .xlsx or CSV of positions; RetPlan finds the table, reads the columns, identifies every security on Yahoo (symbol, ISIN or name), flags doubtful matches, and imports after you review |
| **Securities** (`/securities`) | look up any symbol live on Yahoo; administrators add, amend and delete securities, including manually priced ones (private funds, property) |
| **Prices** (`/prices`) | the collector's schedule, every tracked security, and the run log |
| **Help** (`/help`) | 29 subjects in five categories, searchable; `Ctrl-K` searches pages, help and holdings |

### Database

SQLAlchemy over **SQLite** (default, zero setup) or **PostgreSQL** - switch with
one line in `config/retplan.toml`:

```toml
[database]
url = "sqlite:///data/retplan.db"
# url = "postgresql+psycopg://retplan:secret@localhost:5432/retplan"
```

There are **no migrations**. The schema is two hand-written files that describe
the same tables, `schema/sqlite.sql` and `schema/postgres.sql`; an empty database
is built from the one for its dialect at start-up, and a database missing a
declared table is refused with a clear error. `tests/test_portfolio.py` checks
the two files declare identical tables, columns and indexes.

```bash
python tools/copy_db.py --to postgresql+psycopg://...    # move your data across
make test-pg PG=postgresql+psycopg://.../empty_db         # run the suite on PostgreSQL
```

### Prices

Daily closes for every held symbol (and the FX pairs their portfolios need) come
from Yahoo Finance's chart endpoint, using only the standard library. The web
app collects them daily at `prices.run_at` and catches up at start-up if the last
run is stale; `tools/fetch_prices.py` does one run for cron. Closes older than
`prices.retention_days` (365) are deleted after every run; long-run return and
volatility from up to 20 years of monthly history are kept as numbers only.

Charts are **server-rendered inline SVG** with a hover layer - no charting
library, no CDN. The categorical palette is validated for colour-vision
separation against the light and dark surfaces, and every chart ships a table
view so no value is reachable only by hovering.

Plans and portfolios are keyed by an opaque workspace id in a signed session
cookie; there are no accounts, and the cookie never carries your finances.

### Layout

```
web/         app singleton, config, templating, charts, view models, wizard, plan store
web/static/  css/tokens.css + css/theme.css (the MAYA design), js, vendored Bootstrap
web/templates/  base + _nav (mega menu) + _macros/ui.html; one folder per area
routes/      one handler class per area, registered by the app singleton
portfolio/   db (SQLAlchemy), repository, yahoo, prices, projection, stress, checks, fx
schema/      sqlite.sql and postgres.sql - the only definition of the database
config/      retplan.toml
run_retplan_web.py   launcher (port 5007 by default)
```

## Repository layout

```
retplan/     the engine - rng, tax, markets, engine, metrics, solvers, reader, samples
web/         the FastAPI application
routes/      one route handler class per area of the web application
portfolio/   portfolios, prices and projections
schema/      the database schema, one file per backend
build/       the workbook generator (UNO): spec, theme, sheet builders
macros/      in-document Python macros for LibreOffice
tools/       installer, trust helper, simulation runner, cross-check, inspectors,
             fetch_prices, copy_db
tests/       run_tests.py (engine, 91 assertions) and test_portfolio.py (database,
             prices, projections, wizard, web; offline)
docs/        specification and delivery notes
```

## Licence

MIT. **Not financial advice** — this is an educational model, and its output is
only as good as the assumptions you type into it.
