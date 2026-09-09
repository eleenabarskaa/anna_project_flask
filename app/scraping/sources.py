"""Конфигурация источников для сканирования триггеров.

Порт `trigger_sources.py` из Streamlit-версии.

- CATEGORIES: пары (подпись в интерфейсе, внутренний ключ категории).
  Внутренний ключ обязан совпадать с ключом в domains_by_category.json.
- DOMAINS_BY_CATEGORY: читается один раз из domains_by_category.json рядом
  с этим файлом. На категорию: {"domains": [...], "known_urls": [...]}.
  domains — белый список хостов, которые разрешено обходить;
  known_urls — статьи, уже заведённые в базу, чтобы не находить их снова.

Чтобы добавить или убрать источник, правьте только domains_by_category.json.
"""

from __future__ import annotations

import json
from pathlib import Path

_CONFIG_PATH = Path(__file__).with_name("domains_by_category.json")

with _CONFIG_PATH.open(encoding="utf-8") as _f:
    DOMAINS_BY_CATEGORY: dict[str, dict] = json.load(_f)

# (подпись в UI, внутренний ключ)
CATEGORIES: list[tuple[str, str]] = [
    ("M&A / Liquidity Event", "M&A / Liquidity event"),
    ("IPO / Listing", "IPO / Listing"),
    ("PE Exit", "PE Exit"),
    ("Succession / Leadership Transition", "Succession / Leadership transition"),
    ("Real Estate", "Real Estate"),
    ("Family Office", "Family Office"),
]

# В Streamlit-версии ключ IPO был записан как "IPO / Листинг", а в
# domains_by_category.json — как "IPO / Listing". Из-за этого сканирование
# IPO молча не находило ни одного источника. Ключи выровнены, а старое
# написание оставлено алиасом, чтобы не сломать сохранённые ссылки.
CATEGORY_ALIASES = {"IPO / Листинг": "IPO / Listing"}

LABEL_TO_KEY = {label: key for label, key in CATEGORIES}
KEY_TO_LABEL = {key: label for label, key in CATEGORIES}


def normalize_key(category_key: str) -> str:
    return CATEGORY_ALIASES.get(category_key, category_key)


def get_scope(category_key: str) -> tuple[list[str], list[str]]:
    """(domains, known_urls) для внутреннего ключа категории."""
    entry = DOMAINS_BY_CATEGORY.get(normalize_key(category_key), {})
    return entry.get("domains", []), entry.get("known_urls", [])


def is_known_category(category_key: str) -> bool:
    return normalize_key(category_key) in KEY_TO_LABEL
