"""JSON API (/api/v1).

Тот же сервисный слой, что и у страниц — чтобы фронтенд, скрипты ингеста
и внешние интеграции работали с одними и теми же данными.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app.repositories import seed_data
from app.services.desk import DeskService

bp = Blueprint("api", __name__)


def service() -> DeskService:
    return DeskService(current_app.repos)  # type: ignore[attr-defined]


def _trigger_dict(trigger) -> dict:  # noqa: ANN001
    data = trigger.to_dict()
    data["heat"] = trigger.heat
    return data


@bp.get("/health")
def health():
    return jsonify(status="ok", backend=current_app.repos.backend)  # type: ignore[attr-defined]


# --- Triggers ------------------------------------------------------------

@bp.get("/triggers")
def list_triggers():
    category = request.args.get("category")
    page = max(1, request.args.get("page", 1, type=int))
    per_page = request.args.get("per_page", current_app.config["TRIGGERS_PER_PAGE"], type=int)

    data = service().triggers_page(category=category, page=page, per_page=per_page)
    return jsonify(
        items=[_trigger_dict(t) for t in data["rows"]],
        meta={
            "total": data["total"],
            "page": data["page"],
            "pages": data["pages"],
            "per_page": data["per_page"],
            "category": category or "All categories",
        },
    )


@bp.get("/triggers/<trigger_id>")
def get_trigger(trigger_id: str):
    trigger = current_app.repos.triggers.get(trigger_id)  # type: ignore[attr-defined]
    if trigger is None:
        return jsonify(error="not_found", message=f"trigger {trigger_id}"), 404
    return jsonify(_trigger_dict(trigger))


# --- Prospect briefs (researched_documents) ------------------------------

@bp.get("/prospects")
def list_documents():
    """Список брифов. full_markdown в перечне не отдаётся — он объёмный."""
    query = request.args.get("q")
    page = max(1, request.args.get("page", 1, type=int))
    per_page = request.args.get("per_page", current_app.config["DOCUMENTS_PER_PAGE"], type=int)

    data = service().documents_page(query=query, page=page, per_page=per_page)
    return jsonify(
        items=[
            {k: v for k, v in d.to_dict().items() if k != "full_markdown"}
            for d in data["documents"]
        ],
        meta={
            "total": data["total"],
            "page": data["page"],
            "pages": data["pages"],
            "per_page": data["per_page"],
            "q": query,
        },
    )


@bp.get("/prospects/<document_id>")
def get_document(document_id: str):
    """Один бриф целиком: исходный markdown + отрендеренный HTML."""
    payload = service().document(document_id)
    if payload is None or payload["document"] is None:
        return jsonify(error="not_found", message=f"document {document_id}"), 404

    brief = payload["brief"]
    return jsonify(
        document=payload["document"].to_dict(),
        html=str(brief.html),
        toc=brief.toc,
        word_count=brief.word_count,
    )


@bp.get("/prospects/queue")
def prospect_queue():
    rows = current_app.repos.prospects.queue()  # type: ignore[attr-defined]
    return jsonify(
        items=[p.to_dict() for p in rows],
        composition=seed_data.QUEUE_COMPOSITION,
    )


@bp.post("/prospects/<document_id>/watch")
def set_watch(document_id: str):
    """Переключить бриф в watchlist: {"watched": true} или без тела — тогл."""
    body = request.get_json(silent=True) or {}
    repos = current_app.repos  # type: ignore[attr-defined]
    current = repos.documents.get(document_id)
    if current is None:
        return jsonify(error="not_found", message=f"document {document_id}"), 404
    watched = bool(body.get("watched", not current.watched))
    updated = repos.documents.set_watched(document_id, watched)
    return jsonify({k: v for k, v in updated.to_dict().items() if k != "full_markdown"})


# --- Desk ----------------------------------------------------------------

@bp.get("/desk/overview")
def desk_overview():
    data = service().overview()
    return jsonify(
        kpis=data["kpis"],
        latest_triggers=[_trigger_dict(t) for t in data["latest_triggers"]],
        watchlist=[
            {k: v for k, v in w.to_dict().items() if k != "full_markdown"}
            for w in data["watchlist"]
        ],
        recent_briefs=[
            {k: v for k, v in b.to_dict().items() if k != "full_markdown"}
            for b in data["recent_briefs"]
        ],
        queue=[p.to_dict() for p in data["queue"]],
        composition=data["composition"],
    )


@bp.get("/desk/watchlist")
def watchlist():
    rows = current_app.repos.documents.watchlist(50)  # type: ignore[attr-defined]
    return jsonify(
        items=[{k: v for k, v in d.to_dict().items() if k != "full_markdown"} for d in rows],
        meta={"total": len(rows)},
    )


# --- Sources -------------------------------------------------------------

@bp.get("/sources")
def list_sources():
    rows = current_app.repos.sources.list()  # type: ignore[attr-defined]
    return jsonify(items=[s.to_dict() for s in rows], meta={"total": len(rows)})


@bp.get("/sources/categories")
def list_categories():
    rows = current_app.repos.sources.categories()  # type: ignore[attr-defined]
    return jsonify(items=[c.to_dict() for c in rows])


@bp.post("/sources/categories/<path:key>/toggle")
def toggle_category(key: str):
    body = request.get_json(silent=True) or {}
    repos = current_app.repos  # type: ignore[attr-defined]
    current = next((c for c in repos.sources.categories() if c.key == key), None)
    if current is None:
        return jsonify(error="not_found", message=f"category {key}"), 404
    enabled = bool(body.get("enabled", not current.enabled))
    return jsonify(repos.sources.set_category_enabled(key, enabled).to_dict())


@bp.get("/sources/logs")
def ingest_logs():
    rows = current_app.repos.sources.logs()  # type: ignore[attr-defined]
    return jsonify(items=[log.to_dict() for log in rows])


# --- Сканирование источников (кнопка Find triggers) ----------------------

@bp.get("/scan/<job_id>")
def scan_status(job_id: str):
    """Статус фоновой задачи: стадия, лог прогресса, найдено/добавлено."""
    from app.services.scanner import registry as scan_registry

    job = scan_registry.get(job_id)
    if job is None:
        return jsonify(error="not_found", message=f"scan job {job_id}"), 404
    return jsonify(job.to_dict())


@bp.post("/scan")
def scan_start():
    """Запуск сканирования из API: {"category": "...", "months": 3}."""
    from app.scraping import sources as scraping_sources
    from app.services.scanner import ScanService
    from app.services.scanner import registry as scan_registry

    running = scan_registry.running()
    if running is not None:
        return jsonify(error="already_running", job=running.to_dict()), 409

    body = request.get_json(silent=True) or {}
    category_key = body.get("category", "")
    if not scraping_sources.is_known_category(category_key):
        return jsonify(
            error="unknown_category",
            message="Допустимые значения: " + ", ".join(k for _, k in scraping_sources.CATEGORIES),
        ), 400

    months = max(1, min(12, int(body.get("months") or current_app.config["SCAN_DEFAULT_MONTHS"])))
    service = ScanService(dict(current_app.config), job_repo=current_app.repos.jobs)
    job = service.start(
        category_key=category_key,
        category_label=scraping_sources.KEY_TO_LABEL.get(category_key, category_key),
        months=months,
    )
    return jsonify(job.to_dict()), 202


@bp.post("/scan/<job_id>/stop")
def scan_stop(job_id: str):
    from app.services.scanner import registry as scan_registry

    if not scan_registry.cancel(job_id):
        return jsonify(error="not_running", message=f"scan job {job_id}"), 409
    return jsonify(scan_registry.get(job_id).to_dict())


@bp.get("/scan/categories")
def scan_categories():
    from app.scraping import sources as scraping_sources

    return jsonify(items=[{"label": label, "key": key} for label, key in scraping_sources.CATEGORIES])


# --- Build brief (вкладка Command) ---------------------------------------

@bp.get("/brief/<job_id>")
def brief_status(job_id: str):
    """Статус запроса к агенту: стадия, лог и готовый ответ."""
    from app.services.brief_runner import registry as brief_registry

    job = brief_registry.get(job_id)
    if job is None:
        return jsonify(error="not_found", message=f"brief job {job_id}"), 404
    return jsonify(job.to_dict())


@bp.post("/brief")
def brief_start():
    """Запуск из API: {"q": "founders who exited a Swiss industrial group"}."""
    from app.services.brief_runner import BriefService
    from app.services.brief_runner import registry as brief_registry

    running = brief_registry.running()
    if running is not None:
        return jsonify(error="already_running", job=running.to_dict()), 409

    body = request.get_json(silent=True) or {}
    query = (body.get("q") or body.get("message") or "").strip()
    if not query:
        return jsonify(error="empty_query", message="Нужен непустой запрос"), 400

    runner = BriefService(dict(current_app.config), chat_jobs=current_app.repos.chat_jobs)
    return jsonify(runner.start(query, body.get("session_id")).to_dict()), 202


@bp.post("/brief/<job_id>/stop")
def brief_stop(job_id: str):
    from app.services.brief_runner import registry as brief_registry

    if not brief_registry.cancel(job_id):
        return jsonify(error="not_running", message=f"brief job {job_id}"), 409
    return jsonify(brief_registry.get(job_id).to_dict())
