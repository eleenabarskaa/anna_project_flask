"""Сервисный слой: сборка вью-моделей для страниц и API."""

from __future__ import annotations

from typing import Any

from app.models import Prospect
from app.repositories import Repositories, seed_data

DATA_SOURCE_ERROR = (
    "Не удалось получить события из источника данных. "
    "Показаны пустые списки — проверьте SUPABASE_URL / SUPABASE_SECRET_KEY."
)


class DeskService:
    def __init__(self, repos: Repositories) -> None:
        self.repos = repos

    @staticmethod
    def _safe(call, fallback):
        """Ошибка внешнего источника не должна ронять всю страницу."""
        from app.repositories.supabase import PostgrestError

        try:
            return call(), None
        except PostgrestError as err:
            return fallback, f"{DATA_SOURCE_ERROR} ({err})"

    # --- Desk / overview -------------------------------------------------

    def kpis(self) -> list[dict[str, Any]]:
        return [k.to_dict() for k in seed_data.KPIS]

    def overview(self) -> dict[str, Any]:
        latest, error = self._safe(lambda: self.repos.triggers.latest(5), [])
        return {
            "kpis": self.kpis(),
            "latest_triggers": latest,
            "data_error": error,
            "watchlist": self.repos.desk.watchlist(),
            "tasks": self.repos.desk.tasks(),
            "queue": self.repos.prospects.queue(),
            "composition": seed_data.QUEUE_COMPOSITION,
            "suggestions": seed_data.SEARCH_SUGGESTIONS,
            "recent_briefs": seed_data.RECENT_BRIEFS,
            "total_triggers": seed_data.TOTAL_TRIGGERS,
            "coverage_days": seed_data.COVERAGE_DAYS,
        }

    # --- Prospect brief (researched_documents) ---------------------------

    def documents_page(self, *, query: str | None, page: int, per_page: int) -> dict[str, Any]:
        """Список готовых брифов из researched_documents."""
        offset = (page - 1) * per_page

        def fetch():
            return self.repos.documents.list(
                query=query, limit=per_page, offset=offset, with_count=True
            )

        (rows, total), error = self._safe(fetch, ([], 0))
        total = total or 0
        pages = max(1, -(-total // per_page))
        return {
            "documents": rows,
            "total": total,
            "page": min(page, pages),
            "pages": pages,
            "per_page": per_page,
            "data_error": error,
        }

    def document(self, document_id: str):
        """Один бриф; markdown рендерится в HTML с оглавлением."""
        from app.services.markdown_render import render_brief

        doc, error = self._safe(lambda: self.repos.documents.get(document_id), None)
        if error:
            return {"document": None, "brief": None, "data_error": error}
        if doc is None:
            return None
        return {"document": doc, "brief": render_brief(doc.full_markdown), "data_error": None}

    def search_prospects(self, query: str | None) -> list[Prospect]:
        return self.repos.prospects.list(query=query)

    def dossier_for(self, prospect_id: str) -> dict[str, Any] | None:
        """Возвращает досье; если оно не обогащено — заглушку по образцу макета."""
        prospect = self.repos.prospects.get(prospect_id)
        if prospect is None:
            return None

        dossier = self.repos.dossiers.get(prospect_id)
        if dossier is not None:
            return {"prospect": prospect, "dossier": dossier, "enriched": True}

        return {"prospect": prospect, "dossier": self._empty_dossier(prospect), "enriched": False}

    @staticmethod
    def _empty_dossier(prospect: Prospect):
        from app.models import Angle, Dossier, Fact, Relation, Stat, TimelineEvent

        return Dossier(
            prospect_id=prospect.id,
            name=prospect.name,
            role=prospect.role,
            tags=["Draft brief"],
            stats=[
                Stat(label="Est. proceeds", value="—", note="Awaiting enrichment"),
                Stat(label="Confidence", value="—", note="—"),
                Stat(label="Mandate fit", value="—", note="—"),
            ],
            summary=(
                "This brief has not been enriched yet. Run the ingest for this prospect to "
                "pull filings, press coverage and register entries into a structured dossier. "
                "Only the fields with a named source are shown to the desk."
            ),
            facts=[Fact(label="Status", value="No verified facts on file yet", source="—")],
            timeline=[
                TimelineEvent(
                    date="—",
                    title="No events recorded",
                    detail="Events appear here once a trigger is matched to this prospect.",
                    tone="blue",
                )
            ],
            angles=[Angle(n="01", text="Enrich the brief before the first outreach.")],
            relations=[Relation(name="—", tie="No relationships mapped", strength="—")],
            enriched=False,
        )

    # --- Triggers --------------------------------------------------------

    def triggers_page(self, *, category: str | None, page: int, per_page: int) -> dict[str, Any]:
        offset = (page - 1) * per_page

        def fetch():
            rows = self.repos.triggers.list(category=category, limit=per_page, offset=offset)
            total = self.repos.triggers.count(category=category)
            types = self.repos.triggers.distinct_types()
            return rows, total, types

        (rows, total, types), error = self._safe(fetch, ([], 0, []))
        pages = max(1, -(-total // per_page))
        return {
            "rows": rows,
            "total": total,
            "page": min(page, pages),
            "pages": pages,
            "per_page": per_page,
            "categories": [*types, "All categories"],
            "data_error": error,
        }

    # --- Sources ---------------------------------------------------------

    def sources_page(self) -> dict[str, Any]:
        return {
            "categories": self.repos.sources.categories(),
            "sources": self.repos.sources.list(),
            "logs": self.repos.sources.logs(),
        }
