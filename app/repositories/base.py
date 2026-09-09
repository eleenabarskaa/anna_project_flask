"""Интерфейсы репозиториев.

Всё приложение (веб и API) ходит за данными только через эти протоколы.
Чтобы подключить реальную БД, достаточно написать вторую реализацию
(например `app/repositories/sql.py`) и зарегистрировать её в `app/repositories/__init__.py`
— ни шаблоны, ни сервисы, ни API трогать не придётся.
"""

from __future__ import annotations

from typing import Protocol

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


class TriggerRepository(Protocol):
    def list(
        self,
        *,
        category: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Trigger]: ...

    def count(self, *, category: str | None = None) -> int: ...

    def get(self, trigger_id: str) -> Trigger | None: ...

    def latest(self, limit: int = 5) -> list[Trigger]: ...


class ProspectRepository(Protocol):
    def list(self, *, query: str | None = None) -> list[Prospect]: ...

    def get(self, prospect_id: str) -> Prospect | None: ...

    def queue(self) -> list[Prospect]:
        """Приоритетная очередь, отсортированная по mandate fit."""
        ...

    def set_watched(self, prospect_id: str, watched: bool) -> Prospect | None: ...


class DossierRepository(Protocol):
    def get(self, prospect_id: str) -> Dossier | None: ...


class SourceRepository(Protocol):
    def list(self) -> list[Source]: ...

    def categories(self) -> list[TriggerCategory]: ...

    def set_category_enabled(self, key: str, enabled: bool) -> TriggerCategory | None: ...

    def logs(self) -> list[IngestLogEntry]: ...


class DeskRepository(Protocol):
    def tasks(self) -> list[DeskTask]: ...

    def toggle_task(self, task_id: int) -> DeskTask | None: ...

    def watchlist(self) -> list[WatchlistItem]: ...
