"""Who is an administrator.

RetPlan has no user accounts. Administration (adding, amending and deleting
securities and their prices) is granted in one of two ways, from configuration:

- **a password** (``[admin] password`` or ``RETPLAN_ADMIN_PASSWORD``): signing in
  at /admin/login marks the browser session as admin;
- **no password**: a request from the loopback interface is admin when
  ``[admin] local_is_admin`` is true (the default) - the natural rule for an app
  that listens on 127.0.0.1 for one person.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import hmac

from fastapi import Request

SESSION_FLAG = "rp_admin"
LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def is_admin(request: Request) -> bool:
    cfg = request.app.state.config
    if cfg.admin_password:
        return bool(request.session.get(SESSION_FLAG))
    if not cfg.admin_local:
        return False
    host = request.client.host if request.client else ""
    return host in LOOPBACK


def admin_mode(request: Request) -> str:
    """'password', 'local' or 'off' - for explaining on the page how to get in."""
    cfg = request.app.state.config
    if cfg.admin_password:
        return "password"
    return "local" if cfg.admin_local else "off"


def check_password(request: Request, given: str) -> bool:
    want = request.app.state.config.admin_password
    return bool(want) and hmac.compare_digest(want.encode(), (given or "").encode())
