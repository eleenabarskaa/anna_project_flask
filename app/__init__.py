"""Meridian — Prospecting Desk (PWM).

Application factory.
"""

from __future__ import annotations

import os

from flask import Flask

from app.config import get_config
from app.repositories import build_repositories


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(get_config(config_name))
    app.config.from_prefixed_env()  # FLASK_* переменные перекрывают дефолты

    # Репозитории доступны как current_app.repos
    app.repos = build_repositories(dict(app.config))  # type: ignore[attr-defined]

    from app.blueprints.web.routes import bp as web_bp
    from app.blueprints.api.routes import bp as api_bp

    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp, url_prefix="/api/v1")

    _register_errorhandlers(app)
    _register_template_globals(app)

    return app


def _register_errorhandlers(app: Flask) -> None:
    from flask import jsonify, render_template, request

    def wants_json() -> bool:
        return request.path.startswith("/api/")

    @app.errorhandler(404)
    def not_found(err):  # noqa: ANN001
        if wants_json():
            return jsonify(error="not_found", message=str(err)), 404
        return render_template("pages/error.html", code=404, message="Страница не найдена"), 404

    @app.errorhandler(500)
    def server_error(err):  # noqa: ANN001  # pragma: no cover
        if wants_json():
            return jsonify(error="server_error", message="Internal server error"), 500
        return render_template("pages/error.html", code=500, message="Внутренняя ошибка"), 500


def _register_template_globals(app: Flask) -> None:
    from app.repositories import seed_data

    @app.context_processor
    def inject_globals():
        from datetime import datetime

        user_name = app.config["DESK_USER_NAME"]
        initials = "".join(part[0] for part in user_name.split()[:2]).upper()
        return {
            "app_name": "Meridian",
            "app_subtitle": "Prospecting Desk · PWM",
            "user_name": user_name,
            "user_short": f"{user_name.split()[0][0]}. {user_name.split()[-1]}",
            "user_initials": initials,
            "user_location": app.config["DESK_USER_LOCATION"],
            "coverage_days": seed_data.COVERAGE_DAYS,
            "total_triggers": seed_data.TOTAL_TRIGGERS,
            "prospect_count": len(seed_data.PROSPECTS),
            "now_label": datetime.now().strftime("%A · %-d %B %Y · %H:%M CET"),
        }
