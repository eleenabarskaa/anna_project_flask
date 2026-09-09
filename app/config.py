"""Конфигурация приложения.

Все внешние подключения (Supabase, БД, кэш) читаются из переменных окружения.
Значения вычисляются в момент вызова `build_config()`, а не при импорте модуля —
иначе переменные, выставленные после импорта (тесты, скрипты, ноутбуки),
молча игнорировались бы.
"""

from __future__ import annotations

import os
from typing import Any


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def build_config(name: str | None = None) -> dict[str, Any]:
    env = name or os.getenv("FLASK_ENV", "development")

    config: dict[str, Any] = {
        "ENV_NAME": env,
        "SECRET_KEY": os.getenv("SECRET_KEY", "dev-secret-change-me"),
        "JSON_SORT_KEYS": False,

        # Источник данных: memory | supabase
        "REPOSITORY_BACKEND": os.getenv("REPOSITORY_BACKEND", "memory"),

        # --- Supabase ---------------------------------------------------
        # SUPABASE_SECRET_KEY — service-role ключ, обходит RLS.
        # Только в .env и в переменных окружения хостинга, никогда в репозитории.
        "SUPABASE_URL": os.getenv("SUPABASE_URL"),
        "SUPABASE_SECRET_KEY": os.getenv("SUPABASE_SECRET_KEY"),
        "SUPABASE_TRIGGERS_TABLE": os.getenv("SUPABASE_TRIGGERS_TABLE", "triggers"),

        # --- заготовки под будущие подключения --------------------------
        "DATABASE_URL": os.getenv("DATABASE_URL"),
        "REDIS_URL": os.getenv("REDIS_URL"),
        "INTEGRATIONS_TIMEOUT": _int("INTEGRATIONS_TIMEOUT", 15),

        # --- параметры домена -------------------------------------------
        "TRIGGERS_PER_PAGE": _int("TRIGGERS_PER_PAGE", 8),
        "DEFAULT_LOOKBACK_MONTHS": _int("DEFAULT_LOOKBACK_MONTHS", 3),
        "DESK_USER_NAME": os.getenv("DESK_USER_NAME", "Anna Kaufmann"),
        "DESK_USER_LOCATION": os.getenv("DESK_USER_LOCATION", "Zurich · Desk 4"),
    }

    if env == "development":
        config.update(DEBUG=True, TEMPLATES_AUTO_RELOAD=True)
    elif env == "testing":
        config.update(TESTING=True, SECRET_KEY="testing")
    else:  # production
        config.update(DEBUG=False, SESSION_COOKIE_SECURE=_bool("SESSION_COOKIE_SECURE", True))

    return config
