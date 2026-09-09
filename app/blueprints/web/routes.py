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
from app.services.desk import DeskService

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
    """Prospect Brief — поиск и список результатов."""
    query = request.args.get("q", "")
    results = service().search_prospects(query)
    return render_template(
        "pages/brief.html",
        nav_active="brief",
        crumb="Search · Prospect briefs",
        query=query,
        results=results,
        filter_chips=seed_data.FILTER_CHIPS,
    )


@bp.get("/prospects/<prospect_id>")
def prospect_detail(prospect_id: str):
    """Досье по конкретному проспекту."""
    payload = service().dossier_for(prospect_id)
    if payload is None:
        abort(404)
    return render_template(
        "pages/detail.html",
        nav_active="brief",
        crumb="Dossier · Prospect brief",
        **payload,
    )


@bp.post("/prospects/<prospect_id>/watch")
def toggle_watch(prospect_id: str):
    repos = current_app.repos  # type: ignore[attr-defined]
    prospect = repos.prospects.get(prospect_id)
    if prospect is None:
        abort(404)
    repos.prospects.set_watched(prospect_id, not prospect.watched)
    return redirect(request.referrer or url_for("web.prospect_detail", prospect_id=prospect_id))


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
    return render_template(
        "pages/triggers.html",
        nav_active="triggers",
        crumb="Signals · Trigger feed",
        category=category,
        lookback=lookback,
        open_id=open_id,
        **data,  # rows, total, page, pages, per_page, categories, data_error
    )


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
