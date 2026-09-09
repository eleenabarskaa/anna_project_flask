"""Тесты кнопки «Build brief» на вкладке Command.

Контракт с n8n тот же, что в Streamlit-версии: POST {message, mode, session_id}
→ {job_id} → опрос таблицы chat_jobs до status = done | error.
Сеть не трогаем: requests.post и chat_jobs подменяются заглушками.
"""

import time

import pytest
import requests

from app import create_app
from app.services import brief_runner
from app.services.brief_runner import BriefService, registry

CONFIG = {
    "PROSPECT_BRIEF_NEW_RUN_WEBHOOK_URL": "https://n8n.example/webhook/brief",
    "N8N_WEBHOOK_TIMEOUT": 5,
    "BRIEF_POLL_TIMEOUT": 6,
    "BRIEF_POLL_INTERVAL": 0,
}

REPLY_MD = "# Brief\n\n**Prospect:** Marco Rossi\n\n- Founder, sold 60% in 2025.\n"


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text="ok"):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class FakeChatJobs:
    def __init__(self, result, delay_polls=1):
        self.result = result
        self.delay_polls = delay_polls
        self.calls = 0

    def get(self, job_id):
        self.calls += 1
        if self.calls <= self.delay_polls:
            return {"status": "running", "reply": None}
        return self.result


@pytest.fixture
def posted(monkeypatch):
    captured = []

    def fake_post(url, json=None, timeout=None):  # noqa: A002
        captured.append({"url": url, "json": json})
        return FakeResponse(payload={"job_id": "n8n-job-1"})

    monkeypatch.setattr(brief_runner.requests, "post", fake_post)
    return captured


