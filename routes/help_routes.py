"""Help routes.

Every topic in the catalogue registers its own route here, so adding a page is a
catalogue entry plus a template - there is no list to keep in sync.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request

from web.fastapi_compat import TEMPLATES_DIR, render
from web.help_catalog import CATEGORIES, TOPICS, related

logger = logging.getLogger(__name__)


class HelpRoutes:
    def __init__(self, app: FastAPI, store):
        self.app = app
        self.store = store
        self._register_routes()

    def _register_routes(self) -> None:
        add = self.app.add_api_route
        add("/help", self.index, methods=["GET"], name="help", include_in_schema=False)
        for slug in TOPICS:
            add(f"/help/{slug}", self._page(slug), methods=["GET"],
                name=f"help_{slug.replace('-', '_')}", include_in_schema=False)

    async def index(self, request: Request):
        return render(request, "help/index.html", categories=CATEGORIES,
                      topics=TOPICS)

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
