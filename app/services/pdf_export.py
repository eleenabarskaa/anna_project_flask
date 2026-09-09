"""Экспорт брифа из researched_documents в PDF.

Источник — тот же санированный HTML, что показывается на странице
(`app/services/markdown_render.py`), поэтому PDF и экран не расходятся.
HTML разбирается в набор flowable-элементов reportlab: заголовки, абзацы,
списки и таблицы.

Почему reportlab, а не HTML→PDF конвертер: WeasyPrint требует системных
библиотек (pango, cairo), которых может не оказаться на хостинге, а
reportlab — чистый Python с колёсами под все платформы.

Шрифт DejaVu Sans лежит в репозитории (app/static/fonts). Встроенная
Helvetica умеет только latin-1 и спотыкается на кириллице и части типографики,
а наличие системных шрифтов на сервере не гарантировано.
"""

from __future__ import annotations

import io
import re
from html.parser import HTMLParser
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models import ResearchDocument
from app.services.markdown_render import render_brief

FONTS_DIR = Path(__file__).resolve().parents[1] / "static" / "fonts"

INK = colors.HexColor("#12161B")
INK_SOFT = colors.HexColor("#4A5157")
LINE = colors.HexColor("#D6D9DB")
PANEL = colors.HexColor("#F4F5F5")
BLUE = colors.HexColor("#2F5C99")

PAGE_MARGIN = 18 * mm
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

_fonts_ready = False


def _register_fonts() -> tuple[str, str]:
    """Возвращает (обычный, жирный). При отсутствии файлов — Helvetica."""
    global _fonts_ready
    regular, bold = FONTS_DIR / "DejaVuSans.ttf", FONTS_DIR / "DejaVuSans-Bold.ttf"
    if not (regular.exists() and bold.exists()):
        return "Helvetica", "Helvetica-Bold"
    if not _fonts_ready:
        pdfmetrics.registerFont(TTFont("DejaVu", str(regular)))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(bold)))
        pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold")
        _fonts_ready = True
    return "DejaVu", "DejaVu-Bold"


def _styles(font: str, font_bold: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["BodyText"]
    common = {"textColor": INK, "alignment": TA_LEFT}

    return {
        "title": ParagraphStyle("title", base, fontName=font_bold, fontSize=19, leading=24,
                                spaceAfter=2, textColor=INK),
        "subtitle": ParagraphStyle("subtitle", base, fontName=font, fontSize=9.5, leading=13,
                                   textColor=INK_SOFT, spaceAfter=2),
        "meta": ParagraphStyle("meta", base, fontName=font, fontSize=8, leading=11,
                               textColor=INK_SOFT, spaceAfter=0),
        "h1": ParagraphStyle("h1", base, fontName=font_bold, fontSize=15, leading=19,
                             spaceBefore=14, spaceAfter=6, **common),
        "h2": ParagraphStyle("h2", base, fontName=font_bold, fontSize=12, leading=16,
                             spaceBefore=16, spaceAfter=6, **common),
        "h3": ParagraphStyle("h3", base, fontName=font_bold, fontSize=10.5, leading=14,
                             spaceBefore=11, spaceAfter=4, **common),
        "h4": ParagraphStyle("h4", base, fontName=font_bold, fontSize=9.5, leading=13,
                             spaceBefore=9, spaceAfter=3, textColor=INK_SOFT, alignment=TA_LEFT),
        "body": ParagraphStyle("body", base, fontName=font, fontSize=9.5, leading=14,
                               spaceAfter=7, **common),
        "li": ParagraphStyle("li", base, fontName=font, fontSize=9.5, leading=13.5,
                             spaceAfter=2, **common),
        "quote": ParagraphStyle("quote", base, fontName=font, fontSize=9.5, leading=13.5,
                                leftIndent=10, textColor=INK_SOFT, spaceAfter=7),
        "th": ParagraphStyle("th", base, fontName=font_bold, fontSize=7.5, leading=10,
                             textColor=INK_SOFT, spaceAfter=0),
        "td": ParagraphStyle("td", base, fontName=font, fontSize=7.5, leading=10.5,
                             textColor=INK, spaceAfter=0),
    }


# --- разбор HTML ---------------------------------------------------------

INLINE_KEEP = {"b", "strong", "i", "em", "u", "sub", "super", "sup", "br", "a"}
BLOCK_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "blockquote", "li", "th", "td"}


