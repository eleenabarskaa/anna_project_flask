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
from datetime import date, datetime, timedelta, timezone

from app.models import ResearchDocument, Trigger

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

    def patch(self, table: str, *, params: dict[str, str], data: dict) -> list[dict]:
        """PATCH /rest/v1/<table>?<фильтр> — точечное обновление строк."""
        query = urllib.parse.urlencode(params, safe="*.,()")
        url = f"{self.base_url}/rest/v1/{table}?{query}"
        body = json.dumps(data).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=body,
            method="PATCH",
            headers={
                "apikey": self.api_key,
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Prefer": "return=representation",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8") or "[]")
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", "replace")[:500]
            raise PostgrestError(f"Supabase {err.code}: {detail}") from err
        except urllib.error.URLError as err:
            raise PostgrestError(f"Supabase недоступен: {err.reason}") from err


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

    def count_since(self, hours: int = 24) -> int:
        """Сколько триггеров добавлено за последние N часов (по created_at)."""
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        _, total = self.client.select(
            self.table,
            params={"select": "id", "created_at": f"gte.{since}"},
            offset=0,
            limit=1,
            with_count=True,
        )
        return total or 0

    def latest_added(self, limit: int = 5) -> list[Trigger]:
        """Последние добавленные (по created_at), а не по дате события."""
        rows, _ = self.client.select(
            self.table,
            params={"select": "*", "order": "created_at.desc"},
            offset=0,
            limit=limit,
        )
        return [row_to_trigger(r) for r in rows]

    def refresh_hint(self) -> None:
        """PostgREST не кэширует — метод оставлен для симметрии с memory-версией."""

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


class SupabaseJobRepository:
    """Чтение таблицы `trigger_jobs`, которую наполняет workflow в n8n.

    Строка задачи: {id, status: running|done|error, inserted_count, error}.
    """

    def __init__(self, client: PostgrestClient, table: str = "trigger_jobs") -> None:
        self.client = client
        self.table = table

    def get(self, job_id: str) -> dict | None:
        rows, _ = self.client.select(
            self.table,
            params={
                "select": "status,inserted_count,error",
                "id": f"eq.{job_id}",
                "limit": "1",
            },
        )
        return rows[0] if rows else None


# --- researched_documents ------------------------------------------------

def _researched_at(raw: str | None) -> str | None:
    """'2026-08-16 15:41:43.6+00' → '16 Aug 2026'."""
    if not raw:
        return None
    cleaned = raw.replace("Z", "+00:00").replace(" ", "T", 1)
    try:
        return datetime.fromisoformat(cleaned).strftime("%d %b %Y")
    except ValueError:
        return raw[:10]


def row_to_document(row: dict) -> ResearchDocument:
    return ResearchDocument(
        id=str(row.get("id", "")),
        name=(row.get("name") or "—").strip(),
        normalized_name=(row.get("normalized_name") or "").strip(),
        document_type=(row.get("document_type") or "").strip(),
        status=(row.get("status") or "").strip(),
        source_query=(row.get("source_query") or "").strip(),
        researched_at=_researched_at(row.get("researched_at")),
        full_markdown=row.get("full_markdown") or "",
        watched=bool(row.get("watched")),
    )


class SupabaseDocumentRepository:
    """Таблица `researched_documents` — готовые брифы в markdown.

    В списке колонка full_markdown не запрашивается: она весит десятки
    килобайт на строку и в перечне не нужна.
    """

    LIST_COLUMNS = (
        "id,name,normalized_name,document_type,status,source_query,researched_at,watched"
    )

    def __init__(self, client: PostgrestClient, table: str = "researched_documents") -> None:
        self.client = client
        self.table = table

    def list(
        self,
        *,
        query: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        with_count: bool = False,
    ) -> tuple[list[ResearchDocument], int | None]:
        params = {
            "select": self.LIST_COLUMNS,
            "order": "researched_at.desc.nullslast",
        }
        term = (query or "").strip()
        if term:
            # ilike по имени, нормализованному имени и исходному запросу
            pattern = f"*{term}*"
            params["or"] = f"(name.ilike.{pattern},normalized_name.ilike.{pattern},source_query.ilike.{pattern})"

        rows, total = self.client.select(
            self.table,
            params=params,
            offset=offset if limit is not None else None,
            limit=limit,
            with_count=with_count,
        )
        return [row_to_document(r) for r in rows], total

    def get(self, document_id: str) -> ResearchDocument | None:
        rows, _ = self.client.select(
            self.table,
            params={"select": "*", "id": f"eq.{document_id}", "limit": "1"},
        )
        return row_to_document(rows[0]) if rows else None

    def statuses(self) -> list[str]:
        rows, _ = self.client.select(self.table, params={"select": "status"})
        return sorted({(r.get("status") or "").strip() for r in rows} - {""})

    def set_watched(self, document_id: str, watched: bool) -> ResearchDocument | None:
        rows = self.client.patch(
            self.table,
            params={"id": f"eq.{document_id}", "select": self.LIST_COLUMNS},
            data={"watched": watched},
        )
        return row_to_document(rows[0]) if rows else None

    def watchlist(self, limit: int = 10) -> list[ResearchDocument]:
        rows, _ = self.client.select(
            self.table,
            params={
                "select": self.LIST_COLUMNS,
                "watched": "is.true",
                "order": "researched_at.desc.nullslast",
            },
            offset=0,
            limit=limit,
        )
        return [row_to_document(r) for r in rows]

    def count_watched(self) -> int:
        _, total = self.client.select(
            self.table,
            params={"select": "id", "watched": "is.true"},
            offset=0,
            limit=1,
            with_count=True,
        )
        return total or 0

    def count_since(self, days: int = 7) -> int:
        """Сколько брифов создано за последние N дней (по researched_at)."""
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        _, total = self.client.select(
            self.table,
            params={"select": "id", "researched_at": f"gte.{since}"},
            offset=0,
            limit=1,
            with_count=True,
        )
        return total or 0

    def count_all(self) -> int:
        _, total = self.client.select(
            self.table, params={"select": "id"}, offset=0, limit=1, with_count=True
        )
        return total or 0



class SupabaseChatJobRepository:
    """Таблица `chat_jobs` — результат работы агента в n8n.

    Строка: {id, status: running|done|error, reply}. Та же схема, что
    использовалась в Streamlit-версии.
    """

    def __init__(self, client: PostgrestClient, table: str = "chat_jobs") -> None:
        self.client = client
        self.table = table

    def get(self, job_id: str) -> dict | None:
        rows, _ = self.client.select(
            self.table,
            params={"select": "status,reply", "id": f"eq.{job_id}", "limit": "1"},
        )
        return rows[0] if rows else None
