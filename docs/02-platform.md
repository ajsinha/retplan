# RetPlan — Platform and Architecture

## 1. Stack

| Layer | Choice |
|---|---|
| Language | Python 3 (`tomllib`, so 3.11 or later) |
| Numerics | NumPy — the only dependency of the engine in `retplan/` |
| Web | FastAPI on uvicorn, Starlette session middleware, Jinja2 templates |
| Database | SQLAlchemy 2 Core over SQLite (default) or PostgreSQL 12+ (psycopg 3) |
| Front end | Vendored Bootstrap 5, Bootstrap Icons and fonts; the MAYA design tokens; two small scripts of our own |
| Charts | Server-rendered inline SVG (`web/charts.py`); no charting library |
| Market data | Yahoo Finance chart and search endpoints through `urllib` (`portfolio/yahoo.py`) |
| Upload parsing | `openpyxl` for .xlsx in the portfolio builder; `csv` for text |

`requirements.txt` lists runtime and test dependencies; `scripts/setup.sh` creates
`.venv` and installs them.

## 2. Layout

```
retplan/        the planning engine: plan, rng, markets, tax, engine, metrics, solvers, samples
portfolio/      db, repository, account_types, yahoo, prices, fx, assets, checks,
                importer, builder, networth, projection, stress
web/            app singleton, config, templating helpers, charts, view models,
                wizard, plan store, plan_link (plans linked to a portfolio), admin,
                help catalogue
web/templates/  base, _nav (mega menu), shared UI components; one folder per area
web/static/     css/tokens.css, css/theme.css, js/, img/, vendor/
routes/         one handler class per area
schema/         sqlite.sql and postgres.sql — the only definition of the database
config/         retplan.toml
tools/          fetch_prices.py, copy_db.py
tests/          run_tests.py, test_portfolio.py
run_retplan_web.py   launcher (port 5007 by default)
```

The dependency direction is one-way: `routes/` → `web/` → `portfolio/` and
`retplan/`. `retplan/` imports nothing from the rest; `portfolio/` imports only
`retplan.rng.cholesky_psd`.

## 3. The application object

`web/retplan_webapp.py` defines `RetPlanWebApp`, a thread-safe singleton
(`get_instance`) that:

1. loads configuration (`web/config.load_config`);
2. opens the database (`portfolio.db.Database`), which builds or checks the schema;
3. constructs the services — `PlanStore`, `PortfolioRepo`, `PriceCollector`,
   `PriceScheduler`;
4. creates the FastAPI app with a lifespan that starts the scheduler and, on
   shutdown, stops it and disposes the engine;
5. installs `SessionMiddleware` (cookie `retplan_session`, SameSite=Lax, one year),
   mounts `/static`, and puts every service on `app.state`;
6. constructs every class in `routes.ALL_ROUTES` with `(app, store)`;
7. installs the 404 and catch-all error handlers.

`create_app()` is the factory for `uvicorn --reload`. OpenAPI docs are at
`/api/docs`.

## 4. Route classes

Each module in `routes/` defines one class. Its constructor stores the app and the
plan store and calls `_register_routes`, which uses `app.add_api_route` with a
route name; templates refer to routes by that name through `url_for`. Anything
else a handler needs is read from `request.app.state`.

