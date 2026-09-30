# Configuration reference

Every setting RetPlan reads, where it comes from, and what it does. Settings live in
`config/retplan.yaml`, read by the configurator adopted from DishtaYantra
(`core/properties_configurator.py`). The effective values are on the **System** page.

## How settings are found

- **Keys are dotted paths** through the YAML: `database.url`, `prices.run_at`,
  `assistant.limits.questions_per_hour`.
- **Values can refer to others** - `${app.data_dir}` - and to environment variables,
  with a default: `${RETPLAN_DATABASE_URL:sqlite:///${app.data_dir}/retplan.db}` uses
  the variable if it is set, else what follows the first colon.
- **Precedence**, highest first: a command-line argument `--key=value`; an environment
  variable named exactly like the key; `config/retplan.local.yaml`; `config/retplan.yaml`.
- **`config/retplan.local.yaml`** is optional and git-ignored: loaded straight after the
  main file, it overrides only what it names. It is the place for secrets - an API key,
  a password - so they are never committed.
- **A different file**: `RETPLAN_CONFIG=/path/to/file.yaml` (its `.local.yaml` overlay is
  read too).
- **Live changes**: the files are re-read every `app.reload_seconds`. The database URL,
  the data folder and the collector's schedule are read at start-up; the strategy
  optimiser's and the assistant's settings are read each time they are used, so they
  change without a restart.

## The file

```yaml
# config/retplan.yaml (abridged - the file itself explains every key)
app:
  data_dir: "${RETPLAN_DATA:data}"
  reload_seconds: 60
database:
  url: "${RETPLAN_DATABASE_URL:sqlite:///${app.data_dir}/retplan.db}"
  echo: false
prices:
  enabled: "${RETPLAN_PRICES_ENABLED:true}"
  run_at: "${RETPLAN_PRICES_RUN_AT:18:30}"
  retention_days: "${RETPLAN_PRICES_RETENTION_DAYS:365}"
admin:
  username: "${RETPLAN_ADMIN_USERNAME:admin}"
  password: "${RETPLAN_ADMIN_PASSWORD:retplan-dev-admin}"
  local_is_admin: "${RETPLAN_ADMIN_LOCAL:false}"
strategy:
  search_trials: 600
  claiming: {min_age: 62, max_age: 70, full_age: 67}
assistant:
  enabled: false
  api_key: "${ANTHROPIC_API_KEY:}"
```

## `app`

| Key | Environment | Default | What it does |
|---|---|---|---|
| `app.data_dir` | `RETPLAN_DATA`, or `--data-dir` on the launcher | `data` | Holds the session secret, plan files from before 2.0 (imported on first sight) and, by default, the SQLite database. A relative path is resolved from the project folder, not from where you started the app. |
| `app.reload_seconds` | - | `60` | How often the configuration files are re-read. |

## `database`

| Key | Environment | Default | What it does |
|---|---|---|---|
| `database.url` | `RETPLAN_DATABASE_URL` | `sqlite:///${app.data_dir}/retplan.db` | The database, as a SQLAlchemy URL. For PostgreSQL: `postgresql+psycopg://user:password@host:5432/retplan`. |
| `database.echo` | - | `false` | Log every SQL statement. For debugging only. |

!!! note "Switching databases"
    Point the URL at an **empty** database and restart: RetPlan builds the tables from
    `schema/sqlite.sql` or `schema/postgres.sql`. To bring your data with you, run
    `python tools/copy_db.py --to <new url>` first. There are no migrations: a database
    missing a declared table or column is refused at start-up with a message naming exactly
    what to add.

## `prices`

| Key | Environment | Default | What it does |
|---|---|---|---|
| `prices.enabled` | `RETPLAN_PRICES_ENABLED` | `true` | Collect daily bars for every held symbol, every market-data security and the exchange rates they need while the app runs. |
| `prices.run_at` | `RETPLAN_PRICES_RUN_AT` | `18:30` | Local time of the daily run. The app also runs once at start-up when the last successful run is more than 20 hours old. |
| `prices.retention_days` | `RETPLAN_PRICES_RETENTION_DAYS` | `365` | Daily bars older than this are deleted after each run, unless a market-data symbol keeps more. |

## `admin`

| Key | Environment | Default | What it does |
|---|---|---|---|
| `admin.username` | `RETPLAN_ADMIN_USERNAME` | `admin` | The administrator's user name. |
| `admin.password` | `RETPLAN_ADMIN_PASSWORD` | `retplan-dev-admin` | The starting password. Once it is changed in the app, a salted PBKDF2 hash is kept in the database and this setting is ignored. Until then every page an administrator sees warns about it. Better still, set it in `config/retplan.local.yaml`. |
| `admin.local_is_admin` | `RETPLAN_ADMIN_LOCAL` | `false` | Also treat requests from this computer as administrator without signing in. Never behind a reverse proxy. |

## `strategy` - the strategy optimiser

