"""Кнопка «Build brief» на вкладке Command.

Порт логики из Streamlit-версии (`render_plain_chat` + `poll_for_job_result`).
Контракт с n8n не менялся:

    POST PROSPECT_BRIEF_NEW_RUN_WEBHOOK_URL
        {"message": "<запрос>", "mode": "new_run", "session_id": "<uuid>"}
    ← {"job_id": "..."}            (вебхук отвечает сразу)

    затем опрос таблицы chat_jobs по job_id, пока не появится
    status = done (reply) или status = error.

Если вебхук ответил текстом без job_id — как и в Streamlit, считаем это
синхронным ответом и показываем его.

Пайплайн живёт минутами (у свежего проспекта — 5-7), поэтому работает в
фоновом потоке, а страница опрашивает GET /api/v1/brief/<job_id>.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import requests

RUNNING = "running"
DONE = "done"
ERROR = "error"
CANCELLED = "cancelled"

MODE = "new_run"


@dataclass
class BriefJob:
    id: str
    query: str
    session_id: str
    status: str = RUNNING
    stage: str = "Отправляю запрос агенту…"
    log: list[str] = field(default_factory=list)
    reply: str | None = None
    error: str | None = None
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str | None = None
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "query": self.query,
            "session_id": self.session_id,
            "status": self.status,
            "stage": self.stage,
            "log": list(self.log),
            "reply": self.reply,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "finished": self.status != RUNNING,
        }


class BriefRegistry:
    MAX_JOBS = 20

    def __init__(self) -> None:
        self._jobs: dict[str, BriefJob] = {}
        self._order: list[str] = []
        self._lock = threading.RLock()

    def create(self, query: str, session_id: str) -> BriefJob:
        job = BriefJob(id=str(uuid.uuid4()), query=query, session_id=session_id)
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
            while len(self._order) > self.MAX_JOBS:
                self._jobs.pop(self._order.pop(0), None)
        return job

    def get(self, job_id: str) -> BriefJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def running(self) -> BriefJob | None:
        with self._lock:
            for job_id in reversed(self._order):
                if self._jobs[job_id].status == RUNNING:
                    return self._jobs[job_id]
        return None

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job is None or job.status != RUNNING:
            return False
        job._stop.set()
        return True


registry = BriefRegistry()


class BriefService:
    def __init__(self, config: dict[str, Any], chat_jobs=None) -> None:
        self.webhook_url = config.get("PROSPECT_BRIEF_NEW_RUN_WEBHOOK_URL")
        self.webhook_timeout = int(config.get("N8N_WEBHOOK_TIMEOUT", 15))
        self.poll_timeout = int(config.get("BRIEF_POLL_TIMEOUT", 540))
        self.poll_interval = int(config.get("BRIEF_POLL_INTERVAL", 3))
        self.chat_jobs = chat_jobs

    def start(self, query: str, session_id: str | None = None) -> BriefJob:
        job = registry.create(query.strip(), session_id or str(uuid.uuid4()))
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return job

    # --- пайплайн ---------------------------------------------------------

    def _run(self, job: BriefJob) -> None:
        try:
            job_id = self._call_webhook(job)
            if job_id is _FAILED:
                return
            if job_id is None:          # синхронный ответ уже записан в job.reply
                return
            self._await_reply(job, job_id)
        except Exception as err:  # noqa: BLE001 — фон, наверх пробрасывать некуда
            job.error = str(err)
            self._finish(job, ERROR, "Ошибка")

    def _call_webhook(self, job: BriefJob):
        if not self.webhook_url:
            job.error = (
                "Не задан PROSPECT_BRIEF_NEW_RUN_WEBHOOK_URL — "
                "запрос отправлять некуда."
            )
            self._finish(job, ERROR, "Webhook не настроен")
            return _FAILED

        self._log(job, f"Запрос агенту: «{job.query}»")
        try:
            response = requests.post(
                self.webhook_url,
                json={"message": job.query, "mode": MODE, "session_id": job.session_id},
                timeout=self.webhook_timeout,
            )
        except requests.exceptions.Timeout:
            job.error = "Истекло время ожидания ответа n8n."
            self._finish(job, ERROR, "n8n не ответил")
            return _FAILED
        except requests.exceptions.RequestException as err:
            job.error = f"Не удалось достучаться до n8n: {err}"
            self._finish(job, ERROR, "n8n недоступен")
            return _FAILED

        if response.status_code != 200:
            job.error = (
                f"n8n вернул {response.status_code}: {response.text[:300]}. "
                "Проверьте, что workflow активен."
            )
            self._finish(job, ERROR, "n8n отклонил запрос")
            return _FAILED

        try:
            payload = response.json()
        except ValueError:
            payload = None

        remote_job_id = payload.get("job_id") if isinstance(payload, dict) else None
        if not remote_job_id:
            # Вебхук ответил синхронно текстом — поведение как в Streamlit.
            job.reply = response.text
            self._log(job, "Агент ответил сразу, без фоновой задачи.")
            self._finish(job, DONE, "Готово")
            return None

        self._log(job, f"Задача принята: {remote_job_id}")
        return remote_job_id

    def _await_reply(self, job: BriefJob, remote_job_id: str) -> None:
        if self.chat_jobs is None:
            job.error = (
                "Опрос таблицы chat_jobs недоступен на этом бэкенде — "
                "включите REPOSITORY_BACKEND=supabase."
            )
            self._finish(job, ERROR, "Нет доступа к chat_jobs")
            return

        job.stage = "Агент исследует — это занимает несколько минут"
        self._log(job, job.stage)

        elapsed = 0
        while elapsed < self.poll_timeout:
            if job._stop.is_set():
                self._finish(job, CANCELLED, "Остановлено")
                return
            try:
                row = self.chat_jobs.get(remote_job_id)
            except Exception:  # noqa: BLE001 — строки может ещё не быть
                row = None

            if row and row.get("status") == DONE:
                job.reply = row.get("reply") or ""
                self._log(job, "Ответ получен.")
                self._finish(job, DONE, "Готово")
                return
            if row and row.get("status") == ERROR:
                job.error = row.get("reply") or "unknown error"
                self._finish(job, ERROR, "Агент вернул ошибку")
                return

            time.sleep(self.poll_interval)
            elapsed += self.poll_interval

        minutes = self.poll_timeout // 60
        job.error = (
            f"Агент не ответил за {minutes} мин — возможно, workflow завис. "
            "Проверьте лог выполнения в n8n."
        )
        self._finish(job, ERROR, "Таймаут ожидания")

    # --- служебное --------------------------------------------------------

    @staticmethod
    def _log(job: BriefJob, message: str) -> None:
        stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        job.log.append(f"{stamp} · {message}")
        del job.log[:-100]

    @staticmethod
    def _finish(job: BriefJob, status: str, stage: str) -> None:
        job.status = status
        job.stage = stage
        job.finished_at = datetime.now(timezone.utc).isoformat()


_FAILED = object()  # маркер «шаг уже завершил задачу с ошибкой»
