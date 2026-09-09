"""Страницы desk-приложения (server-side rendering)."""

from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)

from app.repositories import seed_data
from app.scraping import sources as scraping_sources
from app.services.desk import DeskService
from app.services.scanner import ScanService
from app.services.scanner import registry as scan_registry

bp = Blueprint("web", __name__, template_folder="../../templates")


def service() -> DeskService:
    return DeskService(current_app.repos)  # type: ignore[attr-defined]


@bp.get("/")
def desk():
    """Desk · Overview. Три раскладки: desk | queue | command."""
    variant = request.args.get("variant", "desk")
    if variant not in {"desk", "queue", "command"}:
        variant = "desk"

    data = service().overview()
    return render_template(
        "pages/desk.html",
        nav_active="home",
        crumb="Desk · Overview",
        variant=variant,
        **data,
    )


@bp.get("/prospects")
def prospects():
    """Prospect Brief — список готовых брифов из researched_documents."""
    query = request.args.get("q", "")
    page = max(1, request.args.get("page", 1, type=int))
    data = service().documents_page(
        query=query,
        page=page,
        per_page=current_app.config["DOCUMENTS_PER_PAGE"],
    )
    return render_template(
        "pages/brief.html",
        nav_active="brief",
        crumb="Search · Prospect briefs",
        query=query,
        **data,  # documents, total, page, pages, per_page, data_error
    )


@bp.get("/prospects/<document_id>")
def prospect_detail(document_id: str):
    """Досье: full_markdown из researched_documents, отрендеренный в HTML."""
    payload = service().document(document_id)
    if payload is None:
        abort(404)
    return render_template(
        "pages/detail.html",
        nav_active="brief",
        crumb="Dossier · Prospect brief",
        **payload,
    )


@bp.get("/triggers")
def triggers():
    """Лента триггеров с фильтром по категории и пагинацией."""
    category = request.args.get("category", "All categories")
    lookback = request.args.get("lookback", current_app.config["DEFAULT_LOOKBACK_MONTHS"], type=int)
    page = request.args.get("page", 1, type=int)
    open_id = request.args.get("event", "t1")

    data = service().triggers_page(
        category=category,
        page=max(1, page),
        per_page=current_app.config["TRIGGERS_PER_PAGE"],
    )
    job_id = request.args.get("job")
    job = scan_registry.get(job_id) if job_id else scan_registry.running()

    return render_template(
        "pages/triggers.html",
        nav_active="triggers",
        crumb="Signals · Trigger feed",
        category=category,
        lookback=lookback,
        open_id=open_id,
        scan_categories=scraping_sources.CATEGORIES,
        scan_months=current_app.config["SCAN_DEFAULT_MONTHS"],
        scan_job=job.to_dict() if job else None,
        **data,  # rows, total, page, pages, per_page, categories, data_error
    )


@bp.post("/triggers/scan")
def start_scan():
    """Кнопка «Find triggers»: запускает сканирование в фоне и уводит на
    страницу с этой задачей — прогресс подтягивается опросом API."""
    if scan_registry.running():
        return redirect(url_for("web.triggers"))  # одно сканирование за раз

    category_key = request.form.get("scan_category", "")
    if not scraping_sources.is_known_category(category_key):
        abort(400)
    months = max(1, min(12, request.form.get("scan_months", type=int) or 3))

    service = ScanService(dict(current_app.config), job_repo=current_app.repos.jobs)  # type: ignore[attr-defined]
    job = service.start(
        category_key=category_key,
        category_label=scraping_sources.KEY_TO_LABEL.get(category_key, category_key),
        months=months,
    )
    return redirect(url_for("web.triggers", job=job.id))


@bp.post("/triggers/scan/<job_id>/stop")
def stop_scan(job_id: str):
    scan_registry.cancel(job_id)
    return redirect(url_for("web.triggers", job=job_id))


@bp.get("/sources")
def sources():
    """Конфигурация: категории триггеров, лицензированные источники, лог ингеста."""
    return render_template(
        "pages/sources.html",
        nav_active="sources",
        crumb="Configuration · Triggers & sources",
        **service().sources_page(),
    )


@bp.post("/sources/categories/<path:key>/toggle")
def toggle_category(key: str):
    repos = current_app.repos  # type: ignore[attr-defined]
    category = next((c for c in repos.sources.categories() if c.key == key), None)
    if category is None:
        abort(404)
    repos.sources.set_category_enabled(key, not category.enabled)
    return redirect(url_for("web.sources"))


@bp.post("/tasks/<int:task_id>/toggle")
def toggle_task(task_id: int):
    repos = current_app.repos  # type: ignore[attr-defined]
    if repos.desk.toggle_task(task_id) is None:
        abort(404)
    return redirect(request.referrer or url_for("web.desk"))


@bp.get("/healthz")
def healthz():
    return {"status": "ok", "backend": current_app.repos.backend}  # type: ignore[attr-defined]
