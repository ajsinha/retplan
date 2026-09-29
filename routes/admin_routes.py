"""Administrator sign-in, sign-out and password change.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

from web.admin import (DEFAULT_PASSWORD, SESSION_FLAG, admin_mode, check_login,
                       default_password_in_force, is_admin, set_password)
from web.fastapi_compat import flash, redirect_to, render

logger = logging.getLogger(__name__)
MIN_LENGTH = 10


def _safe_next(url: str | None) -> str:
    return url if url and url.startswith("/") and not url.startswith("//") else "/securities"


class AdminRoutes:
    def __init__(self, app: FastAPI, store):
        self.app = app
        self.store = store
        self._register_routes()

    def _register_routes(self) -> None:
        add = self.app.add_api_route
        r = dict(include_in_schema=False)
        add("/admin/login", self.login_form, methods=["GET"], name="admin_login", **r)
        add("/admin/login", self.login, methods=["POST"], name="admin_login_post", **r)
        add("/admin/logout", self.logout, methods=["POST"], name="admin_logout", **r)
        add("/admin/password", self.password_form, methods=["GET"], name="admin_password", **r)
        add("/admin/password", self.password, methods=["POST"],
            name="admin_password_post", **r)

    async def login_form(self, request: Request):
        return render(request, "admin/login.html", mode=admin_mode(request),
                      admin=is_admin(request), next=request.query_params.get("next", ""),
                      username=request.app.state.config.admin_username)

    async def login(self, request: Request):
        form = await request.form()
        nxt = _safe_next(form.get("next"))
        if check_login(request, form.get("username") or "", form.get("password") or ""):
            request.session[SESSION_FLAG] = True
            flash(request, "Signed in as administrator.", "success")
            return RedirectResponse(nxt, status_code=303)
        logger.warning("failed administrator sign-in from %s",
                       request.client.host if request.client else "?")
        flash(request, "That user name and password do not match.", "error")
        return redirect_to(request, "admin_login", next=nxt)

    async def logout(self, request: Request):
        request.session.pop(SESSION_FLAG, None)
        return redirect_to(request, "index", flash_message="Signed out of administration.")

    async def password_form(self, request: Request):
        if not is_admin(request):
            return redirect_to(request, "admin_login", next="/admin/password")
        return render(request, "admin/password.html", min_length=MIN_LENGTH,
                      default=default_password_in_force(request))

    async def password(self, request: Request):
        if not is_admin(request):
            return redirect_to(request, "admin_login", next="/admin/password")
        form = await request.form()
        user = request.app.state.config.admin_username
        new, again = form.get("new") or "", form.get("again") or ""
        if not check_login(request, user, form.get("current") or ""):
            flash(request, "The current password is not right.", "error")
        elif len(new) < MIN_LENGTH:
            flash(request, f"Choose at least {MIN_LENGTH} characters.", "error")
        elif new != again:
            flash(request, "The two new passwords differ.", "error")
        elif new == DEFAULT_PASSWORD:
            flash(request, "That is the default password; choose another.", "error")
        else:
            set_password(request, new)
            logger.info("administrator password changed")
            return redirect_to(request, "securities", flash_message=
                               "Password changed. The one in the configuration file is "
                               "no longer used.")
        return redirect_to(request, "admin_password")