| Key | Default | What it does |
|---|---|---|
| `strategy.enabled` | `true` | Offer the optimiser. |
| `strategy.search_trials` | `600` | Simulated futures per candidate while searching. More is slower and steadier. |
| `strategy.final_trials` | `3000` | Futures for the confirming run of the recommended strategy and of your plan. |
| `strategy.max_seconds` | `600` | Stop searching after this long and report the best found. |
| `strategy.retire.earliest_shift` | `-5` | How many years before your planned retirement age to try. |
| `strategy.retire.latest_age` | `75` | Never suggest working beyond this age. |
| `strategy.claiming.min_age` / `max_age` | `62` / `70` | The range of claiming ages tried for a public pension. |
| `strategy.claiming.full_age` | `67` | The age the plan's pension amount is taken to be for. |
| `strategy.claiming.early_reduction` / `late_increase` | `0.0667` / `0.08` | Change in the pension per year claimed before or after `full_age` (US Social Security). |
| `strategy.investments.equity_shifts` | `-0.3 … 0.2` | Moves of the share in shares to try. |
| `strategy.withdrawals.try_guardrails` | `true` | Also try guardrail spending. |
| `strategy.withdrawals.try_draw_orders` | `true` | Also try every order of drawing on the accounts. |
| `strategy.conversions.enabled` | `true` | Also try Roth-style conversions. |
| `strategy.conversions.heir_tax_rate` | `0.25` | Tax heirs pay on money left in accounts taxed on the way out, when comparing what is left. |

## `assistant` - the AI assistant (optional)

Off unless `assistant.enabled` is true and its provider is ready (Anthropic needs an API
key; the fake provider needs nothing). Every figure it quotes comes from RetPlan's own engine,
through the tools allowed here.

The administrator can switch the provider and the two models on **Admin → Assistant
settings** without editing this file; that choice is kept in the database and wins over the
file until *Reset to configuration*. The page also sends a test message.

| Key | Default | What it does |
|---|---|---|
| `assistant.enabled` | `false` | Switch the assistant on. |
| `assistant.provider` | `anthropic` | `anthropic` (Claude), `fake` (no model: does nothing), or `none`. |
| `assistant.api_key` | `${ANTHROPIC_API_KEY:}` | The API key. Set the environment variable, or put it in `config/retplan.local.yaml` - never in the committed file. |
| `assistant.base_url` | empty | An optional gateway or proxy. |
| `assistant.model` | `claude-sonnet-5-5` | The model for conversation, what-ifs and reviews. Anthropic: `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-4-5-20251001` (or any other id). Fake: `fake-null` (a fixed note, no tools) or `fake-tools`. |
| `assistant.strategy_model` | `claude-opus-5-5` | The model for explaining a strategy and writing its report. |
| `assistant.max_tokens`, `temperature`, `timeout_seconds` | `4000`, `0.2`, `60` | Limits of one answer. |
| `assistant.max_tool_calls` | `12` | How many engine calls one question may make. |
| `assistant.access` | `everyone` | `everyone`, or `admin` to keep it to the administrator. |
| `assistant.features.*` | all `true` | `intake` (set up a plan by conversation), `explain_strategy`, `what_if`, `review`, `report`. |
| `assistant.tools.*` | reads and simulations on; `edit_plan` off | Which engine tools it may call: `read_plan`, `read_portfolios`, `run_simulation`, `run_optimiser`, `save_scenario`, `edit_plan` (not offered in this version); `confirm_writes` asks you before any write. |
| `assistant.privacy.share_names` | `false` | People and accounts become "Person 1", "Account 2" before anything is sent. |
| `assistant.privacy.share_holdings` | `false` | Whether symbols and quantities of holdings are sent. |
| `assistant.privacy.round_money_to` | `1000` | Amounts sent to the model are rounded to this. |
| `assistant.limits.questions_per_hour` | `30` | Per workspace. |
| `assistant.limits.daily_token_budget` | `2000000` | All workspaces together; `0` for no limit. |
| `assistant.logging.*` | kept 30 days | `keep_conversations`, `retention_days`, `log_tool_calls`. |
| `assistant.prompts.system_file` | empty | Replace the built-in instructions with this file. |
| `assistant.prompts.disclaimer` | educational, not advice | Shown with every answer. |

## Environment only

| Variable | Default | What it does |
|---|---|---|
| `RETPLAN_CONFIG` | `config/retplan.yaml` | Which configuration file to read (its `.local.yaml` overlay too). |
| `RETPLAN_SECRET` | generated | The key that signs session cookies. Without it, one is generated once and kept in `data_dir/.session-secret`, so workspaces survive a restart. |
| `RETPLAN_HOST` | `127.0.0.1` | The address the launcher listens on (`--host`). |
| `RETPLAN_PORT` | `5007` | The port (`--port`). |

!!! warning "Listening beyond this computer"
    With `--host 0.0.0.0` anyone who can reach the port can use the app. Planning data is
    separated by workspace, but change the administrator password first, and put a TLS
    proxy in front if it crosses a network you do not control.
