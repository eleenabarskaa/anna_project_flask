"""Репозиторий триггеров поверх Supabase (PostgREST).

Клиент написан на stdlib (urllib) — никаких дополнительных зависимостей,
одинаково работает локально и на Render.

Ожидаемая схема таблицы `triggers`:
    id uuid, event_date date, company_or_person text, trigger_type text,
    context text, bidder text, seller text, source text (url),
    created_at timestamptz, updated_at timestamptz, founded text

Полей est / confidence / individuals в таблице нет — они остаются None,
и шаблоны показывают в этих местах «—».
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime

from app.models import Trigger

# «Acme SpA (bidder: Foo) (seller: Bar)» → отрезаем служебные скобки в конце
_ROLE_SUFFIX = re.compile(r"\s*\((?:bidder|seller|buyer|acquirer)\s*:.*$", re.IGNORECASE)
# Конец первого предложения: точка/!/? + пробел + заглавная буква
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-ÞÈÉ0-9«\"])")

HEADLINE_MAX = 160


class PostgrestError(RuntimeError):
    """Ошибка обращения к Supabase — пробрасывается наверх с телом ответа."""


class PostgrestClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 15) -> None:
        if not base_url or not api_key:
            raise ValueError("Нужны SUPABASE_URL и SUPABASE_SECRET_KEY")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def select(
        self,
        table: str,
        *,
        params: dict[str, str] | None = None,
        offset: int | None = None,
        limit: int | None = None,
        with_count: bool = False,
    ) -> tuple[list[dict], int | None]:
        """GET /rest/v1/<table>. Возвращает (строки, total | None)."""
        query = urllib.parse.urlencode(params or {}, safe="*.,()")
        url = f"{self.base_url}/rest/v1/{table}"
        if query:
            url = f"{url}?{query}"

        headers = {
            "apikey": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }
        if with_count:
            headers["Prefer"] = "count=exact"
        if offset is not None and limit is not None:
            headers["Range-Unit"] = "items"
            headers["Range"] = f"{offset}-{offset + limit - 1}"

        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8") or "[]")
                total = _parse_total(response.headers.get("Content-Range"))
        except urllib.error.HTTPError as err:  # 4xx/5xx от PostgREST
            body = err.read().decode("utf-8", "replace")[:500]
            raise PostgrestError(f"Supabase {err.code}: {body}") from err
        except urllib.error.URLError as err:  # сеть/DNS/таймаут
            raise PostgrestError(f"Supabase недоступен: {err.reason}") from err

        return payload, total


def _parse_total(content_range: str | None) -> int | None:
    """'0-7/292' → 292; '*/0' → 0; None → None."""
    if not content_range or "/" not in content_range:
        return None
    tail = content_range.rsplit("/", 1)[1]
    return int(tail) if tail.isdigit() else None


# --- маппинг строки таблицы в доменную модель ---------------------------

def _company(raw: str | None) -> str:
    return _ROLE_SUFFIX.sub("", (raw or "—").strip()).strip() or "—"


def _headline(context: str | None) -> str:
    """Первое предложение контекста, обрезанное до разумной длины."""
    text = (context or "").strip()
    if not text:
        return "Без описания"
    first = _SENTENCE_END.split(text, maxsplit=1)[0].strip()
    if len(first) <= HEADLINE_MAX:
        return first
    return first[:HEADLINE_MAX].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _parties(bidder: str | None, seller: str | None) -> str:
    parts = []
    if bidder:
        parts.append(f"Buyer: {bidder}")
    if seller:
        parts.append(f"Seller: {seller}")
    return " · ".join(parts) if parts else "—"


def _source_name(url: str | None) -> str:
    if not url:
        return "—"
    host = urllib.parse.urlparse(url).netloc
    return host[4:] if host.startswith("www.") else (host or "—")


def _event_date(raw: str | None) -> date:
    try:
        return date.fromisoformat((raw or "")[:10])
    except ValueError:
        return date.min


def _ingested_at(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = raw.replace("Z", "+00:00").replace(" ", "T", 1)
    try:
        return datetime.fromisoformat(cleaned).strftime("%d %b %H:%M")
    except ValueError:
        return raw[:16]


def row_to_trigger(row: dict) -> Trigger:
    return Trigger(
        id=str(row.get("id", "")),
        date=_event_date(row.get("event_date")),
        company=_company(row.get("company_or_person")),
        headline=_headline(row.get("context")),
        type=(row.get("trigger_type") or "—").strip(),
        source=_source_name(row.get("source")),
        principal=row.get("seller") or row.get("bidder"),
        est=None,               # в таблице пока нет
        confidence=None,        # в таблице пока нет
        confidence_pct=None,
        parties=_parties(row.get("bidder"), row.get("seller")),
        context=(row.get("context") or "").strip(),
        url=row.get("source") or "",
        ingested_at=_ingested_at(row.get("created_at")),
        reviewer="auto (LLM)" if row.get("founded") == "llm" else (row.get("founded") or None),
        people=[],              # физлиц в таблице пока нет
    )


# --- репозиторий ---------------------------------------------------------

class SupabaseTriggerRepository:
    """Реализация TriggerRepository из app/repositories/base.py."""

    def __init__(self, client: PostgrestClient, table: str = "triggers") -> None:
        self.client = client
        self.table = table

    def list(
        self,
        *,
        category: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Trigger]:
        rows, _ = self._query(category=category, limit=limit, offset=offset, with_count=False)
        return [row_to_trigger(r) for r in rows]

    def count(self, *, category: str | None = None) -> int:
        _, total = self._query(category=category, limit=1, offset=0, with_count=True)
        return total or 0

    def get(self, trigger_id: str) -> Trigger | None:
        rows, _ = self.client.select(
            self.table,
            params={"select": "*", "id": f"eq.{trigger_id}", "limit": "1"},
        )
        return row_to_trigger(rows[0]) if rows else None

    def latest(self, limit: int = 5) -> list[Trigger]:
        return self.list(limit=limit, offset=0)

    def distinct_types(self) -> list[str]:
        """Список значений trigger_type — для выпадающего фильтра."""
        rows, _ = self.client.select(
            self.table,
            params={"select": "trigger_type", "order": "trigger_type.asc"},
        )
        seen = {(r.get("trigger_type") or "").strip() for r in rows}
        return sorted(t for t in seen if t)

    def _query(self, *, category: str | None, limit: int | None, offset: int, with_count: bool):
        params = {"select": "*", "order": "event_date.desc,created_at.desc"}
        if category and category != "All categories":
            params["trigger_type"] = f"eq.{category}"
        return self.client.select(
            self.table,
            params=params,
            offset=offset if limit is not None else None,
            limit=limit,
            with_count=with_count,
        )
