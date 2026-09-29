"""Database access through SQLAlchemy, on SQLite or PostgreSQL.

The backend is chosen by one URL in configuration (``[database] url`` in
``config/retplan.toml``, or ``RETPLAN_DATABASE_URL``)::

    sqlite:///data/retplan.db
    postgresql+psycopg://retplan:secret@localhost:5432/retplan

There are no migrations. The schema is two hand-written files,
``schema/sqlite.sql`` and ``schema/postgres.sql``, that describe the same
tables. On start-up an empty database is built from the file for its dialect; a
populated one is checked for every table the file declares, and a missing table
is reported rather than silently created half-way.

Queries are SQLAlchemy Core ``text()`` with named parameters, written in the
subset of SQL both engines accept (``ON CONFLICT``, ``RETURNING``), so the
repository above this layer never branches on the dialect.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import json
import logging
import os
import re
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.pool import StaticPool

logger = logging.getLogger(__name__)

PRICE_RETENTION_DAYS = 365
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_DIR = os.path.join(ROOT, "schema")
SCHEMA_FILES = {"sqlite": "sqlite.sql", "postgresql": "postgres.sql"}


class SchemaError(RuntimeError):
    """The database exists but does not match the schema file."""


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def schema_path(dialect: str) -> str:
    try:
        return os.path.join(SCHEMA_DIR, SCHEMA_FILES[dialect])
    except KeyError:
        raise SchemaError(f"no schema file for the '{dialect}' dialect; "
                          f"supported: {', '.join(SCHEMA_FILES)}") from None


def split_sql(script: str) -> list[str]:
    """Statements of a schema file, comments removed, in order."""
    lines = []
    for line in script.splitlines():
        cut = line.find("--")
        lines.append(line if cut < 0 else line[:cut])
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def declared_tables(script: str) -> list[str]:
    return re.findall(r"CREATE TABLE IF NOT EXISTS\s+(\w+)", script, flags=re.I)


def declared_columns(script: str) -> dict[str, list[str]]:
    """{table: [column, ...]} as the schema file declares them."""
    out = {}
    for stmt in split_sql(script):
        m = re.match(r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*)\)", stmt, re.S | re.I)
        if not m:
            continue
        cols = []
        for line in m.group(2).split("\n"):
            words = line.strip().rstrip(",").split()
            if words and words[0].upper() not in ("PRIMARY", "UNIQUE", "FOREIGN",
                                                  "CHECK", "CONSTRAINT"):
                cols.append(words[0].lower())
        out[m.group(1)] = cols
    return out


class Database:
    """An engine, the schema bootstrap, and small query helpers."""

    def __init__(self, url: str, echo: bool = False):
        self.url = url
        self.engine: Engine = _make_engine(url, echo)
        self.dialect = self.engine.dialect.name
        self.ensure_schema()

    # -- schema ------------------------------------------------------------
    def ensure_schema(self) -> None:
        path = schema_path(self.dialect)
        with open(path, encoding="utf-8") as fh:
            script = fh.read()
        wanted = declared_tables(script)
        present = set(inspect(self.engine).get_table_names())
        if not present & set(wanted):
            logger.info("database is empty; creating the schema from %s",
                        os.path.relpath(path, ROOT))
            with self.engine.begin() as c:
                for stmt in split_sql(script):
                    c.exec_driver_sql(stmt)
            return
        missing = [t for t in wanted if t not in present]
        if missing:
            raise SchemaError(
                f"the database at {self.safe_url} is missing table(s) "
                f"{', '.join(missing)} declared in {os.path.relpath(path, ROOT)}. "
                "RetPlan does not migrate schemas: create them from the schema "
                "file, or point the configuration at a fresh database.")
        insp = inspect(self.engine)
        gaps = []
        for table, cols in declared_columns(script).items():
            have = {c["name"].lower() for c in insp.get_columns(table)}
            gaps += [f"{table}.{c}" for c in cols if c not in have]
        if gaps:
            raise SchemaError(
                f"the database at {self.safe_url} lacks column(s) {', '.join(gaps)} "
                f"declared in {os.path.relpath(path, ROOT)}. RetPlan does not migrate "
                "schemas: add them with ALTER TABLE (the schema file gives each "
                "column's type and default), or start from a fresh database and move "
                "your data with tools/copy_db.py.")

    @property
    def safe_url(self) -> str:
        """The URL with any password masked, for logs and the status page."""
        return self.engine.url.render_as_string(hide_password=True)

    # -- connections -------------------------------------------------------
    @contextmanager
    def tx(self):
        """A transaction: commits on success, rolls back on any exception."""
        with self.engine.begin() as c:
            yield c

    def query(self, sql: str, params: dict | None = None) -> list[dict]:
        with self.engine.connect() as c:
            return [dict(r._mapping) for r in c.execute(text(sql), params or {})]

    def one(self, sql: str, params: dict | None = None) -> dict | None:
        with self.engine.connect() as c:
            r = c.execute(text(sql), params or {}).first()
            return dict(r._mapping) if r is not None else None

    def scalar(self, sql: str, params: dict | None = None, default=None):
        with self.engine.connect() as c:
            v = c.execute(text(sql), params or {}).scalar()
        return default if v is None else v

    @staticmethod
    def run(c: Connection, sql: str, params=None):
        """Execute inside an open transaction (``with db.tx() as c``)."""
        return c.execute(text(sql), params or {})

    @staticmethod
    def insert(c: Connection, sql: str, params: dict) -> int:
        """Run an INSERT ... RETURNING id and give back the new id."""
        return int(c.execute(text(sql + " RETURNING id"), params).scalar_one())

    # -- key/value settings ------------------------------------------------
    def get_setting(self, key: str, default=None):
        row = self.one("SELECT value FROM app_settings WHERE key = :k", {"k": key})
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except ValueError:
            return row["value"]

    def set_setting(self, key: str, value) -> None:
        with self.tx() as c:
            self.run(c, "INSERT INTO app_settings (key, value) VALUES (:k, :v) "
                        "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                     {"k": key, "v": json.dumps(value)})

    def dispose(self) -> None:
        self.engine.dispose()


def _make_engine(url: str, echo: bool) -> Engine:
    if url.startswith("sqlite"):
        in_memory = url in ("sqlite://", "sqlite:///:memory:")
        if not in_memory:
            path = url.split("///", 1)[-1]
            if path and not path.startswith(":"):
                os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        kw = dict(connect_args={"check_same_thread": False, "timeout": 30})
        if in_memory:
            # one shared connection, or every checkout would see an empty database
            kw["poolclass"] = StaticPool
        engine = create_engine(url, echo=echo, **kw)

        @event.listens_for(engine, "connect")
        def _pragmas(dbapi_conn, _record):          # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys = ON")
            if not in_memory:
                # WAL: the background price collector never blocks a page read
                cur.execute("PRAGMA journal_mode = WAL")
                cur.execute("PRAGMA synchronous = NORMAL")
            cur.close()
        return engine
    return create_engine(url, echo=echo, pool_pre_ping=True, pool_size=5,
                         max_overflow=10)
