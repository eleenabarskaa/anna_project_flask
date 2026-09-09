"""Точка сборки репозиториев.

Здесь выбирается конкретная реализация. Сейчас — in-memory; когда придут
доступы к БД, добавляем ветку по `REPOSITORY_BACKEND` из конфига.
"""

from __future__ import annotations

from typing import Any

from app.repositories.memory import (
    InMemoryDeskRepository,
    InMemoryDossierRepository,
    InMemoryProspectRepository,
    InMemorySourceRepository,
    InMemoryTriggerRepository,
)


class Repositories:
    """Контейнер репозиториев, доступный как `current_app.repos`."""

    def __init__(self, backend: str = "memory", settings: dict[str, Any] | None = None) -> None:
        self.backend = backend
        self.settings = settings or {}

        if backend == "memory":
            self.triggers = InMemoryTriggerRepository()
            self.prospects = InMemoryProspectRepository()
            self.dossiers = InMemoryDossierRepository()
            self.sources = InMemorySourceRepository()
            self.desk = InMemoryDeskRepository()
        else:  # pragma: no cover - появится вместе с реальной БД
            raise ValueError(
                f"Неизвестный REPOSITORY_BACKEND={backend!r}. "
                "Доступно: 'memory'. Реализацию для БД добавим при подключении."
            )


def build_repositories(config: dict[str, Any]) -> Repositories:
    return Repositories(backend=config.get("REPOSITORY_BACKEND", "memory"), settings=config)
