"""Administrators: one account, signed in with a user name and password.

RetPlan has no user accounts for planning - every browser is its own workspace.
Administration (adding, amending and deleting securities and their prices) is
the one thing that affects everyone, so it needs signing in:

- The account is ``[admin] username`` / ``password`` in config/retplan.toml
  (default ``admin`` / ``retplan-dev-admin``), or RETPLAN_ADMIN_USERNAME /
  RETPLAN_ADMIN_PASSWORD.
- Once changed in the app (/admin/password), the new password is stored as a
  salted PBKDF2 hash in the database and takes precedence over the file.
- While the shipped default password is still in force, every page an
  administrator sees carries a warning, as MAYA does for its bootstrap admin.
- ``[admin] local_is_admin`` (default false) additionally treats requests from
  this computer as administrator without signing in.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

from fastapi import Request

SESSION_FLAG = "rp_admin"
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "retplan-dev-admin"
HASH_KEY = "admin.password_hash"
LOOPBACK = {"127.0.0.1", "::1", "localhost"}
ITERATIONS = 240_000


def hash_password(password: str, salt: str | None = None,
                  iterations: int = ITERATIONS) -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${dk.hex()}"


def verify_hash(password: str, stored: str) -> bool:
    try:
        algo, iters, salt, want = stored.split("$")
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    got = hash_password(password, salt, int(iters)).split("$")[-1]
    return hmac.compare_digest(got, want)


def _stored_hash(request: Request) -> str | None:
    try:
        return request.app.state.db.get_setting(HASH_KEY)
    except Exception:  # noqa: BLE001 - a missing table must not lock anyone out
        return None


def check_login(request: Request, username: str, password: str) -> bool:
    cfg = request.app.state.config
    if not hmac.compare_digest((username or "").strip().encode(),
                               cfg.admin_username.encode()):
        return False
    stored = _stored_hash(request)
    if stored:
        return verify_hash(password or "", stored)
    return bool(cfg.admin_password) and hmac.compare_digest(
        (password or "").encode(), cfg.admin_password.encode())


def set_password(request: Request, new: str) -> None:
    request.app.state.db.set_setting(HASH_KEY, hash_password(new))


def default_password_in_force(request: Request) -> bool:
    cfg = request.app.state.config
    return not _stored_hash(request) and cfg.admin_password == DEFAULT_PASSWORD


def is_admin(request: Request) -> bool:
    if request.session.get(SESSION_FLAG):
        return True
    cfg = request.app.state.config
    if cfg.admin_local:
        host = request.client.host if request.client else ""
        return host in LOOPBACK
    return False


def admin_mode(request: Request) -> str:
    """'password' when signing in is possible, 'local' when only this computer
    is admin, 'off' when neither."""
    cfg = request.app.state.config
    if cfg.admin_password or _stored_hash(request):
        return "password"
    return "local" if cfg.admin_local else "off"