| Class | Area |
|---|---|
| `NoAuthRoutes` | landing, about, method, search, system, `/healthz` |
| `WizardRoutes` | `/start` |
| `ScenarioRoutes` | `/scenarios`, `/compare`, `/api/compare/run` |
| `PlanRoutes` | `/plan/{section}`, `/plan/link`, `/plan/unlink` |
| `DashboardRoutes` | `/dashboard`, `/audit`, `/report/plan` |
| `SimulationRoutes` | `/api/simulate`, `/api/analysis`, `/api/results`, `/api/clear` |
| `ReportRoutes` | `/reports/{name}` |
| `ExportRoutes` | plan JSON export and import, reset, clear |
| `BuilderRoutes` | `/portfolios/build` (`?aid=` into one account, `?pid=` from a portfolio) |
| `AccountRoutes` | `/accounts` (every account, by kind), `/accounts/dialog`, `/accounts/save`, `/accounts/{aid}` and its `delete`, `duplicate`, `portfolios`, `refresh`, `holdings`, `import`, `holdings/save`; `/holdings/{hid}/delete` |
| `PortfolioRoutes` | `/portfolios/*` (portfolios; `/portfolios/{pid}/members` to choose accounts and parts, `/portfolios/{pid}/accounts/{aid}/remove`, `/portfolios/{pid}/parts/{cid}/remove`, `/portfolios/{pid}/record` for net worth on demand), `/prices`, `/api/tickers`, `/api/portfolios/{pid}` |
| `SecurityRoutes` | `/securities/*` |
| `AdminRoutes` | `/admin/login`, `/admin/logout`, `/admin/password` |
| `ToolsRoutes` | `/api/whatif`, `/api/whatif/save`, `/api/levers`, `/tools/claiming`, `/tools/conversions`, `/tools/spending`, `/tools/draw-order`, `/tools/health` |
| `NetWorthRoutes` | `/networth` - every account together, then each portfolio: net worth today, split by kind, and its recorded history |
| `HelpRoutes` | `/help`, one route per help topic, `/help/guides/*` (Markdown in `web/guides/`, rendered by `web/guide_render.py`), `/help/case-studies/*` (`web/cases.py`) |

Long computations (Monte Carlo, solvers, scenario comparison) are JSON endpoints
the page calls and then swaps the results in, rather than long form posts.

## 5. Templates and front end

- `web/fastapi_compat.py` holds the Jinja2 environment, a context processor with
  the application-wide properties, a Flask-style `url_for`, `render`, `redirect_to`
  and a flash-message queue on the session. Static URLs carry a cache-busting
  version from the newest mtime of our own CSS and JS.
- `base.html` loads the vendored Bootstrap CSS and icons, `tokens.css`, `theme.css`,
  `js/theme-init.js` in the head (so a stored theme applies before first paint) and
  `js/retplan.js` plus the Bootstrap bundle at the end of the body.
- **No CDN.** Every library is under `web/static/vendor/`; the application works
  offline apart from price collection and symbol lookup.
- **No inline JavaScript.** Behaviour is attached from `retplan.js` by data
  attributes; templates contain no `<script>` bodies and no `on*=` handlers.
- Shared Jinja components (page heads, KPI tiles, pills, key/value lists, empty
  states) live in one include file under `web/templates/`.

## 6. Design system (MAYA)

- `web/static/css/tokens.css` is the only place colours are defined. Four themes —
  Crimson (stored as `light`), Dark, Blue and Green — each redefine the same
  `--rp-*` roles (accent, ink, surface, canvas, border, ok/warn/bad, navigation
  gradient). With no stored choice, the operating system's light/dark preference
  decides.
- `--viz-*` is the chart palette: eight categorical slots validated for colour-vision
  separation against the light and dark surfaces, and a six-step sequential ramp for
  bands.
- `theme.css` builds the components — mega-menu navigation, gradient heroes, cards,
  tables — from the tokens only.
- The chosen theme is kept in `localStorage` (`retplan.theme`).

## 7. Charts

`web/charts.py` renders every chart as an SVG string: line, stacked area, fan,
spaghetti, histogram, tornado, projection fan, range bars, binned histogram, date
line and quarter path. Each carries a title and description for assistive
technology, a hover layer, and a table view. Colours are CSS variables, so a chart
follows the theme — including a saved projection re-rendered later.

## 8. Database

- `portfolio/db.Database` wraps one SQLAlchemy engine. The backend is chosen by
  `[database] url` (or `RETPLAN_DATABASE_URL`):
  `sqlite:///{data_dir}/retplan.db` by default, or
  `postgresql+psycopg://user:pass@host:5432/db`.
