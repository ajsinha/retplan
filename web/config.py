"""Application configuration: ``config/retplan.toml`` plus environment overrides.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import logging
import os
import secrets
import tomllib
from dataclasses import dataclass

logger = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_FILE = os.path.join(ROOT, "config", "retplan.toml")


@dataclass
class Config:
    data_dir: str = "data"
    database_url: str = "sqlite:///{data_dir}/retplan.db"
    database_echo: bool = False
    prices_enabled: bool = True
    prices_run_at: str = "18:30"
    prices_retention_days: int = 365
    admin_username: str = "admin"
    admin_password: str = "retplan-dev-admin"
    admin_local: bool = False
    source: str = "defaults"

    def secret(self) -> str:
        """RETPLAN_SECRET, else a secret generated once and kept in the data dir,
        so sessions (and the workspaces they point at) survive a restart."""
        env = os.environ.get("RETPLAN_SECRET")
        if env:
            return env
        path = os.path.join(self.data_dir, ".session-secret")
        try:
            with open(path, encoding="utf-8") as fh:
                value = fh.read().strip()
            if len(value) >= 32:
                return value
        except FileNotFoundError:
            pass
        value = secrets.token_hex(32)
        os.makedirs(self.data_dir, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(value)
        return value


def _bool(v) -> bool:
    return v if isinstance(v, bool) else str(v).strip().lower() in ("1", "true", "yes", "on")


def load_config(path: str | None = None, data_dir: str | None = None) -> Config:
    path = path or os.environ.get("RETPLAN_CONFIG") or DEFAULT_FILE
    raw: dict = {}
    cfg = Config()
    if os.path.exists(path):
        with open(path, "rb") as fh:
            raw = tomllib.load(fh)
        cfg.source = path
    app, db, px = raw.get("app", {}), raw.get("database", {}), raw.get("prices", {})
    adm = raw.get("admin", {})
    cfg.admin_username = str(adm.get("username", cfg.admin_username) or "admin").strip()
    cfg.admin_password = str(adm.get("password", cfg.admin_password) or "")
    cfg.admin_local = _bool(adm.get("local_is_admin", cfg.admin_local))
    cfg.data_dir = app.get("data_dir", cfg.data_dir)
    cfg.database_url = db.get("url", cfg.database_url)
    cfg.database_echo = _bool(db.get("echo", cfg.database_echo))
    cfg.prices_enabled = _bool(px.get("enabled", cfg.prices_enabled))
    cfg.prices_run_at = str(px.get("run_at", cfg.prices_run_at))
    cfg.prices_retention_days = int(px.get("retention_days", cfg.prices_retention_days))

    env = os.environ.get
    cfg.data_dir = data_dir or env("RETPLAN_DATA") or cfg.data_dir
    cfg.database_url = env("RETPLAN_DATABASE_URL") or cfg.database_url
    if env("RETPLAN_PRICES_ENABLED") is not None:
        cfg.prices_enabled = _bool(env("RETPLAN_PRICES_ENABLED"))
    cfg.prices_run_at = env("RETPLAN_PRICES_RUN_AT") or cfg.prices_run_at
    cfg.admin_username = env("RETPLAN_ADMIN_USERNAME") or cfg.admin_username
    cfg.admin_password = env("RETPLAN_ADMIN_PASSWORD") or cfg.admin_password
    if env("RETPLAN_ADMIN_LOCAL") is not None:
        cfg.admin_local = _bool(env("RETPLAN_ADMIN_LOCAL"))
    if env("RETPLAN_PRICES_RETENTION_DAYS"):
        cfg.prices_retention_days = int(env("RETPLAN_PRICES_RETENTION_DAYS"))
    # relative paths are the project's, not the shell's current directory
    if not os.path.isabs(cfg.data_dir):
        cfg.data_dir = os.path.join(ROOT, cfg.data_dir)
    cfg.database_url = cfg.database_url.replace("{data_dir}", cfg.data_dir)
    if cfg.database_url.startswith("sqlite:///") and not cfg.database_url.startswith("sqlite:////"):
        rel = cfg.database_url[len("sqlite:///"):]
        if rel and not rel.startswith(":"):
            cfg.database_url = "sqlite:///" + os.path.join(ROOT, rel)
    hh, mm = cfg.prices_run_at.split(":")
    if not (0 <= int(hh) < 24 and 0 <= int(mm) < 60):
        raise ValueError(f"prices.run_at must be HH:MM, got {cfg.prices_run_at!r}")
    return cfg
