"""Templating and request helpers shared by every route module.

Mirrors the house pattern: a Jinja2 environment with a context processor that
injects the app-wide template properties, a Flask-style ``url_for`` so templates
name routes rather than hard-code paths, and a flash-message queue on the
session.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import logging
import os
import traceback
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from retplan import __version__ as VERSION

logger = logging.getLogger(__name__)

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

APP_TEMPLATE_PROPS: dict = {
    "app_name": "RetPlan",
    "app_tagline": "Retirement planning you can audit",
    "app_version": VERSION,
}

FLASH_KEY = "_flashes"


# --------------------------------------------------------------------------- #
# Flash messages
# --------------------------------------------------------------------------- #
def flash(request: Request, message: str, category: str = "message") -> None:
    """Queue a message for display on the next rendered page."""
    request.session.setdefault(FLASH_KEY, []).append((category, message))


def get_flashed_messages(request: Request, with_categories: bool = False,
                         category_filter=()):
    messages = request.session.pop(FLASH_KEY, [])
    if category_filter:
        messages = [m for m in messages if m[0] in category_filter]
    return messages if with_categories else [m[1] for m in messages]


def flash_error_and_log(request: Request, user_message: str, exc: Exception) -> None:
    """Show the error to the user AND log the full stack trace. Never swallow."""
    logger.error("%s: %s", user_message, exc)
    logger.error("Full stack trace:\n%s", traceback.format_exc())
    flash(request, f"{user_message}: {exc}", "error")


# --------------------------------------------------------------------------- #
# url_for with Flask semantics
# --------------------------------------------------------------------------- #
def url_for(request: Request, name: str, /, **params) -> str:
    """Resolve a route name to a URL; ``url_for('static', filename=...)`` works.

    ``name`` is positional-only on purpose: the reports link to a route whose own
    path parameter is called ``name``, and a keyword parameter here would collide
    with it.
    """
    app = request.app
    if name == "static":
        filename = params.pop("filename", "")
        url = app.url_path_for("static", path=filename)
        return f"{url}?{urlencode(params)}" if params else url

    path_param_names = set()
    for route in app.routes:
        if getattr(route, "name", None) == name:
            path_param_names = set(getattr(route, "param_convertors", {}).keys())
            break
    path_params = {k: v for k, v in params.items() if k in path_param_names}
    query_params = {k: v for k, v in params.items() if k not in path_param_names}
    url = app.url_path_for(name, **path_params)
    if query_params:
        url = f"{url}?{urlencode(query_params)}"
    return url


# --------------------------------------------------------------------------- #
# Templates
# --------------------------------------------------------------------------- #
def _inject_globals(request: Request) -> dict:
    context = dict(APP_TEMPLATE_PROPS)
    context["session"] = request.session
    context["url_for"] = lambda *a, **kw: url_for(request, *a, **kw)
    context["get_flashed_messages"] = (
        lambda with_categories=False, category_filter=():
        get_flashed_messages(request, with_categories, category_filter))
    context["current_path"] = request.url.path
    return context


templates = Jinja2Templates(directory=TEMPLATES_DIR,
                            context_processors=[_inject_globals])
templates.env.auto_reload = True
templates.env.cache = {}


def _money(value, symbol="", decimals=0):
    """Format a number as money; blank for None so tables stay quiet."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ""
    return f"{symbol}{v:,.{decimals}f}"


def _pct(value, decimals=1):
    try:
        return f"{float(value) * 100:.{decimals}f}%"
    except (TypeError, ValueError):
        return ""


def _compact(value):
    """1.2M / 340k - for axis ticks and stat tiles where width is scarce."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ""
    sign = "-" if v < 0 else ""
    v = abs(v)
    for cut, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if v >= cut:
            trimmed = f"{v / cut:.1f}".rstrip("0").rstrip(".")
            return f"{sign}{trimmed}{suffix}"
    return f"{sign}{v:,.0f}"


templates.env.filters["money"] = _money
templates.env.filters["pct"] = _pct
templates.env.filters["compact"] = _compact


def render(request: Request, template_name: str, status_code: int = 200, **context):
    """Render a Jinja template with the app-wide context."""
    return templates.TemplateResponse(request=request, name=template_name,
                                      context=context, status_code=status_code)


def redirect_to(request: Request, endpoint: str, flash_message: str = None,
                flash_category: str = "success", **params) -> RedirectResponse:
    """Redirect to a named route (303, so a POST lands on a GET)."""
    if flash_message:
        flash(request, flash_message, flash_category)
    return RedirectResponse(url=url_for(request, endpoint, **params), status_code=303)


def wants_json(request: Request) -> bool:
    return (request.url.path.startswith("/api/")
            or "application/json" in request.headers.get("accept", ""))
