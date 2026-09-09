"""In-memory реализация репозиториев поверх seed-данных.

Состояние живёт в процессе: изменения (watchlist, задачи, категории)
сохраняются до перезапуска. Это временная заглушка — контракт совпадает
с `app/repositories/base.py`, поэтому замена на БД локальна.
"""

from __future__ import annotations

import copy
import threading

from app.models import (
    DeskTask,
    Dossier,
    IngestLogEntry,
    Prospect,
    Source,
    Trigger,
    TriggerCategory,
    WatchlistItem,
)
from app.repositories import seed_data


class _Store:
    """Единое изменяемое хранилище на процесс."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.reset()

    def reset(self) -> None:
        self.triggers: list[Trigger] = copy.deepcopy(seed_data.TRIGGERS)
        self.prospects: list[Prospect] = copy.deepcopy(seed_data.PROSPECTS)
        self.dossiers: list[Dossier] = copy.deepcopy(seed_data.DOSSIERS)
        self.sources: list[Source] = copy.deepcopy(seed_data.SOURCES)
        self.categories: list[TriggerCategory] = copy.deepcopy(seed_data.TRIGGER_CATEGORIES)
        self.logs: list[IngestLogEntry] = copy.deepcopy(seed_data.INGEST_LOG)
        self.tasks: list[DeskTask] = copy.deepcopy(seed_data.DESK_TASKS)
        self.watchlist: list[WatchlistItem] = copy.deepcopy(seed_data.WATCHLIST)


store = _Store()


class InMemoryTriggerRepository:
    def list(
        self,
        *,
        category: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Trigger]:
        rows = self._filtered(category)
        rows = rows[offset:]
        if limit is not None:
            rows = rows[:limit]
        return rows

    def count(self, *, category: str | None = None) -> int:
        return len(self._filtered(category))

    def get(self, trigger_id: str) -> Trigger | None:
        return next((t for t in store.triggers if t.id == trigger_id), None)

    def latest(self, limit: int = 5) -> list[Trigger]:
        return sorted(store.triggers, key=lambda t: t.date, reverse=True)[:limit]

    @staticmethod
    def _filtered(category: str | None) -> list[Trigger]:
        rows = sorted(store.triggers, key=lambda t: t.date, reverse=True)
        if category and category != "All categories":
            rows = [t for t in rows if t.type == category]
        return rows


class InMemoryProspectRepository:
    def list(self, *, query: str | None = None) -> list[Prospect]:
        rows = list(store.prospects)
        if query:
            q = query.strip().lower()
            rows = [
                p
                for p in rows
                if q in p.name.lower() or q in p.role.lower() or q in p.trigger.lower()
            ]
        return rows

    def get(self, prospect_id: str) -> Prospect | None:
        return next((p for p in store.prospects if p.id == prospect_id), None)

    def queue(self) -> list[Prospect]:
        return sorted(store.prospects, key=lambda p: p.fit, reverse=True)

    def set_watched(self, prospect_id: str, watched: bool) -> Prospect | None:
        with store.lock:
            prospect = self.get(prospect_id)
            if prospect is None:
                return None
            prospect.watched = watched
            return prospect


class InMemoryDossierRepository:
    def get(self, prospect_id: str) -> Dossier | None:
        return next((d for d in store.dossiers if d.prospect_id == prospect_id), None)


class InMemorySourceRepository:
    def list(self) -> list[Source]:
        return list(store.sources)

    def categories(self) -> list[TriggerCategory]:
        return list(store.categories)

    def set_category_enabled(self, key: str, enabled: bool) -> TriggerCategory | None:
        with store.lock:
            category = next((c for c in store.categories if c.key == key), None)
            if category is None:
                return None
            category.enabled = enabled
            return category

    def logs(self) -> list[IngestLogEntry]:
        return list(store.logs)


class InMemoryDeskRepository:
    def tasks(self) -> list[DeskTask]:
        return list(store.tasks)

    def toggle_task(self, task_id: int) -> DeskTask | None:
        with store.lock:
            task = next((t for t in store.tasks if t.id == task_id), None)
            if task is None:
                return None
            task.done = not task.done
            return task

    def watchlist(self) -> list[WatchlistItem]:
        return list(store.watchlist)
