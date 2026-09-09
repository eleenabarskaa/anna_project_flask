"""Тесты Supabase-бэкенда.

Реальную базу не дёргаем: поднимаем локальный HTTP-сервер, который отвечает
как PostgREST (включая заголовок Content-Range), и проверяем маппинг полей,
пагинацию, фильтр по категории и поведение при недоступном источнике.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from app import create_app
from app.repositories.supabase import (
    PostgrestClient,
    PostgrestError,
    SupabaseTriggerRepository,
    row_to_trigger,
)

ROWS = [
    {
        "id": "8b5853e9-e459-405b-88eb-de48350a4fe8",
        "event_date": "2026-09-04",
        "company_or_person": "Telecom Italia (Tim) (bidder: Poste Italiane)",
        "trigger_type": "M&A / Liquidity event",
        "context": (
            "Poste Italiane ha lanciato un'opas su Tim il 20 luglio, offrendo 1,67 euro in "
            "contanti più 0,218 azioni Poste di nuova emissione per ogni azione Tim. "
            "Si valuta un possibile rilancio in denaro."
        ),
        "bidder": "Poste Italiane",
        "seller": None,
        "source": "https://www.milanofinanza.it/news/poste-rilancera-l-opas-su-tim-202609041954462183",
        "created_at": "2026-09-06 16:05:48.342523+00",
        "updated_at": "2026-09-06 16:05:48.342523+00",
        "founded": "llm",
    },
    {
        "id": "78ae1d72-6ae4-479c-8458-b4f04b898ffb",
        "event_date": "2026-09-03",
        "company_or_person": "Gruppo Turatti (seller: Taste of Italy fund)",
        "trigger_type": "PE Exit",
        "context": "Green Arrow Capital ha siglato un accordo vincolante per la cessione del 100%.",
        "bidder": "Grote Company Family of Brands",
        "seller": "Green Arrow Capital",
        "source": "https://bebeez.it/private-equity/green-arrow-capital-cede-turatti/",
        "created_at": "2026-09-06 16:05:48.342523+00",
        "updated_at": "2026-09-06 16:05:48.342523+00",
        "founded": "llm",
    },
]


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        url = urlparse(self.path)
        params = parse_qs(url.query)

        rows = ROWS
        if "trigger_type" in params:
            wanted = params["trigger_type"][0].removeprefix("eq.")
            rows = [r for r in rows if r["trigger_type"] == wanted]
        if "id" in params:
            wanted = params["id"][0].removeprefix("eq.")
            rows = [r for r in rows if r["id"] == wanted]

        total = len(rows)
        window = rows
        rng = self.headers.get("Range")
        if rng:
            start, end = (int(x) for x in rng.split("-"))
            window = rows[start : end + 1]

        body = json.dumps(window).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Range", f"0-{max(len(window) - 1, 0)}/{total}")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # тишина в выводе тестов
        pass


@pytest.fixture(scope="module")
def fake_supabase():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture
def repo(fake_supabase):
    return SupabaseTriggerRepository(PostgrestClient(fake_supabase, "test-key"))


# --- маппинг -------------------------------------------------------------

def test_mapping_strips_role_suffix_from_company():
    assert row_to_trigger(ROWS[0]).company == "Telecom Italia (Tim)"
    assert row_to_trigger(ROWS[1]).company == "Gruppo Turatti"


def test_headline_is_first_sentence_not_whole_context():
    t = row_to_trigger(ROWS[0])
    assert t.headline.startswith("Poste Italiane ha lanciato")
    assert "rilancio" not in t.headline
    assert len(t.headline) <= 161


def test_missing_fields_stay_none():
    t = row_to_trigger(ROWS[0])
    assert (t.est, t.confidence, t.confidence_pct, t.people) == (None, None, None, [])
    assert t.heat == "faint"


def test_parties_and_source_and_dates():
    a, b = row_to_trigger(ROWS[0]), row_to_trigger(ROWS[1])
    assert a.parties == "Buyer: Poste Italiane"
    assert b.parties == "Buyer: Grote Company Family of Brands · Seller: Green Arrow Capital"
    assert a.source == "milanofinanza.it"
    assert a.date.isoformat() == "2026-09-04"
    assert a.ingested_at == "06 Sep 16:05"
    assert a.reviewer == "auto (LLM)"


def test_broken_row_does_not_crash():
    t = row_to_trigger({"id": "x"})
    assert t.company == "—" and t.headline == "Без описания" and t.source == "—"


# --- репозиторий ---------------------------------------------------------

def test_repo_list_and_count(repo):
    assert len(repo.list()) == 2
    assert repo.count() == 2


def test_repo_pagination(repo):
    first = repo.list(limit=1, offset=0)
    second = repo.list(limit=1, offset=1)
    assert len(first) == len(second) == 1
    assert first[0].id != second[0].id


def test_repo_category_filter(repo):
    rows = repo.list(category="PE Exit")
    assert [r.type for r in rows] == ["PE Exit"]
    assert repo.count(category="PE Exit") == 1


def test_repo_get_and_distinct_types(repo):
    assert repo.get(ROWS[0]["id"]).company == "Telecom Italia (Tim)"
    assert repo.get("missing") is None
    assert repo.distinct_types() == ["M&A / Liquidity event", "PE Exit"]


# --- интеграция с приложением -------------------------------------------

@pytest.fixture
def client(fake_supabase, monkeypatch):
    monkeypatch.setenv("REPOSITORY_BACKEND", "supabase")
    monkeypatch.setenv("SUPABASE_URL", fake_supabase)
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "test-key")
    app = create_app("testing")  # конфиг читает переменные окружения здесь и сейчас
    assert app.repos.backend == "supabase"
    with app.test_client() as c:
        yield c


def test_triggers_page_renders_live_rows(client):
    body = client.get("/triggers").get_data(as_text=True)
    assert "Telecom Italia (Tim)" in body
    assert "milanofinanza.it" in body
    assert "2 of 2 events" in body


def test_desk_page_renders_live_rows(client):
    assert "Gruppo Turatti" in client.get("/").get_data(as_text=True)


def test_api_serves_live_rows(client):
    data = client.get("/api/v1/triggers").get_json()
    assert data["meta"]["total"] == 2
    assert data["items"][0]["company"] == "Telecom Italia (Tim)"
    assert data["items"][0]["est"] is None


def test_unreachable_source_shows_banner_not_500():
    from app.repositories import build_repositories

    app = create_app("testing")
    app.repos = build_repositories(
        {
            "REPOSITORY_BACKEND": "supabase",
            "SUPABASE_URL": "http://127.0.0.1:1",  # заведомо закрытый порт
            "SUPABASE_SECRET_KEY": "test-key",
        }
    )
    with app.test_client() as c:
        resp = c.get("/triggers")
        assert resp.status_code == 200
        assert "Не удалось получить события" in resp.get_data(as_text=True)


def test_missing_credentials_fail_loudly():
    from app.repositories import build_repositories

    with pytest.raises(ValueError):
        build_repositories({"REPOSITORY_BACKEND": "supabase"})


def test_postgrest_error_on_http_status(fake_supabase):
    bad = PostgrestClient(fake_supabase, "test-key")
    bad.base_url = "http://127.0.0.1:1"
    with pytest.raises(PostgrestError):
        bad.select("triggers")
