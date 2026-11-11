import sqlite3

import click
import psycopg
from flask import Flask, jsonify, redirect, request, send_from_directory, url_for
from werkzeug.exceptions import HTTPException

from .config import ROOT, configuration, validate_configuration
from .db import DatabaseConnectionError, close_db, init_db
from .errors import AppError
from .models import create_request
from .paypal import PayPalService
from .security import authenticated, require_management


def create_app(test_config=None):
    app = Flask(__name__, static_folder=None)
    app.config.update(configuration())
    if test_config:
        app.config.update(test_config)
        # An explicitly selected local/test database must never inherit a real
        # DATABASE_URL from the developer's environment file.
        if "DATABASE" in test_config and "DATABASE_URL" not in test_config:
            app.config["DATABASE_URL"] = ""
    validate_configuration(app.config)
    from .auth import auth, configure_sessions, render_login_error
    configure_sessions(app)
    app.register_blueprint(auth)
    app.teardown_appcontext(close_db)
    with app.app_context():
        try:
            init_db()
        except psycopg.Error:
            raise DatabaseConnectionError("PostgreSQL schema initialization failed; no reset was performed. Check permissions and schema compatibility.") from None
    app.extensions["paypal"] = PayPalService(app.config)
    from .routes import api
    app.register_blueprint(api)

    @app.errorhandler(AppError)
    def app_error(error):
        details = {"code": error.code, "message": error.message}
        if error.diagnostics.get("debug_id"):
            details["debug_id"] = error.diagnostics["debug_id"]
        if app.config["AUTH_REQUIRED"] and request.endpoint == "auth.login" and not request.is_json:
            response = app.response_class(render_login_error(error), mimetype="text/html")
        else:
            response = jsonify({"error": details})
        if error.status == 429:
            response.headers["Retry-After"] = str(error.diagnostics.get("retry_after", 60))
        return response, error.status

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify({"error": {"code": error.name.lower().replace(" ", "_"), "message": error.description}}), error.code

    @app.errorhandler(sqlite3.OperationalError)
    @app.errorhandler(psycopg.OperationalError)
    @app.errorhandler(DatabaseConnectionError)
    def db_error(_error):
        return jsonify({"error": {"code": "database_busy", "message": "The workspace is busy. Please retry shortly."}}), 503

    @app.errorhandler(Exception)
    def unexpected_error(error):
        # No exception body: upstream errors can contain sensitive payloads.
        app.logger.error("Unhandled application error: %s", type(error).__name__)
        return jsonify({"error": {"code": "internal_error", "message": "Something went wrong. Please retry."}}), 500

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Native form navigations under no-referrer can send Origin: null.
        # Preserve the login POST's same-origin Origin without leaking referrers
        # cross-site. Token pages keep the stricter bearer-link privacy policy.
        response.headers["Referrer-Policy"] = "same-origin" if request.endpoint == "auth.login" else "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=()"
        response.headers["X-Frame-Options"] = "DENY"
        if not request.path.startswith(("/assets/", "/auth-assets/")):
            response.headers["Cache-Control"] = "no-store"
        if app.config["HOSTED"]:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        if request.path == "/login":
            response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
        return response

    @app.get("/healthz")
    def healthz():
        # Render liveness: do not wake Neon or expose config on every health poll.
        return jsonify(status="ok")

    @app.route("/api", defaults={"path": ""}, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    @app.route("/api/<path:path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    def missing_api(path):
        raise AppError("not_found", "API endpoint not found.", 404)

    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def frontend(path):
        if path == "api" or path.startswith("api/"):
            raise AppError("not_found", "API endpoint not found.", 404)
        dist = ROOT / "dist"
        if path.startswith("assets/") or path in ("brand-mark.svg", "icons.svg"):
            if (dist / path).is_file() and (dist / path).resolve().is_relative_to(dist.resolve()):
                return send_from_directory(dist, path)
            raise AppError("not_found", "Asset not found.", 404)
        if not path.startswith("pay/"):
            if app.config["AUTH_REQUIRED"] and not authenticated():
                return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
            require_management()
        if not (dist / "index.html").exists():
            raise AppError("frontend_not_built", "Run npm run build or use the Vite development server.", 503)
        return send_from_directory(dist, "index.html")

    @app.cli.command("seed-demo")
    def seed_demo():
        """Explicitly add fictional, unpaid requests. Never invent successful payments."""
        from datetime import timedelta
        from .models import today
        from .db import get_db
        if get_db().execute("SELECT COUNT(*) AS count FROM payment_requests").fetchone()["count"]:
            click.echo("Database is not empty; no demo data added.")
            return
        for name, service, amount, days in [
            ("Alex Demo", "Fictional website design project", "250.00", 7),
            ("Sam Example", "Fictional brand identity package", "120.50", -3),
            ("Jordan Sample", "Fictional consulting session", "75.00", 0),
        ]:
            create_request({"client_name": name, "service_description": service, "amount": amount,
                            "due_date": (today() + timedelta(days=days)).isoformat()})
        click.echo("Added three fictional unpaid requests. No payments or AI responses were fabricated.")

    return app
