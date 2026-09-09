"""Конфигурация приложения.

Все внешние подключения (БД, кэш, интеграции) читаются из переменных
окружения — когда пришлёте креды, достаточно заполнить .env.
"""

from __future__ import annotations

import os


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class BaseConfig:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    JSON_SORT_KEYS = False

    # Выбор реализации репозиториев: memory | (позже) sql
    REPOSITORY_BACKEND = os.getenv("REPOSITORY_BACKEND", "memory")

    # --- Заготовки под будущие подключения -------------------------------
    # Основная БД (Postgres/MySQL): postgresql+psycopg://user:pass@host:5432/db
    DATABASE_URL = os.getenv("DATABASE_URL")
    # Полнотекстовый поиск / витрина событий
    SEARCH_URL = os.getenv("SEARCH_URL")
    # Кэш и очередь ингеста
    REDIS_URL = os.getenv("REDIS_URL")
    # Внешние интеграции (новостные API, реестры, CRM)
    INTEGRATIONS_TIMEOUT = int(os.getenv("INTEGRATIONS_TIMEOUT", "15"))

    # --- Параметры домена -------------------------------------------------
    TRIGGERS_PER_PAGE = int(os.getenv("TRIGGERS_PER_PAGE", "8"))
    DEFAULT_LOOKBACK_MONTHS = int(os.getenv("DEFAULT_LOOKBACK_MONTHS", "3"))
    DESK_USER_NAME = os.getenv("DESK_USER_NAME", "Anna Kaufmann")
    DESK_USER_LOCATION = os.getenv("DESK_USER_LOCATION", "Zurich · Desk 4")


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    TEMPLATES_AUTO_RELOAD = True


class TestingConfig(BaseConfig):
    TESTING = True
    SECRET_KEY = "testing"


class ProductionConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", True)


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None):
    name = name or os.getenv("FLASK_ENV", "development")
    return CONFIGS.get(name, DevelopmentConfig)
