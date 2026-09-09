"""Сканирование источников по кнопке «Find triggers».

Порт логики из Streamlit-версии (`render_find_trigger_info_section`).
Отличие только в способе исполнения: Streamlit мог блокировать поток на
несколько минут, а HTTP-запрос столько жить не может — gunicorn убьёт воркер
по таймауту. Поэтому здесь:

    POST /triggers/scan   → создаёт задачу, сразу отдаёт её id
    GET  /api/v1/scan/<id> → статус, лог прогресса и итог

Порядок шагов сохранён один в один:
    1. scan_category() обходит источники категории и собирает статьи;
    2. статьи уходят POST-ом в n8n вместе с job_id;
    3. приложение опрашивает таблицу trigger_jobs, пока n8n не поставит
       status = done (inserted_count) или error;
    4. на странице появляется «Found N · Added M».

Задачи живут в памяти процесса: перезапуск воркера их теряет. Для одного
воркера (как сейчас на Render) этого достаточно; когда воркеров станет
больше, реестр переедет в Redis или в ту же таблицу trigger_jobs.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import requests

from app.scraping.scraper import ScanCancelled, scan_category

RUNNING = "running"
DONE = "done"
ERROR = "error"
CANCELLED = "cancelled"


@dataclass
class ScanJob:
    id: str
    category_key: str
    category_label: str
    months: int
    status: str = RUNNING
    stage: str = "Запуск…"
    log: list[str] = field(default_factory=list)
    found: int | None = None       # сколько статей-кандидатов собрано
    added: int | None = None       # сколько строк n8n записал в triggers
    error: str | None = None
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str | None = None
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category_label,
            "category_key": self.category_key,
            "months": self.months,
            "status": self.status,
            "stage": self.stage,
            "log": list(self.log),
            "found": self.found,
            "added": self.added,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "finished": self.status != RUNNING,
        }


class ScanRegistry:
    """Реестр задач сканирования в памяти процесса."""

    MAX_JOBS = 20

    def __init__(self) -> None:
        self._jobs: dict[str, ScanJob] = {}
        self._order: list[str] = []
        self._lock = threading.RLock()

    def create(self, category_key: str, category_label: str, months: int) -> ScanJob:
        job = ScanJob(
            id=str(uuid.uuid4()),
            category_key=category_key,
            category_label=category_label,
            months=months,
        )
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
            while len(self._order) > self.MAX_JOBS:
                self._jobs.pop(self._order.pop(0), None)
        return job

    def get(self, job_id: str) -> ScanJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def latest(self) -> ScanJob | None:
        with self._lock:
            return self._jobs.get(self._order[-1]) if self._order else None

    def running(self) -> ScanJob | None:
        with self._lock:
            for job_id in reversed(self._order):
                job = self._jobs[job_id]
                if job.status == RUNNING:
                    return job
        return None

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job is None or job.status != RUNNING:
            return False
        job._stop.set()
        return True


registry = ScanRegistry()


class ScanService:
    """Пайплайн: скрейпинг → n8n → опрос trigger_jobs."""

    def __init__(self, config: dict[str, Any], job_repo=None) -> None:
        self.webhook_url = config.get("N8N_TRIGGERS_SCAN_WEBHOOK_URL")
        self.webhook_timeout = int(config.get("N8N_WEBHOOK_TIMEOUT", 15))
        self.poll_timeout = int(config.get("SCAN_POLL_TIMEOUT", 300))
        self.poll_interval = int(config.get("SCAN_POLL_INTERVAL", 3))
        self.job_repo = job_repo

    # --- запуск -----------------------------------------------------------

    def start(self, category_key: str, category_label: str, months: int) -> ScanJob:
        job = registry.create(category_key, category_label, months)
        thread = threading.Thread(target=self._run, args=(job,), daemon=True)
        thread.start()
        return job

    # --- пайплайн ---------------------------------------------------------

    def _run(self, job: ScanJob) -> None:
        try:
            articles = self._scrape(job)
            if articles is None:
                return
            if not self._send(job, articles):
                return
            self._await_result(job)
        except ScanCancelled:
            self._finish(job, CANCELLED, "Остановлено")
        except Exception as err:  # noqa: BLE001 — фон, наверх пробрасывать некуда
            job.error = str(err)
            self._finish(job, ERROR, "Ошибка")

    def _scrape(self, job: ScanJob) -> list[dict] | None:
        job.stage = f"Сканирую источники · {job.category_label}, {job.months} мес."
        self._log(job, job.stage)
        try:
            articles = scan_category(
                job.category_key,
                months=job.months,
                progress_callback=lambda msg: self._log(job, msg),
                should_stop=job._stop.is_set,
            )
        except ScanCancelled:
            raise
        except Exception as err:  # noqa: BLE001
            job.error = f"Scraping failed: {err}"
            self._finish(job, ERROR, "Сканирование не удалось")
            return None

        job.found = len(articles)
        if not articles:
            job.added = 0
            self._log(
                job,
                f"Новых статей-кандидатов за последние {job.months} мес. не найдено "
                "(либо все уже есть в базе).",
            )
            self._finish(job, DONE, "Ничего нового не найдено")
            return None
        return articles

    def _send(self, job: ScanJob, articles: list[dict]) -> bool:
        if not self.webhook_url:
            job.error = (
                "Не задан N8N_TRIGGERS_SCAN_WEBHOOK_URL — статьи собраны, "
                "но отправлять их на классификацию некуда."
            )
            self._finish(job, ERROR, "Webhook не настроен")
            return False

        job.stage = f"Найдено {len(articles)} статей · отправляю в n8n"
        self._log(job, job.stage)
        try:
            response = requests.post(
                self.webhook_url,
                json={
                    "action": "scan_trigger",
                    "category": job.category_key,
                    "job_id": job.id,
                    "articles": articles,
                },
                timeout=self.webhook_timeout,
            )
            if response.status_code != 200:
                job.error = f"n8n вернул {response.status_code}: {response.text[:300]}"
                self._finish(job, ERROR, "n8n отклонил задачу")
                return False
        except requests.exceptions.Timeout:
            job.error = "Истекло время ожидания ответа n8n."
            self._finish(job, ERROR, "n8n не ответил")
            return False
        except requests.exceptions.RequestException as err:
            job.error = f"Не удалось достучаться до n8n: {err}"
            self._finish(job, ERROR, "n8n недоступен")
            return False
        return True

    def _await_result(self, job: ScanJob) -> None:
        if self.job_repo is None:
            self._log(job, "Задача принята n8n. Опрос trigger_jobs недоступен на этом бэкенде.")
            self._finish(job, DONE, "Задача передана в n8n")
            return

        job.stage = "n8n принял задачу · жду классификацию"
        self._log(job, job.stage)

        elapsed = 0
        while elapsed < self.poll_timeout:
            if job._stop.is_set():
                raise ScanCancelled
            try:
                row = self.job_repo.get(job.id)
            except Exception:  # noqa: BLE001 — строки может ещё не быть
                row = None

            if row and row.get("status") == DONE:
                job.added = row.get("inserted_count") or 0
                self._log(job, f"Классификация завершена: добавлено {job.added}.")
                self._finish(job, DONE, "Готово")
                return
            if row and row.get("status") == ERROR:
                job.error = row.get("error") or "unknown error"
                self._finish(job, ERROR, "Ошибка классификации")
                return

            time.sleep(self.poll_interval)
            elapsed += self.poll_interval

        job.error = "Истекло время ожидания завершения задачи n8n."
        self._finish(job, ERROR, "Таймаут ожидания n8n")

    # --- служебное --------------------------------------------------------

    @staticmethod
    def _log(job: ScanJob, message: str) -> None:
        stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        job.log.append(f"{stamp} · {message}")
        del job.log[:-200]  # держим только хвост

    @staticmethod
    def _finish(job: ScanJob, status: str, stage: str) -> None:
        job.status = status
        job.stage = stage
        job.finished_at = datetime.now(timezone.utc).isoformat()
