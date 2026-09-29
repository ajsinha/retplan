# Configuration reference

Every setting RetPlan reads, where it comes from, and what it does. Settings live in
`config/retplan.toml`; each can be overridden by an environment variable, which wins over
the file. A different file can be named with `RETPLAN_CONFIG=/path/to/file.toml`. The
effective values are on the **System** page.

## The file

```toml
# config/retplan.toml
[app]
data_dir = "data"

[database]
url = "sqlite:///{data_dir}/retplan.db"
echo = false

[prices]
enabled = true
run_at = "18:30"
retention_days = 365

[admin]
username = "admin"
password = "retplan-dev-admin"
local_is_admin = false
```

## `[app]`

| Key | Environment | Default | What it does |
|---|---|---|---|
| `data_dir` | `RETPLAN_DATA`, or `--data-dir` on the launcher | `data` | Holds the session secret, plan files from before 2.0 (imported on first sight) and, by default, the SQLite database. A relative path is resolved from the project folder, not from where you started the app. |

## `[database]`

| Key | Environment | Default | What it does |
|---|---|---|---|
| `url` | `RETPLAN_DATABASE_URL` | `sqlite:///{data_dir}/retplan.db` | The database, as a SQLAlchemy URL. `{data_dir}` is replaced by the setting above. For PostgreSQL: `postgresql+psycopg://user:password@host:5432/retplan`. |
| `echo` | - | `false` | Log every SQL statement. For debugging only. |

!!! note "Switching databases"
    Point `url` at an **empty** database and restart: RetPlan builds the tables from
    `schema/sqlite.sql` or `schema/postgres.sql`. To bring your data with you, run
    `python tools/copy_db.py --to <new url>` first. There are no migrations: a database
    missing a declared table or column is refused at start-up with a message naming exactly
    what to add.

## `[prices]`

| Key | Environment | Default | What it does |
|---|---|---|---|
| `enabled` | `RETPLAN_PRICES_ENABLED` | `true` | Collect daily closes for every held symbol while the app runs. |
| `run_at` | `RETPLAN_PRICES_RUN_AT` | `18:30` | Local time of the daily run. Pick a time after the close of the market most of your holdings trade on. The app also runs once at start-up when the last successful run is more than 20 hours old. |
| `retention_days` | `RETPLAN_PRICES_RETENTION_DAYS` | `365` | Daily closes older than this are deleted after each run; a new symbol's first fetch covers the whole window. |

## `[admin]`

| Key | Environment | Default | What it does |
|---|---|---|---|
| `username` | `RETPLAN_ADMIN_USERNAME` | `admin` | The administrator's user name. |
| `password` | `RETPLAN_ADMIN_PASSWORD` | `retplan-dev-admin` | The starting password. Once it is changed in the app, a salted PBKDF2 hash is kept in the database and this setting is ignored. Until then every page an administrator sees warns about it. |
| `local_is_admin` | `RETPLAN_ADMIN_LOCAL` | `false` | Also treat requests from this computer as administrator without signing in. Never behind a reverse proxy. |

## Environment only

| Variable | Default | What it does |
|---|---|---|
| `RETPLAN_CONFIG` | `config/retplan.toml` | Which configuration file to read. |
| `RETPLAN_SECRET` | generated | The key that signs session cookies. Without it, one is generated once and kept in `data_dir/.session-secret`, so workspaces survive a restart. |
| `RETPLAN_HOST` | `127.0.0.1` | The address the launcher listens on (`--host`). |
| `RETPLAN_PORT` | `5007` | The port (`--port`). |

!!! warning "Listening beyond this computer"
    With `--host 0.0.0.0` anyone who can reach the port can use the app. Planning data is
    separated by workspace, but change the administrator password first, and put a TLS
    proxy in front if it crosses a network you do not control.
