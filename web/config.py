"""Application configuration: ``config/retplan.yaml``, read by the configurator
adopted from DishtaYantra (core/properties_configurator.py).

The configurator flattens the YAML to dotted keys (``database.url``), resolves
``${other.key}``, ``${ENV_VAR}`` and ``${ENV_VAR:default}``, and applies the
precedence command line > environment > ``config/retplan.local.yaml`` (an
optional, git-ignored overlay for secrets) > ``config/retplan.yaml``. It re-reads
the files every ``app.reload_seconds``.

:class:`Config` is a snapshot of the settings the application needs at start-up
(the database URL cannot change under a running app). Settings meant to change
while RetPlan runs - the assistant's and the optimiser's - are read live through
:meth:`Config.get` and friends, which go to the configurator each time.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass, field

from core.properties_configurator import PropertiesConfigurator

logger = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_FILE = os.path.join(ROOT, "config", "retplan.yaml")


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
    # the live configurator (None for a Config built in code, e.g. by the tests)
    props: PropertiesConfigurator | None = field(default=None, repr=False, compare=False)
    # values set in code win over the files - the tests use this
    overrides: dict = field(default_factory=dict, repr=False, compare=False)

    # -- live settings -------------------------------------------------------
    def get(self, key: str, default=None):
        if key in self.overrides:
            return self.overrides[key]
        if self.props is None:
            return default
        return self.props.get(key, default)

    def get_bool(self, key: str, default: bool = False) -> bool:
        v = self.get(key)
        if v is None or v == "":
            return default
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("1", "true", "yes", "on", "y", "t")

    def get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(float(self.get(key)))
        except (TypeError, ValueError):
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        try:
            return float(self.get(key))
        except (TypeError, ValueError):
            return default

    def get_float_list(self, key: str, default: list | None = None) -> list:
        v = self.get(key)
        if v is None or v == "":
            return list(default or [])
        if isinstance(v, (list, tuple)):
            return [float(x) for x in v]
        try:
            return [float(x) for x in str(v).split(",") if x.strip()]
        except ValueError:
            return list(default or [])

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
    """Read the configuration files into a :class:`Config` snapshot, keeping the
    configurator for live settings. Reads afresh on every call."""
    path = path or os.environ.get("RETPLAN_CONFIG") or DEFAULT_FILE
    PropertiesConfigurator.reset_instance()
    reload_seconds = 60
    props = PropertiesConfigurator(path, reload_interval=reload_seconds)
    cfg = Config(props=props, source=path if os.path.exists(path) else "defaults")
    g = props.get
    try:
        props._reload_interval = max(5, int(g("app.reload_seconds", reload_seconds)))
    except (TypeError, ValueError):
        pass
    cfg.data_dir = data_dir or g("app.data_dir", cfg.data_dir) or "data"
    cfg.database_url = g("database.url", cfg.database_url) or cfg.database_url
    cfg.database_echo = _bool(g("database.echo", cfg.database_echo))
    cfg.prices_enabled = _bool(g("prices.enabled", cfg.prices_enabled))
    cfg.prices_run_at = str(g("prices.run_at", cfg.prices_run_at))
    cfg.prices_retention_days = int(g("prices.retention_days", cfg.prices_retention_days))
    cfg.admin_username = str(g("admin.username", cfg.admin_username) or "admin").strip()
    cfg.admin_password = str(g("admin.password", cfg.admin_password) or "")
    cfg.admin_local = _bool(g("admin.local_is_admin", cfg.admin_local))

    # relative paths are the project's, not the shell's current directory
    old_dir = cfg.data_dir
    if not os.path.isabs(cfg.data_dir):
        cfg.data_dir = os.path.join(ROOT, cfg.data_dir)
    cfg.database_url = cfg.database_url.replace("{data_dir}", cfg.data_dir)
    if cfg.database_url.startswith("sqlite:///") and not cfg.database_url.startswith("sqlite:////"):
        rel = cfg.database_url[len("sqlite:///"):]
        if data_dir and rel.startswith(f"{g('app.data_dir', 'data')}/"):
            # an explicit data dir moves the default SQLite file with it
            rel = os.path.join(old_dir, rel.split("/", 1)[1])
        if rel and not rel.startswith(":") and not os.path.isabs(rel):
            cfg.database_url = "sqlite:///" + os.path.join(ROOT, rel)
        elif rel and os.path.isabs(rel):
            cfg.database_url = "sqlite:///" + rel
    hh, mm = cfg.prices_run_at.split(":")
    if not (0 <= int(hh) < 24 and 0 <= int(mm) < 60):
        raise ValueError(f"prices.run_at must be HH:MM, got {cfg.prices_run_at!r}")
    return cfg
