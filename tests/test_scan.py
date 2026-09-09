"""Тесты кнопки «Find triggers».

Сеть не трогаем: сам скрейпинг и POST в n8n подменяются заглушками,
таблица trigger_jobs — фейковым репозиторием. Проверяется именно пайплайн:
скрейпинг → отправка в n8n → опрос задачи → «Found N · Added M».
"""

import time

import pytest
import requests

from app import create_app
from app.scraping import scraper, sources
from app.services import scanner
from app.services.scanner import ScanService, registry

ARTICLES = [
    {
        "category": "PE Exit",
        "url": "https://bebeez.it/a",
        "domain": "bebeez.it",
        "title": "Fondo cede la quota di maggioranza",
        "published_meta": "2026-09-01",
        "text": "x" * 400,
    },
    {
        "category": "PE Exit",
        "url": "https://bebeez.it/b",
        "domain": "bebeez.it",
        "title": "Private equity exit",
        "published_meta": "2026-09-02",
        "text": "y" * 400,
    },
]

CONFIG = {
    "N8N_TRIGGERS_SCAN_WEBHOOK_URL": "https://n8n.example/webhook/scan",
    "N8N_WEBHOOK_TIMEOUT": 5,
    "SCAN_POLL_TIMEOUT": 6,
    "SCAN_POLL_INTERVAL": 0,
}


class FakeJobRepo:
    """Имитация таблицы trigger_jobs: n рефрешей 'running', затем результат."""

    def __init__(self, result: dict, delay_polls: int = 1) -> None:
        self.result = result
        self.delay_polls = delay_polls
        self.calls = 0

    def get(self, job_id: str):
        self.calls += 1
        if self.calls <= self.delay_polls:
            return {"status": "running", "inserted_count": None, "error": None}
        return self.result


class FakeResponse:
    def __init__(self, status_code=200, text="ok"):
        self.status_code = status_code
        self.text = text


@pytest.fixture
def sent(monkeypatch):
    """Перехватываем POST в n8n и возвращаем список отправленных payload'ов."""
    captured = []

    def fake_post(url, json=None, timeout=None):  # noqa: A002
        captured.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr(scanner.requests, "post", fake_post)
    return captured


@pytest.fixture
def fake_scrape(monkeypatch):
    def use(articles, raises=None):
        def fake_scan(category_key, months=3, progress_callback=None, should_stop=None):
            if progress_callback:
                progress_callback(f"Scanning example.com ... ({category_key}, {months} mo)")
            if raises:
                raise raises
            return articles

        monkeypatch.setattr(scanner, "scan_category", fake_scan)

    return use


