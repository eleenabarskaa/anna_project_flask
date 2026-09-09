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


# --- Prospects -----------------------------------------------------------

@bp.get("/prospects")
def list_prospects():
    query = request.args.get("q")
    rows = service().search_prospects(query)
    return jsonify(items=[p.to_dict() for p in rows], meta={"total": len(rows), "q": query})


@bp.get("/prospects/queue")
def prospect_queue():
    rows = current_app.repos.prospects.queue()  # type: ignore[attr-defined]
    return jsonify(
        items=[p.to_dict() for p in rows],
        composition=seed_data.QUEUE_COMPOSITION,
    )


@bp.get("/prospects/<prospect_id>")
def get_prospect(prospect_id: str):
    payload = service().dossier_for(prospect_id)
    if payload is None:
        return jsonify(error="not_found", message=f"prospect {prospect_id}"), 404
    return jsonify(
        prospect=payload["prospect"].to_dict(),
        dossier=payload["dossier"].to_dict(),
        enriched=payload["enriched"],
    )


@bp.post("/prospects/<prospect_id>/watch")
def set_watch(prospect_id: str):
    body = request.get_json(silent=True) or {}
    repos = current_app.repos  # type: ignore[attr-defined]
    current = repos.prospects.get(prospect_id)
    if current is None:
        return jsonify(error="not_found", message=f"prospect {prospect_id}"), 404
    watched = bool(body.get("watched", not current.watched))
    prospect = repos.prospects.set_watched(prospect_id, watched)
    return jsonify(prospect.to_dict())


# --- Desk ----------------------------------------------------------------

@bp.get("/desk/overview")
def desk_overview():
    data = service().overview()
    return jsonify(
        kpis=data["kpis"],
        latest_triggers=[_trigger_dict(t) for t in data["latest_triggers"]],
        watchlist=[w.to_dict() for w in data["watchlist"]],
        tasks=[t.to_dict() for t in data["tasks"]],
        queue=[p.to_dict() for p in data["queue"]],
        composition=data["composition"],
        recent_briefs=data["recent_briefs"],
    )


@bp.get("/desk/tasks")
def list_tasks():
    rows = current_app.repos.desk.tasks()  # type: ignore[attr-defined]
    return jsonify(items=[t.to_dict() for t in rows])


@bp.post("/desk/tasks/<int:task_id>/toggle")
def toggle_task(task_id: int):
    task = current_app.repos.desk.toggle_task(task_id)  # type: ignore[attr-defined]
    if task is None:
        return jsonify(error="not_found", message=f"task {task_id}"), 404
    return jsonify(task.to_dict())


@bp.get("/desk/watchlist")
def watchlist():
    rows = current_app.repos.desk.watchlist()  # type: ignore[attr-defined]
    return jsonify(items=[w.to_dict() for w in rows])


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