- **Two schema files, no migrations.** `schema/sqlite.sql` and
  `schema/postgres.sql` declare the same tables, columns and indexes. At start-up an
  empty database is built from the file for its dialect; a populated one is checked
  for every declared table and column, and a gap stops start-up with a message
  naming it. Schema changes are made by editing both files and altering or
  rebuilding the database by hand. (A database from before accounts belonged to the
  workspace must be rebuilt: `accounts` and `holdings` no longer have
  `portfolio_id`, and `portfolio_accounts` and `portfolio_children` are new.)
- Queries are SQLAlchemy Core `text()` with named parameters, in the SQL subset
  both engines accept (`ON CONFLICT … DO UPDATE`, `RETURNING`), so the repository
  never branches on dialect.
- SQLite connections enable foreign keys, WAL journalling and `synchronous=NORMAL`,
  so the background collector never blocks a page read. PostgreSQL uses a pool of
  5 (+10 overflow) with pre-ping.
- `tools/copy_db.py` copies every table from one URL to another.

See [03-data-model.md](03-data-model.md) for the tables.

## 9. Background price scheduler

`portfolio.prices.PriceScheduler` runs `PriceCollector.collect` on a daemon thread
named `price-scheduler`:

- daily at `prices.run_at` (local time, default 18:30);
- once at start-up if the last successful run is older than 20 hours;
- never if `prices.enabled` is false (the test suites construct the app with the
  scheduler off).

The collector holds a lock so only one run proceeds at a time, pauses 0.4 s between
symbols, records each run in `fetch_runs`, prunes closes older than
`prices.retention_days`, refreshes long-run statistics every 30 days, and records
the day's net worth for every account together and for each portfolio
(`portfolio/networth.py`). FX pairs needed by an account's or portfolio's currency
are collected automatically. A new symbol added to an account is collected at once on a short-lived background
thread. `tools/fetch_prices.py` runs the same collector from cron.

## 10. Yahoo client

`portfolio/yahoo.py` talks to two unofficial endpoints with the standard library:

- `query1.finance.yahoo.com/v8/finance/chart/<symbol>` — daily or monthly bars,
  adjusted closes, currency and instrument type;
- `query2.finance.yahoo.com/v1/finance/search` — symbol search for autocomplete,
  the builder and lookups.

It sends a bare `Mozilla/5.0` user agent (a full browser string is answered with
429), uses a 20 s timeout, parses defensively, and raises `YahooError` per symbol.
FX rates are ordinary symbols of the form `<FROM><TO>=X`.

## 11. Configuration

`config/retplan.toml` (or the file named by `RETPLAN_CONFIG`), overridden by
environment variables:

| Key | Environment | Default |
|---|---|---|
| `app.data_dir` | `RETPLAN_DATA` | `data` (relative to the project root) |
| `database.url` | `RETPLAN_DATABASE_URL` | `sqlite:///{data_dir}/retplan.db` |
| `database.echo` | — | `false` |
| `prices.enabled` | `RETPLAN_PRICES_ENABLED` | `true` |
| `prices.run_at` | `RETPLAN_PRICES_RUN_AT` | `18:30` |
| `prices.retention_days` | `RETPLAN_PRICES_RETENTION_DAYS` | `365` |
| `admin.username` | `RETPLAN_ADMIN_USERNAME` | `admin` |
| `admin.password` | `RETPLAN_ADMIN_PASSWORD` | the shipped default (change it) |
| `admin.local_is_admin` | `RETPLAN_ADMIN_LOCAL` | `false` |
| — | `RETPLAN_SECRET` | generated once into `data_dir/.session-secret` |

The launcher takes `--host`, `--port` (5007), `--reload`, `--log-level` and
`--data-dir`.

## 12. Security posture

- No user accounts for planning; a workspace is an opaque id in a signed cookie,
  and the cookie never carries financial data.
- The administrator is one account. A password changed in the app is stored as a
  salted PBKDF2-SHA256 hash in `app_settings` and takes precedence over the file.
  With `local_is_admin`, loopback requests are administrators without signing in —
  unsafe behind a reverse proxy, where every request looks local.
- Uploads are capped at 10 MB and parsed in memory; nothing is written to disk.
- `next=` redirects accept only same-site relative paths.