class _BriefParser(HTMLParser):
    """HTML → плоский список блоков.

    Абзацы и ячейки собираются в мини-разметку, понятную Paragraph reportlab
    (<b>, <i>, <a href>, <br/>), остальные теги отбрасываются.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[dict] = []
        self._buf: list[str] = []
        self._block: str | None = None
        self._list: list[str] | None = None
        self._list_ordered = False
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._in_head = False

    # -- служебное
    def _flush(self) -> str:
        text = _WS_RE.sub(" ", "".join(self._buf)).strip()
        self._buf = []
        return text

    def _emit(self, kind: str, **payload) -> None:
        self.blocks.append({"kind": kind, **payload})

    # -- теги
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("ul", "ol"):
            self._list, self._list_ordered = [], tag == "ol"
        elif tag == "table":
            self._table = []
        elif tag == "tr":
            self._row = []
        elif tag == "thead":
            self._in_head = True
        elif tag in BLOCK_TAGS:
            self._block = tag
            self._buf = []
        elif tag == "hr":
            self._emit("hr")
        elif tag == "br":
            self._buf.append("<br/>")
        elif tag in ("b", "strong"):
            self._buf.append("<b>")
        elif tag in ("i", "em"):
            self._buf.append("<i>")
        elif tag == "a" and attrs.get("href"):
            href = attrs["href"].replace('"', "%22")
            self._buf.append(f'<a href="{href}" color="#2F5C99">')
        elif tag == "code":
            self._buf.append("<i>")

    def handle_endtag(self, tag):
        if tag in ("ul", "ol"):
            if self._list:
                self._emit("list", items=self._list, ordered=self._list_ordered)
            self._list = None
        elif tag == "thead":
            self._in_head = False
        elif tag == "tr":
            if self._row is not None and self._table is not None:
                self._table.append(self._row)
            self._row = None
        elif tag == "table":
            if self._table:
                self._emit("table", rows=self._table)
            self._table = None
        elif tag in ("th", "td"):
            if self._row is not None:
                self._row.append(self._flush())
            self._block = None
        elif tag == "li":
            text = self._flush()
            if text and self._list is not None:
                self._list.append(text)
            self._block = None
        elif tag in BLOCK_TAGS:
            text = self._flush()
            if text:
                self._emit("heading" if tag.startswith("h") else "para", tag=tag, text=text)
            self._block = None
        elif tag in ("b", "strong"):
            self._buf.append("</b>")
        elif tag in ("i", "em", "code"):
            self._buf.append("</i>")
        elif tag == "a":
            self._buf.append("</a>")

    def handle_data(self, data):
        if self._block or self._list is not None or self._row is not None:
            self._buf.append(data.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _parse(html: str) -> list[dict]:
    parser = _BriefParser()
    parser.feed(html)
    parser.close()
    return parser.blocks


# --- сборка flowables ----------------------------------------------------

def _table_flowable(rows: list[list[str]], styles, available_width: float) -> Table:
    columns = max(len(r) for r in rows)
    normalised = [r + [""] * (columns - len(r)) for r in rows]

    head, *body = normalised
    data = [[Paragraph(c, styles["th"]) for c in head]]
    data += [[Paragraph(c, styles["td"]) for c in row] for row in body]

    table = Table(
        data,
        colWidths=[available_width / columns] * columns,
        repeatRows=1,
        hAlign="LEFT",
    )
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("BACKGROUND", (0, 0), (-1, 0), PANEL),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _flowables(blocks: list[dict], styles, available_width: float) -> list:
    out: list = []
    for block in blocks:
        kind = block["kind"]
        if kind == "heading":
            level = block["tag"]
            style = styles.get(level if level in styles else "h4", styles["h4"])
            out.append(Paragraph(block["text"], style))
        elif kind == "para":
            style = styles["quote"] if block["tag"] == "blockquote" else styles["body"]
            out.append(Paragraph(block["text"], style))
        elif kind == "list":
            items = [ListItem(Paragraph(t, styles["li"]), leftIndent=12) for t in block["items"]]
            out.append(ListFlowable(
                items,
                bulletType="1" if block["ordered"] else "bullet",
                bulletFontName=styles["li"].fontName,
                bulletFontSize=7,
                leftIndent=14,
                spaceAfter=8,
            ))
        elif kind == "table":
            out.append(Spacer(1, 3))
            out.append(_table_flowable(block["rows"], styles, available_width))
            out.append(Spacer(1, 9))
        elif kind == "hr":
            out.append(Spacer(1, 5))
            out.append(HRFlowable(width="100%", thickness=0.5, color=LINE, spaceAfter=7))
    return out


def _header(document: ResearchDocument, styles, available_width: float) -> list:
    meta = " · ".join(
        part for part in (
            document.document_type or None,
            document.status or None,
            f"researched {document.researched_at}" if document.researched_at else None,
        ) if part
    )
    head = [
        Paragraph(document.name, styles["title"]),
        Paragraph(document.source_query or "Public-source research", styles["subtitle"]),
    ]
    if meta:
        head.append(Paragraph(meta, styles["meta"]))
    head.append(Spacer(1, 6))
    head.append(HRFlowable(width="100%", thickness=0.8, color=INK, spaceAfter=12))
    return [KeepTogether(head)]


def _page_furniture(document: ResearchDocument, font: str):
    """Колонтитул: имя слева, номер страницы справа."""

    def draw(canvas, doc):  # noqa: ANN001
        canvas.saveState()
        canvas.setFont(font, 7)
        canvas.setFillColor(INK_SOFT)
        canvas.drawString(PAGE_MARGIN, 12 * mm, f"{document.name} · Meridian prospect brief")
        canvas.drawRightString(A4[0] - PAGE_MARGIN, 12 * mm, str(canvas.getPageNumber()))
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.4)
        canvas.line(PAGE_MARGIN, 15 * mm, A4[0] - PAGE_MARGIN, 15 * mm)
        canvas.restoreState()

    return draw


def build_pdf(document: ResearchDocument) -> bytes:
    """Собрать PDF из брифа. Пустой markdown — короткая страница-заглушка."""
    font, font_bold = _register_fonts()
    styles = _styles(font, font_bold)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=PAGE_MARGIN,
        rightMargin=PAGE_MARGIN,
        topMargin=PAGE_MARGIN,
        bottomMargin=22 * mm,
        title=f"{document.name} — prospect brief",
        author="Meridian Prospecting Desk",
        subject=document.source_query or "",
    )
    available_width = doc.width

    story = _header(document, styles, available_width)
    brief = render_brief(document.full_markdown)
    if brief.empty:
        story.append(Paragraph(
            "Для этой записи ещё нет содержимого: колонка full_markdown пуста.",
            styles["body"],
        ))
    else:
        story.extend(_flowables(_parse(str(brief.html)), styles, available_width))

    draw = _page_furniture(document, font)
    doc.build(story, onFirstPage=draw, onLaterPages=draw)
    return buffer.getvalue()


def pdf_filename(document: ResearchDocument) -> str:
    """Безопасное имя файла: 'Miuccia Prada' → 'miuccia-prada-brief.pdf'."""
    base = (document.normalized_name or document.name or "brief").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return f"{slug or 'prospect'}-brief.pdf"
