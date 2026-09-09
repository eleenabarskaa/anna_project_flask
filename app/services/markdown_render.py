"""Рендер брифа из колонки `full_markdown` в безопасный HTML.

Содержимое пишет LLM-нода по материалам из открытых источников, то есть это
не доверенный ввод: результат конвертации пропускается через белый список
тегов и атрибутов. Заодно собирается оглавление по заголовкам второго уровня.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import bleach
import markdown as markdown_lib
from markupsafe import Markup

ALLOWED_TAGS = [
    "h1", "h2", "h3", "h4", "h5", "h6",
    "p", "br", "hr", "blockquote", "pre", "code",
    "ul", "ol", "li",
    "strong", "em", "b", "i", "u", "s", "sup", "sub",
    "table", "thead", "tbody", "tr", "th", "td",
    "a", "span", "div",
]

ALLOWED_ATTRS = {
    "a": ["href", "title", "rel", "target"],
    "th": ["align", "colspan", "rowspan"],
    "td": ["align", "colspan", "rowspan"],
    "h1": ["id"], "h2": ["id"], "h3": ["id"], "h4": ["id"], "h5": ["id"], "h6": ["id"],
    "span": ["class"], "div": ["class"],
}

_EXTENSIONS = ["tables", "sane_lists", "attr_list", "toc"]
_SLUG = re.compile(r"[^a-z0-9]+")


@dataclass
class RenderedBrief:
    html: Markup
    toc: list[dict]          # [{"id": ..., "title": ..., "level": 2}]
    word_count: int
    empty: bool


def _slugify(value: str, separator: str = "-") -> str:
    """Транслитерации не делаем — заголовки в брифах латиницей."""
    slug = _SLUG.sub(separator, value.strip().lower()).strip(separator)
    return slug or "section"


def _flatten_toc(tokens: list[dict], max_level: int = 3) -> list[dict]:
    flat: list[dict] = []
    for token in tokens:
        if token.get("level", 99) <= max_level:
            flat.append({
                "id": token.get("id", ""),
                "title": token.get("name", ""),
                "level": token.get("level", 2),
            })
        flat.extend(_flatten_toc(token.get("children", []), max_level))
    return flat


def render_brief(source: str | None) -> RenderedBrief:
    text = (source or "").strip()
    if not text:
        return RenderedBrief(html=Markup(""), toc=[], word_count=0, empty=True)

    md = markdown_lib.Markdown(
        extensions=_EXTENSIONS,
        extension_configs={"toc": {"slugify": lambda value, sep: _slugify(value, sep)}},
        output_format="html",
    )
    raw_html = md.convert(text)

    clean_html = bleach.clean(
        raw_html,
        tags=set(ALLOWED_TAGS),
        attributes=ALLOWED_ATTRS,
        protocols=["http", "https", "mailto"],
        strip=True,
    )
    clean_html = bleach.linkify(clean_html, callbacks=[_external_link])

    toc = _flatten_toc(getattr(md, "toc_tokens", []))
    return RenderedBrief(
        html=Markup(clean_html),
        toc=toc,
        word_count=len(text.split()),
        empty=False,
    )


def _external_link(attrs, new=False):  # noqa: ANN001, FBT002
    attrs[(None, "rel")] = "noopener noreferrer"
    attrs[(None, "target")] = "_blank"
    return attrs
