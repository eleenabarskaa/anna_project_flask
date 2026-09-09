"""Тесты Prospect Brief поверх таблицы researched_documents."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, unquote, urlparse

import pytest

from app import create_app
from app.repositories.supabase import (
    PostgrestClient,
    SupabaseDocumentRepository,
    row_to_document,
)
from app.services.markdown_render import render_brief

MARKDOWN = """# PROSPECT ENRICHMENT BRIEF
## Public-Source Research | Italy

**Prospect name:** Miuccia Prada Bianchi

## 1. Executive Assessment

Miuccia Prada Bianchi is the creative and strategic cornerstone of the Prada Group.

### Ownership

| Entity | Role | Ownership |
|---|---|---|
| Prada Holding S.p.A. | Controlling shareholder | ~80% |
| Free float | HKEX Main Board | ~20% |

## 2. Liquidity History

- IPO on HKEX in June 2011, gross proceeds US$2.14 billion.
- Versace acquisition completed December 2025 (€1.25 billion EV).
"""

ROWS = [
    {
        "id": "93d8249d-4d5c-4067-be2e-9906430be077",
        "name": "Miuccia Prada",
        "normalized_name": "miuccia prada",
        "document_type": "person",
        "status": "completed",
        "source_query": "find information about Miuccia Prada",
        "researched_at": "2026-08-16 15:41:43.603605+00",
        "full_markdown": MARKDOWN,
    },
    {
        "id": "0c1f2b3a-1111-4222-8333-444455556666",
        "name": "Gruppo Turatti",
        "normalized_name": "gruppo turatti",
        "document_type": "company",
        "status": "running",
        "source_query": "find information about Gruppo Turatti",
        "researched_at": None,
        "full_markdown": "",
    },
]


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        url = urlparse(self.path)
        params = parse_qs(url.query)
        rows = ROWS

        if "id" in params:
            wanted = params["id"][0].removeprefix("eq.")
            rows = [r for r in rows if r["id"] == wanted]
        if "or" in params:
            # or=(name.ilike.*prada*,...) — вытаскиваем шаблон и ищем без регистра
            raw = unquote(params["or"][0])
            term = raw.split("ilike.", 1)[1].split(",")[0].strip("*)").lower()
            rows = [
                r for r in rows
                if term in (r["name"] or "").lower()
                or term in (r["normalized_name"] or "").lower()
                or term in (r["source_query"] or "").lower()
            ]

        # PostgREST отдаёт только запрошенные колонки
        select = params.get("select", ["*"])[0]
        if select != "*":
            keep = select.split(",")
            rows = [{k: r.get(k) for k in keep} for r in rows]

        total = len(rows)
        window = rows
        if rng := self.headers.get("Range"):
            start, end = (int(x) for x in rng.split("-"))
            window = rows[start : end + 1]

        body = json.dumps(window).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Range", f"0-{max(len(window) - 1, 0)}/{total}")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def fake_supabase():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture
def repo(fake_supabase):
    return SupabaseDocumentRepository(PostgrestClient(fake_supabase, "key"))


# --- маппинг -------------------------------------------------------------

def test_row_mapping():
    doc = row_to_document(ROWS[0])
    assert doc.name == "Miuccia Prada"
    assert doc.document_type == "person"
    assert doc.researched_at == "16 Aug 2026"
    assert doc.is_completed and doc.has_content


def test_row_without_markdown():
    doc = row_to_document(ROWS[1])
    assert not doc.is_completed
    assert not doc.has_content
    assert doc.researched_at is None


def test_broken_row_does_not_crash():
    doc = row_to_document({})
    assert doc.name == "—" and doc.id == "" and doc.full_markdown == ""


# --- рендер markdown -----------------------------------------------------

def test_render_produces_headings_and_tables():
    brief = render_brief(MARKDOWN)
    assert "<h1 id=" in brief.html and "<table>" in brief.html
    assert "<th>Entity</th>" in brief.html
    assert "<li>" in brief.html
    assert brief.word_count > 40 and not brief.empty


def test_render_builds_toc_with_anchors():
    brief = render_brief(MARKDOWN)
    titles = [item["title"] for item in brief.toc]
    assert "1. Executive Assessment" in titles
    assert "2. Liquidity History" in titles
    first = brief.toc[0]
    assert first["id"] and f'id="{first["id"]}"' in brief.html


def test_render_empty_markdown():
    for value in ("", "   ", None):
        assert render_brief(value).empty


def test_render_strips_dangerous_html():
    """Текст пишет LLM по материалам из интернета — доверять ему нельзя."""
    brief = render_brief(
        "# Title\n\n<script>alert('xss')</script>\n\n"
        "<img src=x onerror=alert(1)>\n\n"
        "[link](javascript:alert(1))\n"
    )
    html = str(brief.html)
    assert "<script" not in html and "onerror" not in html
    assert "javascript:" not in html


def test_render_keeps_external_links_safe():
    brief = render_brief("See [FT](https://www.ft.com/x) for details.")
    assert 'href="https://www.ft.com/x"' in brief.html
    assert 'rel="noopener noreferrer"' in brief.html


# --- репозиторий ---------------------------------------------------------

def test_repo_list_and_count(repo):
    rows, total = repo.list(with_count=True)
    assert len(rows) == 2 and total == 2


def test_repo_list_omits_markdown(repo):
    """В перечне full_markdown не запрашивается — колонка тяжёлая."""
    rows, _ = repo.list()
    assert all(not r.full_markdown for r in rows)


def test_repo_search(repo):
    rows, _ = repo.list(query="prada")
    assert [r.name for r in rows] == ["Miuccia Prada"]


def test_repo_pagination(repo):
    first, total = repo.list(limit=1, offset=0, with_count=True)
    second, _ = repo.list(limit=1, offset=1)
    assert total == 2 and first[0].id != second[0].id


def test_repo_get_returns_markdown(repo):
    doc = repo.get(ROWS[0]["id"])
    assert doc.name == "Miuccia Prada"
    assert "Executive Assessment" in doc.full_markdown
    assert repo.get("missing") is None


# --- страницы и API ------------------------------------------------------

@pytest.fixture
def client(fake_supabase, monkeypatch):
    monkeypatch.setenv("REPOSITORY_BACKEND", "supabase")
    monkeypatch.setenv("SUPABASE_URL", fake_supabase)
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "key")
    app = create_app("testing")
    with app.test_client() as c:
        yield c


def test_list_page_shows_live_rows(client):
    body = client.get("/prospects").get_data(as_text=True)
    assert "Miuccia Prada" in body
    assert "find information about Miuccia Prada" in body
    assert "completed" in body and "running" in body


def test_list_page_search(client):
    body = client.get("/prospects?q=turatti").get_data(as_text=True)
    assert "Gruppo Turatti" in body
    assert "Miuccia Prada" not in body


def test_detail_page_renders_markdown(client):
    body = client.get(f"/prospects/{ROWS[0]['id']}").get_data(as_text=True)
    assert "Executive Assessment" in body
    assert "<table>" in body                      # таблицы из брифа отрисованы
    assert "Contents" in body                     # оглавление собрано
    assert "Prada Holding S.p.A." in body


def test_detail_page_without_markdown_explains_why(client):
    body = client.get(f"/prospects/{ROWS[1]['id']}").get_data(as_text=True)
    assert "Gruppo Turatti" in body
    assert "full_markdown" in body


def test_detail_page_404(client):
    assert client.get("/prospects/00000000-0000-4000-8000-000000000000").status_code == 404


def test_api_list_excludes_markdown(client):
    data = client.get("/api/v1/prospects").get_json()
    assert data["meta"]["total"] == 2
    assert "full_markdown" not in data["items"][0]
    assert data["items"][0]["name"] == "Miuccia Prada"


def test_api_detail_returns_markdown_and_html(client):
    data = client.get(f"/api/v1/prospects/{ROWS[0]['id']}").get_json()
    assert data["document"]["full_markdown"].startswith("# PROSPECT ENRICHMENT BRIEF")
    assert "<table>" in data["html"]
    assert any(item["title"] == "1. Executive Assessment" for item in data["toc"])


def test_api_detail_404(client):
    resp = client.get("/api/v1/prospects/00000000-0000-4000-8000-000000000000")
    assert resp.status_code == 404 and resp.get_json()["error"] == "not_found"


def test_unreachable_source_shows_banner_not_500():
    from app.repositories import build_repositories

    app = create_app("testing")
    app.repos = build_repositories(
        {
            "REPOSITORY_BACKEND": "supabase",
            "SUPABASE_URL": "http://127.0.0.1:1",
            "SUPABASE_SECRET_KEY": "key",
        }
    )
    with app.test_client() as c:
        resp = c.get("/prospects")
        assert resp.status_code == 200
        assert "Не удалось получить" in resp.get_data(as_text=True)


# --- выгрузка в PDF ------------------------------------------------------

def _pdf_text(data: bytes) -> str:
    """Достаём текст из PDF без внешних зависимостей — через pdftotext,
    если он есть; иначе проверяем только структуру файла."""
    import shutil
    import subprocess
    import tempfile

    if not shutil.which("pdftotext"):
        return ""
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(data)
        f.flush()
        return subprocess.run(
            ["pdftotext", f.name, "-"], capture_output=True, text=True, check=False
        ).stdout


def test_pdf_is_built_from_markdown():
    from app.models import ResearchDocument
    from app.services.pdf_export import build_pdf

    data = build_pdf(row_to_document(ROWS[0]))
    assert data.startswith(b"%PDF-") and len(data) > 5000

    text = _pdf_text(data)
    if text:  # pdftotext доступен — проверяем содержимое
        assert "Miuccia Prada" in text
        assert "Executive Assessment" in text
        assert "Prada Holding S.p.A." in text        # строка таблицы
        assert "IPO on HKEX in June 2011" in text    # пункт списка


def test_pdf_handles_unicode_and_empty_markdown():
    from app.models import ResearchDocument
    from app.services.pdf_export import build_pdf

    cyrillic = ResearchDocument(
        id="x", name="Пример Компания",
        full_markdown="# Заголовок\n\nТекст с €1.25 млрд.\n",
    )
    assert build_pdf(cyrillic).startswith(b"%PDF-")

    empty = build_pdf(row_to_document(ROWS[1]))
    assert empty.startswith(b"%PDF-")
    text = _pdf_text(empty)
    if text:
        assert "Gruppo Turatti" in text


def test_pdf_filename_is_slugified():
    from app.services.pdf_export import pdf_filename

    assert pdf_filename(row_to_document(ROWS[0])) == "miuccia-prada-brief.pdf"


def test_download_pdf_route(client):
    resp = client.get(f"/prospects/{ROWS[0]['id']}/pdf")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert "miuccia-prada-brief.pdf" in resp.headers["Content-Disposition"]
    assert resp.data.startswith(b"%PDF-")


def test_download_pdf_404(client):
    assert client.get("/prospects/00000000-0000-4000-8000-000000000000/pdf").status_code == 404


def test_detail_page_offers_pdf_not_json(client):
    body = client.get(f"/prospects/{ROWS[0]['id']}").get_data(as_text=True)
    assert "Download PDF" in body
    assert "Export JSON" not in body
    assert f"/prospects/{ROWS[0]['id']}/pdf" in body
