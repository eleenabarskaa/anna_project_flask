"""Точка сборки репозиториев.

Здесь выбирается конкретная реализация по `REPOSITORY_BACKEND`:

  memory    — всё на демо-данных из seed_data.py (по умолчанию)
  supabase  — триггеры читаются из реальной таблицы Supabase,
              остальные экраны пока остаются на демо-данных
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

BACKENDS = ("memory", "supabase")


class Repositories:
    """Контейнер репозиториев, доступный как `current_app.repos`."""

    def __init__(self, backend: str = "memory", settings: dict[str, Any] | None = None) -> None:
        if backend not in BACKENDS:
            raise ValueError(
                f"Неизвестный REPOSITORY_BACKEND={backend!r}. Доступно: {', '.join(BACKENDS)}."
            )

        self.backend = backend
        self.settings = settings or {}

        # Пока из Supabase приходят только триггеры — всё остальное на заглушках.
        self.prospects = InMemoryProspectRepository()
        self.dossiers = InMemoryDossierRepository()
        self.sources = InMemorySourceRepository()
        self.desk = InMemoryDeskRepository()

        if backend == "supabase":
            from app.repositories.supabase import (
                PostgrestClient,
                SupabaseJobRepository,
                SupabaseTriggerRepository,
            )

            client = PostgrestClient(
                base_url=self.settings.get("SUPABASE_URL") or "",
                api_key=self.settings.get("SUPABASE_SECRET_KEY") or "",
                timeout=int(self.settings.get("INTEGRATIONS_TIMEOUT", 15)),
            )
            self.triggers = SupabaseTriggerRepository(
                client, table=self.settings.get("SUPABASE_TRIGGERS_TABLE", "triggers")
            )
            # Таблица trigger_jobs — статус фоновой задачи классификации в n8n
            self.jobs = SupabaseJobRepository(
                client, table=self.settings.get("SUPABASE_TRIGGER_JOBS_TABLE", "trigger_jobs")
            )
        else:
            self.triggers = InMemoryTriggerRepository()
            self.jobs = None


def build_repositories(config: dict[str, Any]) -> Repositories:
    return Repositories(backend=config.get("REPOSITORY_BACKEND", "memory"), settings=config)
