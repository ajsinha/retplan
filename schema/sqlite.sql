-- RetPlan database schema - SQLite
--
-- This file and schema/postgres.sql describe the same tables, columns, keys and
-- indexes; keep them in step. There are no migrations: on start-up RetPlan runs
-- this file when the database has no tables, and otherwise checks that every
-- table below exists. To change the schema, edit both files and rebuild (or
-- ALTER) the database yourself.
--
-- Conventions:
--   * timestamps are ISO-8601 UTC text ("2026-09-29T14:03:11+00:00")
--   * dates are ISO-8601 text ("2026-09-29"), which sorts and compares correctly
--   * JSON documents are stored as text
--   * money and prices are REAL (IEEE double in SQLite)

PRAGMA foreign_keys = ON;

-- A plan is one named scenario of the retirement model, stored as the JSON form
-- of retplan.plan.Plan. An owner (browser workspace) has one active plan.
CREATE TABLE IF NOT EXISTS plans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    owner       TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    data        TEXT    NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 0 CHECK (is_active IN (0, 1)),
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_plans_owner ON plans (owner);

-- A portfolio of securities belonging to one owner.
CREATE TABLE IF NOT EXISTS portfolios (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    owner       TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    currency    TEXT    NOT NULL DEFAULT 'USD',
    description TEXT    NOT NULL DEFAULT '',
    settings    TEXT    NOT NULL DEFAULT '{}',      -- projection settings, JSON
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_portfolios_owner ON portfolios (owner);

-- Securities: one row per symbol, shared by every portfolio that holds it.
-- lt_* are long-run statistics from up to 20 years of monthly history; only the
-- numbers are kept, never the monthly series. A 'manual' security is priced by an
-- administrator (a private fund, a property) and never fetched from Yahoo.
-- A security marked 'collect' is market data: collected every day whether or
-- not anyone holds it - an index, a fund, a currency pair someone wants to follow.
CREATE TABLE IF NOT EXISTS securities (
    symbol          TEXT PRIMARY KEY,
    name            TEXT NOT NULL DEFAULT '',
    quote_type      TEXT NOT NULL DEFAULT '',
    currency        TEXT NOT NULL DEFAULT '',
    exchange        TEXT NOT NULL DEFAULT '',
    asset_class     TEXT NOT NULL DEFAULT '',
    last_price      REAL,
    prev_close      REAL,
    last_price_date TEXT,
    fetched_at      TEXT,
    fetch_error     TEXT,
    lt_return       REAL,
    lt_vol          REAL,
    lt_years        REAL,
    lt_updated      TEXT,
    dividend_yield  REAL,
    source          TEXT NOT NULL DEFAULT 'yahoo',     -- yahoo | manual (prices typed in)
    collect         INTEGER NOT NULL DEFAULT 0,        -- 1: collect daily, held or not
    keep_days       INTEGER,                           -- days of history kept; NULL: the global setting
    notes           TEXT NOT NULL DEFAULT ''
);

-- An account: investments (holding positions), cash, property or a debt. The
-- type (portfolio/account_types.py) says which, and how it is taxed. Accounts
-- belong to a workspace (owner), not to a portfolio: a portfolio is a selection
-- of them (portfolio_accounts), and one account can be in several. Investment
-- accounts are valued from their holdings; the others carry a value set by hand
-- on as_of, in the account's currency. A debt's value is what is owed on as_of;
-- with a rate and a monthly payment it is paid down month by month from then.
CREATE TABLE IF NOT EXISTS accounts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    owner        TEXT    NOT NULL,
    name         TEXT    NOT NULL,
    type         TEXT    NOT NULL,                   -- account_types.TYPES key
    owner_person INTEGER NOT NULL DEFAULT 0,         -- 0 you, 1 partner, -1 joint
    institution  TEXT    NOT NULL DEFAULT '',
    currency     TEXT    NOT NULL DEFAULT 'USD',     -- of the values typed in
    value        REAL    NOT NULL DEFAULT 0,         -- cash, property, debt
    as_of        TEXT,                               -- the date value was set
    rate         REAL,                               -- debts: annual interest
    payment      REAL,                               -- debts: monthly payment
    term_months  INTEGER,                            -- debts: months left on as_of
    notes        TEXT    NOT NULL DEFAULT '',
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_accounts_owner ON accounts (owner);

-- Which accounts make up which portfolio, and in what order they are shown.
CREATE TABLE IF NOT EXISTS portfolio_accounts (
    portfolio_id INTEGER NOT NULL REFERENCES portfolios (id) ON DELETE CASCADE,
    account_id   INTEGER NOT NULL REFERENCES accounts (id) ON DELETE CASCADE,
    position     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (portfolio_id, account_id)
);
CREATE INDEX IF NOT EXISTS ix_portfolio_accounts_account ON portfolio_accounts (account_id);

-- Portfolios made of other portfolios: a parent includes every account of each
-- child, recursively, each account counted once. Cycles are refused by the app.
CREATE TABLE IF NOT EXISTS portfolio_children (
    parent_id    INTEGER NOT NULL REFERENCES portfolios (id) ON DELETE CASCADE,
    child_id     INTEGER NOT NULL REFERENCES portfolios (id) ON DELETE CASCADE,
    position     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (parent_id, child_id)
);
CREATE INDEX IF NOT EXISTS ix_portfolio_children_child ON portfolio_children (child_id);

-- A position in an investment account. The symbol CASH is a cash balance priced
-- at 1.
CREATE TABLE IF NOT EXISTS holdings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id   INTEGER NOT NULL REFERENCES accounts (id) ON DELETE CASCADE,
    symbol       TEXT    NOT NULL REFERENCES securities (symbol),
    quantity     REAL    NOT NULL DEFAULT 0,
    cost_basis   REAL,                               -- total, not per unit
    asset_class  TEXT    NOT NULL DEFAULT '',
    notes        TEXT    NOT NULL DEFAULT '',
    added_at     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_holdings_account ON holdings (account_id);
CREATE INDEX IF NOT EXISTS ix_holdings_symbol ON holdings (symbol);

-- Daily bars: open, high, low, close, adjusted close (restated after dividends
-- and splits) and volume. After every collection run, rows older than the
-- security's keep_days - or the global retention window (365 days) - are deleted.
CREATE TABLE IF NOT EXISTS prices (
    symbol    TEXT NOT NULL REFERENCES securities (symbol) ON DELETE CASCADE,
    date      TEXT NOT NULL,
    close     REAL NOT NULL,
    adj_close REAL NOT NULL,
    volume    REAL,
    open      REAL,
    high      REAL,
    low       REAL,
    PRIMARY KEY (symbol, date)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_prices_date ON prices (date);

-- Trading days a symbol's calendar expects but Yahoo has no bar for. Each run
-- asks again; after three attempts a day is a known gap and is not asked for.
CREATE TABLE IF NOT EXISTS price_gaps (
    symbol     TEXT    NOT NULL REFERENCES securities (symbol) ON DELETE CASCADE,
    date       TEXT    NOT NULL,
    attempts   INTEGER NOT NULL DEFAULT 0,
    last_tried TEXT    NOT NULL,
    PRIMARY KEY (symbol, date)
);

-- One row per price-collection run, for the status page.
CREATE TABLE IF NOT EXISTS fetch_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    reason      TEXT    NOT NULL,                    -- schedule | startup | manual | new-symbol
    started_at  TEXT    NOT NULL,
    finished_at TEXT,
    symbols     INTEGER NOT NULL DEFAULT 0,
    ok          INTEGER NOT NULL DEFAULT 0,
    failed      INTEGER NOT NULL DEFAULT 0,
    rows_added  INTEGER NOT NULL DEFAULT 0,
    rows_pruned INTEGER NOT NULL DEFAULT 0,
    message     TEXT    NOT NULL DEFAULT ''
);

-- Saved projection runs (the last few per portfolio), for revisiting and comparing.
CREATE TABLE IF NOT EXISTS projections (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER NOT NULL REFERENCES portfolios (id) ON DELETE CASCADE,
    created_at   TEXT    NOT NULL,
    settings     TEXT    NOT NULL,                   -- JSON
    summary      TEXT    NOT NULL,                   -- JSON
    result       TEXT    NOT NULL                    -- JSON
);
CREATE INDEX IF NOT EXISTS ix_projections_portfolio ON projections (portfolio_id);

-- The portfolio builder's analysis of an uploaded spreadsheet, kept between the
-- upload and the confirmation (the review screen edits it). Old drafts are
-- deleted after a week.
CREATE TABLE IF NOT EXISTS import_drafts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    owner       TEXT    NOT NULL,
    filename    TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL,
    data        TEXT    NOT NULL                     -- JSON
);
CREATE INDEX IF NOT EXISTS ix_import_drafts_owner ON import_drafts (owner);

-- Net worth over time, recorded after every price collection and kept for good
-- (unlike daily prices, which are pruned after a year): kind 'all' is every
-- account the workspace has (ref ''); kind 'portfolio' is one portfolio (ref =
-- its id). Assets, debts, and a JSON breakdown by kind of account.
CREATE TABLE IF NOT EXISTS snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    owner       TEXT    NOT NULL,
    taken_on    TEXT    NOT NULL,                    -- ISO date
    kind        TEXT    NOT NULL DEFAULT 'all',      -- all | portfolio
    ref         TEXT    NOT NULL DEFAULT '',         -- the portfolio id for 'portfolio'
    assets      REAL    NOT NULL DEFAULT 0,
    liabilities REAL    NOT NULL DEFAULT 0,
    data        TEXT    NOT NULL DEFAULT '{}',       -- JSON breakdown
    note        TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_snapshots_day ON snapshots (owner, taken_on, kind, ref);

-- Application-wide key/value settings (JSON values), e.g. the collector schedule.
CREATE TABLE IF NOT EXISTS app_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