def wait_for(job, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if job.status != brief_runner.RUNNING:
            return job
        time.sleep(0.02)
    raise AssertionError(f"Задача не завершилась (stage={job.stage})")


# --- пайплайн ------------------------------------------------------------

def test_payload_matches_streamlit_contract(posted):
    service = BriefService(CONFIG, chat_jobs=FakeChatJobs({"status": "done", "reply": REPLY_MD}))
    job = wait_for(service.start("founders who exited a Swiss industrial group"))

    assert len(posted) == 1
    body = posted[0]["json"]
    assert body["message"] == "founders who exited a Swiss industrial group"
    assert body["mode"] == "new_run"
    assert body["session_id"] == job.session_id
    assert posted[0]["url"] == CONFIG["PROSPECT_BRIEF_NEW_RUN_WEBHOOK_URL"]


def test_reply_is_returned_from_chat_jobs(posted):
    service = BriefService(CONFIG, chat_jobs=FakeChatJobs({"status": "done", "reply": REPLY_MD}))
    job = wait_for(service.start("Marco Rossi"))

    assert job.status == "done"
    assert "Marco Rossi" in job.reply
    assert job.error is None


def test_synchronous_reply_without_job_id(monkeypatch):
    """Как в Streamlit: если вебхук ответил текстом, показываем его."""
    monkeypatch.setattr(
        brief_runner.requests, "post",
        lambda *a, **kw: FakeResponse(payload=None, text="Plain text answer"),
    )
    job = wait_for(BriefService(CONFIG, chat_jobs=None).start("Marco Rossi"))

    assert job.status == "done"
    assert job.reply == "Plain text answer"


def test_agent_error_is_surfaced(posted):
    repo = FakeChatJobs({"status": "error", "reply": "LLM node failed"})
    job = wait_for(BriefService(CONFIG, chat_jobs=repo).start("Marco Rossi"))

    assert job.status == "error"
    assert job.error == "LLM node failed"


def test_missing_webhook_is_reported(posted):
    config = {**CONFIG, "PROSPECT_BRIEF_NEW_RUN_WEBHOOK_URL": None}
    job = wait_for(BriefService(config, chat_jobs=None).start("Marco Rossi"))

    assert job.status == "error"
    assert "PROSPECT_BRIEF_NEW_RUN_WEBHOOK_URL" in job.error
    assert posted == []


def test_non_200_is_reported(monkeypatch):
    monkeypatch.setattr(
        brief_runner.requests, "post",
        lambda *a, **kw: FakeResponse(status_code=404, text="not registered"),
    )
    job = wait_for(BriefService(CONFIG, chat_jobs=None).start("Marco Rossi"))

    assert job.status == "error"
    assert "404" in job.error


def test_unreachable_n8n_is_reported(monkeypatch):
    def boom(*a, **kw):
        raise requests.exceptions.ConnectionError("no route")

    monkeypatch.setattr(brief_runner.requests, "post", boom)
    job = wait_for(BriefService(CONFIG, chat_jobs=None).start("Marco Rossi"))

    assert job.status == "error"
    assert "n8n" in job.error


def test_poll_timeout_is_reported(posted):
    repo = FakeChatJobs({"status": "done", "reply": REPLY_MD}, delay_polls=10_000)
    job = wait_for(BriefService({**CONFIG, "BRIEF_POLL_TIMEOUT": 0}, chat_jobs=repo).start("X"))

    assert job.status == "error"
    assert "не ответил" in job.error


# --- страница и API ------------------------------------------------------

@pytest.fixture
def client():
    app = create_app("testing")
    app.config["PROSPECT_BRIEF_NEW_RUN_WEBHOOK_URL"] = CONFIG["PROSPECT_BRIEF_NEW_RUN_WEBHOOK_URL"]
    app.config["BRIEF_POLL_INTERVAL"] = 0
    app.config["BRIEF_POLL_TIMEOUT"] = 6
    with app.test_client() as c:
        yield c


def test_command_tab_has_build_brief_form(client):
    body = client.get("/?variant=command").get_data(as_text=True)
    assert "Build brief" in body
    assert '/brief/run' in body


def test_button_starts_job_and_page_shows_reply(client, posted, monkeypatch):
    # memory-бэкенд не умеет chat_jobs, поэтому подменяем ответ вебхука на синхронный
    monkeypatch.setattr(
        brief_runner.requests, "post",
        lambda *a, **kw: FakeResponse(payload=None, text=REPLY_MD),
    )
    resp = client.post("/brief/run", data={"q": "Marco Rossi"})
    assert resp.status_code == 302
    job_id = resp.headers["Location"].split("job=")[1]

    wait_for(registry.get(job_id))
    body = client.get(f"/?variant=command&job={job_id}").get_data(as_text=True)
    assert "Marco Rossi" in body
    assert "<h1" in body          # ответ агента отрендерен как markdown


def test_empty_query_does_not_start_job(client):
    before = registry.running()
    client.post("/brief/run", data={"q": "   "})
    assert registry.running() is before


def test_api_start_and_status(client, monkeypatch):
    monkeypatch.setattr(
        brief_runner.requests, "post",
        lambda *a, **kw: FakeResponse(payload=None, text="done"),
    )
    started = client.post("/api/v1/brief", json={"q": "Marco Rossi"})
    assert started.status_code == 202
    job_id = started.get_json()["id"]

    wait_for(registry.get(job_id))
    status = client.get(f"/api/v1/brief/{job_id}").get_json()
    assert status["query"] == "Marco Rossi" and status["finished"] is True
    assert client.get("/api/v1/brief/missing").status_code == 404


def test_api_rejects_empty_query(client):
    resp = client.post("/api/v1/brief", json={"q": ""})
    assert resp.status_code == 400 and resp.get_json()["error"] == "empty_query"


# --- главная страница ----------------------------------------------------

def test_desk_has_no_tasks_widget(client):
    body = client.get("/").get_data(as_text=True)
    assert "Today" not in body
    assert "Refresh source licences" not in body


def test_desk_kpis_are_computed_from_data(client):
    body = client.get("/").get_data(as_text=True)
    assert "New triggers · 24h" in body
    assert "of 1 tracked" in body        # watchlist из demo-данных
    assert "of 3 total" in body          # всего брифов


def test_desk_watchlist_links_to_real_documents(client):
    doc = client.get("/api/v1/desk/watchlist").get_json()["items"][0]
    body = client.get("/").get_data(as_text=True)
    assert doc["name"] in body
    assert f"/prospects/{doc['id']}" in body