def wait_for(job, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if job.status != scanner.RUNNING:
            return job
        time.sleep(0.02)
    raise AssertionError(f"Задача не завершилась за {timeout}s (stage={job.stage})")


# --- конфигурация источников --------------------------------------------

def test_every_category_key_exists_in_domain_config():
    """Регрессия: в Streamlit-версии ключ IPO не совпадал с файлом конфигурации,
    и категория молча сканировала ноль источников."""
    for label, key in sources.CATEGORIES:
        domains, _ = sources.get_scope(key)
        assert domains, f"У категории {label!r} (ключ {key!r}) нет источников"


def test_old_russian_ipo_key_still_resolves():
    domains, _ = sources.get_scope("IPO / Листинг")
    assert domains == sources.get_scope("IPO / Listing")[0]


def test_unknown_category_is_rejected():
    assert sources.is_known_category("PE Exit")
    assert not sources.is_known_category("Nonsense")


def test_keyword_sets_cover_all_categories():
    for _, key in sources.CATEGORIES:
        assert key in scraper.KEYWORD_SETS, f"Нет ключевых слов для {key!r}"


def test_relevance_filter_uses_category_keywords():
    assert scraper._looks_relevant("Il fondo cede la quota", "PE Exit")
    assert not scraper._looks_relevant("Ricetta della pizza", "PE Exit")


# --- пайплайн ------------------------------------------------------------

def test_happy_path_reports_found_and_added(fake_scrape, sent):
    fake_scrape(ARTICLES)
    service = ScanService(CONFIG, job_repo=FakeJobRepo({"status": "done", "inserted_count": 7}))
    job = wait_for(service.start("PE Exit", "PE Exit", 3))

    assert job.status == "done"
    assert (job.found, job.added) == (2, 7)
    assert job.error is None
    assert any("Scanning example.com" in line for line in job.log)


def test_payload_matches_streamlit_contract(fake_scrape, sent):
    fake_scrape(ARTICLES)
    service = ScanService(CONFIG, job_repo=FakeJobRepo({"status": "done", "inserted_count": 1}))
    job = wait_for(service.start("PE Exit", "PE Exit", 4))

    assert len(sent) == 1
    payload = sent[0]["json"]
    assert payload["action"] == "scan_trigger"
    assert payload["category"] == "PE Exit"
    assert payload["job_id"] == job.id
    assert payload["articles"] == ARTICLES


def test_no_articles_finishes_without_calling_n8n(fake_scrape, sent):
    fake_scrape([])
    service = ScanService(CONFIG, job_repo=FakeJobRepo({"status": "done", "inserted_count": 5}))
    job = wait_for(service.start("PE Exit", "PE Exit", 3))

    assert job.status == "done"
    assert (job.found, job.added) == (0, 0)
    assert sent == []


def test_scraping_failure_is_reported(fake_scrape, sent):
    fake_scrape(None, raises=RuntimeError("boom"))
    service = ScanService(CONFIG, job_repo=FakeJobRepo({"status": "done"}))
    job = wait_for(service.start("PE Exit", "PE Exit", 3))

    assert job.status == "error"
    assert "boom" in job.error
    assert sent == []


def test_missing_webhook_is_reported(fake_scrape, sent):
    fake_scrape(ARTICLES)
    service = ScanService({**CONFIG, "N8N_TRIGGERS_SCAN_WEBHOOK_URL": None}, job_repo=None)
    job = wait_for(service.start("PE Exit", "PE Exit", 3))

    assert job.status == "error"
    assert "N8N_TRIGGERS_SCAN_WEBHOOK_URL" in job.error
    assert sent == []


def test_n8n_non_200_is_reported(fake_scrape, monkeypatch):
    fake_scrape(ARTICLES)
    monkeypatch.setattr(
        scanner.requests, "post", lambda *a, **kw: FakeResponse(500, "internal error")
    )
    job = wait_for(ScanService(CONFIG, job_repo=None).start("PE Exit", "PE Exit", 3))

    assert job.status == "error"
    assert "500" in job.error


def test_n8n_unreachable_is_reported(fake_scrape, monkeypatch):
    fake_scrape(ARTICLES)

    def boom(*a, **kw):
        raise requests.exceptions.ConnectionError("no route")

    monkeypatch.setattr(scanner.requests, "post", boom)
    job = wait_for(ScanService(CONFIG, job_repo=None).start("PE Exit", "PE Exit", 3))

    assert job.status == "error"
    assert "n8n" in job.error


def test_job_error_from_supabase_is_reported(fake_scrape, sent):
    fake_scrape(ARTICLES)
    repo = FakeJobRepo({"status": "error", "error": "LLM node failed"})
    job = wait_for(ScanService(CONFIG, job_repo=repo).start("PE Exit", "PE Exit", 3))

    assert job.status == "error"
    assert job.error == "LLM node failed"


def test_poll_timeout_is_reported(fake_scrape, sent):
    fake_scrape(ARTICLES)
    repo = FakeJobRepo({"status": "done", "inserted_count": 1}, delay_polls=10_000)
    config = {**CONFIG, "SCAN_POLL_TIMEOUT": 0}
    job = wait_for(ScanService(config, job_repo=repo).start("PE Exit", "PE Exit", 3))

    assert job.status == "error"
    assert "Истекло время" in job.error


def test_without_job_repo_stops_after_handoff(fake_scrape, sent):
    fake_scrape(ARTICLES)
    job = wait_for(ScanService(CONFIG, job_repo=None).start("PE Exit", "PE Exit", 3))

    assert job.status == "done"
    assert job.found == 2 and job.added is None


# --- страница и API ------------------------------------------------------

@pytest.fixture
def client():
    app = create_app("testing")
    app.config["N8N_TRIGGERS_SCAN_WEBHOOK_URL"] = CONFIG["N8N_TRIGGERS_SCAN_WEBHOOK_URL"]
    app.config["SCAN_POLL_INTERVAL"] = 0
    app.config["SCAN_POLL_TIMEOUT"] = 6
    with app.test_client() as c:
        yield c


def test_page_shows_scan_form(client):
    from markupsafe import escape

    body = client.get("/triggers").get_data(as_text=True)
    assert "Find triggers" in body
    for label, _ in sources.CATEGORIES:
        assert str(escape(label)) in body  # «M&A …» приходит как «M&amp;A …»


def test_button_starts_job_and_page_shows_result(client, fake_scrape, sent):
    fake_scrape(ARTICLES)
    resp = client.post("/triggers/scan", data={"scan_category": "PE Exit", "scan_months": "3"})
    assert resp.status_code == 302
    job_id = resp.headers["Location"].split("job=")[1]

    wait_for(registry.get(job_id))
    body = client.get(f"/triggers?job={job_id}").get_data(as_text=True)
    assert "Found 2 article(s)" in body
    assert "Added 0 new trigger(s)." in body  # memory-бэкенд не опрашивает trigger_jobs


def test_unknown_category_rejected_by_form(client):
    assert client.post("/triggers/scan", data={"scan_category": "Nope"}).status_code == 400


def test_api_start_status_and_conflict(client, fake_scrape, sent):
    fake_scrape(ARTICLES)
    started = client.post("/api/v1/scan", json={"category": "PE Exit", "months": 2})
    assert started.status_code == 202
    job_id = started.get_json()["id"]

    status = client.get(f"/api/v1/scan/{job_id}").get_json()
    assert status["category_key"] == "PE Exit" and status["months"] == 2

    wait_for(registry.get(job_id))
    assert client.get("/api/v1/scan/missing").status_code == 404


def test_api_rejects_unknown_category(client):
    resp = client.post("/api/v1/scan", json={"category": "Nope"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "unknown_category"


def test_scan_can_be_cancelled(monkeypatch, client):
    """Долгий скрейпинг прерывается кнопкой Stop."""

    def slow_scan(category_key, months=3, progress_callback=None, should_stop=None):
        for _ in range(500):
            if should_stop and should_stop():
                raise scraper.ScanCancelled
            time.sleep(0.01)
        return ARTICLES

    monkeypatch.setattr(scanner, "scan_category", slow_scan)
    started = client.post("/api/v1/scan", json={"category": "PE Exit"})
    job_id = started.get_json()["id"]

    assert client.post(f"/api/v1/scan/{job_id}/stop").status_code == 200
    job = wait_for(registry.get(job_id))
    assert job.status == "cancelled"
