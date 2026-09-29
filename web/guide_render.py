"""
Full-reference guides and tutorials: Markdown in ``web/guides``, rendered
when opened (and cached until the file changes).

The rendering speaks the help system's visual language: code blocks become the
same captioned, copyable examples the topic pages use; ``!!! tip`` / ``!!!
warning`` / ``!!! note`` admonitions become the tip, warning and concept boxes;
tables are static reference tables; ``##`` and ``###`` headings feed the table of
contents. Guides are RetPlan's own files, never user input. After MAYA's guide_render.py.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

GUIDES_DIR = Path(__file__).resolve().parent / "guides"
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CODE = re.compile(r'<pre><code(?: class="language-([\w+-]+)")?>(.*?)</code></pre>', re.S)
_ADMONITION = {
    "tip": "tip",
    "warning": "warn",
    "danger": "warn",
    "note": "concept",
    "info": "concept",
    "example": "concept",
}


def path_of(slug: str) -> Path:
    return GUIDES_DIR / f"{slug}.md"


def _figure(match: re.Match[str]) -> str:
    lang = match.group(1) or "text"
    body = match.group(2)
    first = html.unescape(body).strip().splitlines()[0] if body.strip() else ""
    caption = first[2:].strip() if first.startswith(("# ", "// ")) and len(first) < 80 else lang
    return (
        f'<figure class="help-example"><figcaption><span><i class="bi bi-terminal" '
        f'aria-hidden="true"></i> {html.escape(caption)}</span><span class="lang">'
        f'{html.escape(lang)}</span><button type="button" class="copy" data-copy '
        f'aria-label="Copy this example"><i class="bi bi-clipboard" aria-hidden="true">'
        f"</i> Copy</button></figcaption><pre><code>{body}</code></pre></figure>"
    )


def _admonitions(text: str) -> str:
    def box(m: re.Match[str]) -> str:
        kind = _ADMONITION.get(m.group(1), "concept")
        return f'<div class="help-box {kind}">\n<p class="hb-title">'

    text = re.sub(r'<div class="admonition (\w+)">\s*<p class="admonition-title">', box, text)
    return text


def render(slug: str) -> dict[str, Any]:
    """{"html", "toc", "title"} for a guide; raises FileNotFoundError when absent."""
    import markdown

    path = path_of(slug)
    mtime = path.stat().st_mtime
    hit = _CACHE.get(slug)
    if hit and hit[0] == mtime:
        return hit[1]
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "sane_lists", "admonition", "attr_list", "toc"],
        extension_configs={"toc": {"toc_depth": "2-3", "permalink": False}},
    )
    body = md.convert(path.read_text(encoding="utf-8"))
    body = _CODE.sub(_figure, body)
    body = _admonitions(body)
    body = body.replace(
        "<table>", '<div class="help-table-wrap table-scroll"><table class="table table-sm">'
    ).replace("</table>", "</table></div>")
    body = re.sub(r"<h1[^>]*>.*?</h1>", "", body, count=1, flags=re.S)  # the page header has it
    toc = [
        {
            "id": t["id"],
            "name": t["name"],
            "children": [{"id": c["id"], "name": c["name"]} for c in t.get("children", [])],
        }
        for t in md.toc_tokens
    ]
    out = {"html": body, "toc": toc}
    _CACHE[slug] = (mtime, out)
    return out
