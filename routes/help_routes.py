"""Help routes.

Every topic in the catalogue registers its own route here, so adding a page is a
catalogue entry plus a template - there is no list to keep in sync.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

from web import cases as case_studies
from web.fastapi_compat import TEMPLATES_DIR, render
from web.guide_render import render as render_guide
from web.help_catalog import CATEGORIES, GUIDES, TOPICS, guide, related
from web.store import session_id

logger = logging.getLogger(__name__)


class HelpRoutes:
    def __init__(self, app: FastAPI, store):
        self.app = app
        self.store = store
        self._register_routes()

    def _register_routes(self) -> None:
        add = self.app.add_api_route
        add("/help", self.index, methods=["GET"], name="help", include_in_schema=False)
        add("/help/guides", self.guides, methods=["GET"], name="help_guides",
            include_in_schema=False)
        add("/help/guides/{slug}", self.guide, methods=["GET"], name="help_guide",
            include_in_schema=False)
        add("/help/case-studies", self.cases, methods=["GET"], name="help_cases",
            include_in_schema=False)
        add("/help/case-studies/{slug}", self.case, methods=["GET"], name="help_case",
            include_in_schema=False)
        add("/help/case-studies/{slug}/open", self.open_case, methods=["POST"],
            name="help_case_open", include_in_schema=False)
        for slug in TOPICS:
            add(f"/help/{slug}", self._page(slug), methods=["GET"],
                name=f"help_{slug.replace('-', '_')}", include_in_schema=False)

    async def index(self, request: Request):
        return render(request, "help/index.html", categories=CATEGORIES,
                      topics=TOPICS, guides=GUIDES, studies=case_studies.CASES)

    async def guides(self, request: Request):
        return render(request, "help/guides.html", guides=GUIDES)

    async def guide(self, request: Request, slug: str):
        g = guide(slug)
        if g is None:
            return render(request, "error.html", status_code=404, code=404,
                          message=f"There is no guide called '{slug}'.")
        return render(request, "help/guide.html", guide=g, doc=render_guide(slug))

    async def cases(self, request: Request):
        return render(request, "help/cases.html", studies=case_studies.CASES)

    async def case(self, request: Request, slug: str):
        c = case_studies.get(slug)
        if c is None:
            return render(request, "error.html", status_code=404, code=404,
                          message=f"There is no case study called '{slug}'.")
        return render(request, "help/case.html", case=c, fig=case_studies.figures(c),
                      plan=case_studies.plan_for(c), studies=case_studies.CASES)

    async def open_case(self, request: Request, slug: str):
        c = case_studies.get(slug)
        if c is None:
            return RedirectResponse("/help/case-studies", status_code=303)
        plan = case_studies.plan_for(c)
        request.app.state.store.create(session_id(request), plan.label, plan, activate=True)
        from web.fastapi_compat import flash
        flash(request, f"“{plan.label}” is now a scenario in your workspace, and active. "
                       "Change anything - the case study itself is untouched.", "success")
        return RedirectResponse("/dashboard", status_code=303)

    def _page(self, slug: str):
        template = f"help/{slug}.html"
        exists = os.path.exists(os.path.join(TEMPLATES_DIR, template))
        if not exists:
            logger.warning("help topic %s has no template yet", slug)

        async def handler(request: Request):
            if not os.path.exists(os.path.join(TEMPLATES_DIR, template)):
                return render(request, "error.html", status_code=404, code=404,
                              message=f"The help page '{slug}' has not been written yet.")
            return render(request, template, topic=TOPICS[slug],
                          help_related=related(slug))
        handler.__name__ = f"help_{slug.replace('-', '_')}"
        return handler
